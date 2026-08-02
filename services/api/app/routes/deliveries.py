from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GEOCODE_CONFIRMED, User
from ..schemas import DeliveryCreate, DeliveryResponse, PinConfirm
from ..utils.geocoding import save_to_cache
from .auth import get_current_user
from .routes import build_delivery, get_owned_route

router = APIRouter(prefix="/api/routes/{route_id}/deliveries", tags=["deliveries"])


@router.get("/", response_model=list[DeliveryResponse])
async def list_deliveries(
    route_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Entregas da rota, já na ordem otimizada quando houver."""
    route = get_owned_route(route_id, user, db)
    return sorted(
        route.deliveries,
        key=lambda d: (d.sequence_order is None, d.sequence_order or 0, d.id),
    )


@router.post("/", response_model=DeliveryResponse, status_code=201)
async def add_delivery(
    route_id: int,
    delivery_data: DeliveryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adiciona uma entrega a uma rota existente (pendente de geocodificação)."""
    route = get_owned_route(route_id, user, db)

    delivery = build_delivery(delivery_data, delivery_data.jet_order_id)
    route.deliveries.append(delivery)
    # a ordem anterior deixa de valer quando entra um ponto novo
    route.optimization_result = None
    db.commit()
    db.refresh(delivery)
    return delivery


@router.delete("/{delivery_id}", status_code=204)
async def delete_delivery(
    route_id: int,
    delivery_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove uma entrega da rota."""
    route = get_owned_route(route_id, user, db)

    delivery = next((d for d in route.deliveries if d.id == delivery_id), None)
    if not delivery:
        raise HTTPException(status_code=404, detail="Entrega não encontrada")

    route.deliveries.remove(delivery)
    route.optimization_result = None
    db.commit()


@router.post("/{delivery_id}/confirm-pin", response_model=DeliveryResponse)
async def confirm_pin(
    route_id: int,
    delivery_id: int,
    pin: PinConfirm,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Grava o ponto que a usuária confirmou/arrastou no mapa.

    A correção humana vira a verdade: entra no cache como ``manual`` e
    sobrescreve o que o Google tinha respondido para o mesmo endereço.
    """
    route = get_owned_route(route_id, user, db)

    if pin.delivery_id != delivery_id:
        raise HTTPException(
            status_code=400, detail="Entrega informada não confere com a da URL"
        )

    delivery = next((d for d in route.deliveries if d.id == delivery_id), None)
    if not delivery:
        raise HTTPException(status_code=404, detail="Entrega não encontrada")

    delivery.latitude = pin.latitude
    delivery.longitude = pin.longitude
    delivery.geocode_status = GEOCODE_CONFIRMED
    delivery.geocode_source = "manual"
    delivery.geocode_message = None
    delivery.geocode_alternatives = None

    if delivery.street and delivery.number and delivery.neighborhood:
        save_to_cache(
            db,
            delivery.street,
            delivery.number,
            delivery.neighborhood,
            pin.latitude,
            pin.longitude,
            source="manual",
            user_id=user.id,
        )

    db.commit()
    db.refresh(delivery)
    return delivery


@router.put("/order", response_model=list[DeliveryResponse])
async def reorder_deliveries(
    route_id: int,
    delivery_ids: list[int],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Define manualmente a ordem das entregas (sobrescreve a otimização)."""
    route = get_owned_route(route_id, user, db)

    deliveries_by_id = {d.id: d for d in route.deliveries}
    if set(delivery_ids) != set(deliveries_by_id):
        raise HTTPException(
            status_code=400,
            detail="A lista precisa conter exatamente os IDs das entregas da rota",
        )

    for index, delivery_id in enumerate(delivery_ids):
        deliveries_by_id[delivery_id].sequence_order = index

    db.commit()
    return [deliveries_by_id[delivery_id] for delivery_id in delivery_ids]
