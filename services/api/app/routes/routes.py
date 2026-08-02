import csv
import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    GEOCODE_PENDING,
    GEOCODE_RESOLVED,
    Delivery,
    Route,
    User,
)
from ..schemas import (
    AddressInput,
    DeliveryResponse,
    OcrBlock,
    OcrUploadResponse,
    RouteCreate,
    RouteListResponse,
    RouteResponse,
)
from ..utils.address_normalizer import build_full_address
from ..utils.geocoding import resolve_address
from ..utils.image_preprocessing import ImageDecodeError
from ..utils.ocr import extract_text, parse_addresses
from ..utils.jet_integration import get_jet_orders
from ..utils.optimization import (
    get_osrm_route,
    simple_tsp_optimization,
    total_distance_km,
)
from .auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/routes", tags=["routes"])

CSV_REQUIRED_COLUMNS = {"street", "number", "neighborhood"}
CSV_OPTIONAL_COLUMNS = {"cep", "complement"}


def build_delivery(address: AddressInput, jet_order_id: str | None = None) -> Delivery:
    """Create a delivery in the ``pending`` state — geocoding happens later."""
    return Delivery(
        address=build_full_address(
            address.street,
            address.number,
            address.neighborhood,
            address.cep,
            address.complement,
        ),
        street=address.street,
        number=address.number,
        neighborhood=address.neighborhood,
        cep=address.cep,
        complement=address.complement,
        geocode_status=GEOCODE_PENDING,
        jet_order_id=jet_order_id,
    )


def get_owned_route(route_id: int, user: User, db: Session) -> Route:
    """Busca a rota garantindo que ela pertence ao usuário autenticado."""
    route = (
        db.query(Route)
        .filter(Route.id == route_id, Route.user_id == user.id)
        .first()
    )
    if not route:
        raise HTTPException(status_code=404, detail="Rota não encontrada")
    return route


@router.post("/", response_model=RouteResponse)
async def create_route(
    route_data: RouteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria uma rota com os endereços iniciais (ainda sem geocodificar)."""
    route = Route(name=route_data.name, user_id=user.id)

    for address in route_data.deliveries:
        route.deliveries.append(build_delivery(address))

    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@router.get("/", response_model=list[RouteListResponse])
async def list_routes(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Histórico: todas as rotas do usuário, da mais recente para a mais antiga."""
    routes = (
        db.query(Route)
        .filter(Route.user_id == user.id)
        .order_by(Route.created_at.desc(), Route.id.desc())
        .all()
    )
    return [
        RouteListResponse(
            id=route.id,
            name=route.name,
            created_at=route.created_at,
            delivery_count=len(route.deliveries),
        )
        for route in routes
    ]


@router.get("/{route_id}", response_model=RouteResponse)
async def get_route(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retorna uma rota específica do usuário."""
    return get_owned_route(route_id, user, db)


@router.delete("/{route_id}", status_code=204)
async def delete_route(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a rota e suas entregas."""
    route = get_owned_route(route_id, user, db)
    db.delete(route)
    db.commit()


@router.post("/{route_id}/upload-csv")
async def upload_csv(
    route_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Importa entregas de um CSV com as colunas street, number, neighborhood
    (e, opcionalmente, cep e complement)."""
    route = get_owned_route(route_id, user, db)

    contents = await file.read()
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV precisa estar em UTF-8") from None

    reader = csv.DictReader(io.StringIO(text))
    headers = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
    missing = CSV_REQUIRED_COLUMNS - headers
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"CSV sem as colunas obrigatórias: {', '.join(sorted(missing))}",
        )

    added = 0
    for line_number, row in enumerate(reader, start=2):
        normalized = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            address = AddressInput(
                street=normalized.get("street", ""),
                number=normalized.get("number", ""),
                neighborhood=normalized.get("neighborhood", ""),
                cep=normalized.get("cep") or None,
                complement=normalized.get("complement") or None,
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Linha {line_number}: rua, número e bairro são obrigatórios",
            ) from None

        route.deliveries.append(build_delivery(address))
        added += 1

    db.commit()
    return {"message": f"{added} entrega(s) importada(s) para a rota {route_id}", "added": added}


@router.post("/{route_id}/ocr-upload", response_model=OcrUploadResponse)
async def ocr_upload(
    route_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lê os endereços de um print da lista de entregas.

    Não cria nada: devolve o texto lido para a usuária revisar antes de
    adicionar à rota.
    """
    get_owned_route(route_id, user, db)

    contents = await file.read()
    try:
        text = extract_text(contents)
    except ImageDecodeError:
        raise HTTPException(
            status_code=400, detail="Não consegui ler a imagem"
        ) from None
    except Exception as exc:  # Tesseract ausente, imagem corrompida...
        logger.exception("OCR failed for route %s: %s", route_id, exc)
        raise HTTPException(
            status_code=500, detail="Não consegui ler a imagem"
        ) from None

    blocks = [OcrBlock(**block) for block in parse_addresses(text)]
    if not blocks:
        return OcrUploadResponse(
            blocks=[],
            message="Não encontrei endereços nessa imagem. Tente dar zoom antes do print.",
        )

    return OcrUploadResponse(
        blocks=blocks,
        message=f"{len(blocks)} endereço(s) lido(s) — confira antes de adicionar.",
    )


@router.post("/{route_id}/geocode", response_model=list[DeliveryResponse])
async def geocode_route(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Geocodifica as entregas ainda pendentes da rota (cache → Google)."""
    route = get_owned_route(route_id, user, db)

    pending = [d for d in route.deliveries if d.geocode_status == GEOCODE_PENDING]
    for delivery in pending:
        result = await resolve_address(
            db,
            delivery.street or "",
            delivery.number or "",
            delivery.neighborhood or "",
            delivery.cep,
            delivery.complement,
        )
        delivery.latitude = result.latitude
        delivery.longitude = result.longitude
        delivery.geocode_status = result.status
        delivery.geocode_source = result.source
        delivery.geocode_message = result.message
        delivery.geocode_alternatives = result.alternatives or None

    db.commit()
    db.refresh(route)
    return route.deliveries


@router.post("/{route_id}/optimize", response_model=RouteResponse)
async def optimize_route(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Otimiza a ordem das entregas (TSP nearest-neighbor) e consulta o OSRM."""
    route = get_owned_route(route_id, user, db)

    if not route.deliveries:
        raise HTTPException(status_code=400, detail="Rota sem entregas")

    # Optimizing with half-resolved addresses would silently produce a wrong
    # route, so we block and name exactly which addresses are missing.
    unresolved = [d for d in route.deliveries if not d.is_ready_for_optimization]
    if unresolved:
        names = "; ".join(d.address for d in unresolved)
        raise HTTPException(
            status_code=400,
            detail=f"Confirme todos os endereços antes de otimizar: {names}",
        )

    deliveries_by_id = {d.id: d for d in route.deliveries}
    deliveries_dict = [
        {"id": d.id, "latitude": d.latitude, "longitude": d.longitude}
        for d in route.deliveries
    ]

    optimized_ids = simple_tsp_optimization(deliveries_dict)
    for index, delivery_id in enumerate(optimized_ids):
        deliveries_by_id[delivery_id].sequence_order = index

    ordered = [deliveries_by_id[delivery_id] for delivery_id in optimized_ids]
    coordinates = [(d.longitude, d.latitude) for d in ordered]

    osrm_result = await get_osrm_route(coordinates)

    route.optimization_result = {
        "optimized_order": optimized_ids,
        "estimated_distance_km": total_distance_km(coordinates),
        "osrm": osrm_result,
    }
    db.commit()
    db.refresh(route)
    return route


@router.post("/{route_id}/sync-jet", response_model=RouteResponse)
async def sync_jet_orders(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Substitui as entregas da rota pelos pedidos pendentes na J&T Express."""
    route = get_owned_route(route_id, user, db)

    if not user.jet_config:
        raise HTTPException(
            status_code=400, detail="Credenciais J&T não configuradas"
        )

    orders = await get_jet_orders(
        user.jet_config.jet_username, user.jet_config.jet_api_key
    )
    if not orders:
        raise HTTPException(status_code=404, detail="Nenhum pedido encontrado na J&T")

    route.deliveries.clear()
    db.flush()

    # J&T already returns coordinates, so these deliveries skip geocoding.
    for order in orders:
        route.deliveries.append(
            Delivery(
                address=order["address"],
                latitude=order["latitude"],
                longitude=order["longitude"],
                geocode_status=GEOCODE_RESOLVED,
                geocode_source="jet",
                jet_order_id=order.get("orderid"),
            )
        )

    route.optimization_result = None
    db.commit()
    db.refresh(route)
    return route
