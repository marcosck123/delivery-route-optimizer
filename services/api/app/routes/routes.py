import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Delivery, Route, User
from ..schemas import (
    RouteCreate,
    RouteListResponse,
    RouteResponse,
)
from ..utils.jet_integration import get_jet_orders
from ..utils.optimization import (
    get_osrm_route,
    simple_tsp_optimization,
    total_distance_km,
)
from .auth import get_current_user

router = APIRouter(prefix="/api/routes", tags=["routes"])

CSV_REQUIRED_COLUMNS = {"address", "latitude", "longitude"}


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
    """Cria uma rota com os endereços iniciais."""
    route = Route(name=route_data.name, user_id=user.id)

    for delivery in route_data.deliveries:
        route.deliveries.append(
            Delivery(
                address=delivery.address,
                latitude=delivery.latitude,
                longitude=delivery.longitude,
                jet_order_id=delivery.jet_order_id,
            )
        )

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
    """Importa entregas de um CSV com as colunas address, latitude, longitude."""
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
        address = normalized.get("address", "")
        if not address:
            raise HTTPException(
                status_code=400, detail=f"Linha {line_number}: endereço vazio"
            )
        try:
            latitude = float(normalized.get("latitude", ""))
            longitude = float(normalized.get("longitude", ""))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Linha {line_number}: latitude/longitude inválidas",
            ) from None

        route.deliveries.append(
            Delivery(address=address, latitude=latitude, longitude=longitude)
        )
        added += 1

    db.commit()
    return {"message": f"{added} entrega(s) importada(s) para a rota {route_id}", "added": added}


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

    for order in orders:
        route.deliveries.append(
            Delivery(
                address=order["address"],
                latitude=order["latitude"],
                longitude=order["longitude"],
                jet_order_id=order.get("orderid"),
            )
        )

    route.optimization_result = None
    db.commit()
    db.refresh(route)
    return route
