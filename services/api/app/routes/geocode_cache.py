"""Manage the saved addresses (the geocode cache).

A manual correction is permanent by design — that is what stops the same
address from being looked up twice. The flip side: a pin confirmed by mistake
sticks, and every future route starts wrong. These endpoints are the way out.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GeocodeCache, User
from ..schemas import GeocodeCacheResponse, GeocodeCacheUpdate
from ..utils.geocoding import visible_cache_filter
from .auth import get_current_user

router = APIRouter(prefix="/api/geocode-cache", tags=["geocode-cache"])


def get_visible_entry(entry_id: int, user: User, db: Session) -> GeocodeCache:
    """An entry the user may touch: her own, or a shared legacy one."""
    entry = (
        db.query(GeocodeCache)
        .filter(GeocodeCache.id == entry_id, visible_cache_filter(user.id))
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Endereço salvo não encontrado")
    return entry


@router.get("/", response_model=list[GeocodeCacheResponse])
async def list_cache(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Endereços salvos do usuário, do mais recente para o mais antigo."""
    return (
        db.query(GeocodeCache)
        .filter(visible_cache_filter(user.id))
        .order_by(GeocodeCache.updated_at.desc(), GeocodeCache.id.desc())
        .all()
    )


@router.delete("/{entry_id}", status_code=204)
async def delete_cache_entry(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Esquece o endereço: na próxima rota ele é localizado do zero."""
    entry = get_visible_entry(entry_id, user, db)
    db.delete(entry)
    db.commit()


@router.patch("/{entry_id}", response_model=GeocodeCacheResponse)
async def update_cache_entry(
    entry_id: int,
    payload: GeocodeCacheUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Corrige o ponto salvo. A correção vira ``manual`` e passa a ser dela."""
    entry = get_visible_entry(entry_id, user, db)

    entry.latitude = payload.latitude
    entry.longitude = payload.longitude
    entry.source = "manual"
    # Corrigir uma entrada compartilhada antiga cria o vínculo com quem corrigiu.
    if entry.user_id is None:
        entry.user_id = user.id

    db.commit()
    db.refresh(entry)
    return entry
