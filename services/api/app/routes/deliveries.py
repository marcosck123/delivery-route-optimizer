from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Delivery, User
from ..schemas import DeliveryCreate, DeliveryResponse
from .auth import get_current_user
from .routes import get_owned_route

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
    """Adiciona uma entrega a uma rota existente."""
    route = get_owned_route(route_id, user, db)

    delivery = Delivery(
        address=delivery_data.address,
        latitude=delivery_data.latitude,
        longitude=delivery_data.longitude,
        jet_order_id=delivery_data.jet_order_id,
    )
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
