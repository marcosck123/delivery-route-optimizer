from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import JetConfig, User
from ..schemas import JetConfigCreate, JetConfigResponse
from .auth import get_current_user

router = APIRouter(prefix="/api/jet-config", tags=["jet"])


@router.get("/", response_model=JetConfigResponse)
async def get_jet_config(user: User = Depends(get_current_user)):
    """Credenciais J&T do usuário (a chave de API nunca é devolvida)."""
    if not user.jet_config:
        raise HTTPException(status_code=404, detail="Credenciais J&T não configuradas")
    return user.jet_config


@router.put("/", response_model=JetConfigResponse)
async def upsert_jet_config(
    config_data: JetConfigCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cria ou atualiza as credenciais da J&T Express do usuário."""
    if user.jet_config:
        user.jet_config.jet_username = config_data.jet_username
        user.jet_config.jet_api_key = config_data.jet_api_key
    else:
        user.jet_config = JetConfig(
            jet_username=config_data.jet_username,
            jet_api_key=config_data.jet_api_key,
        )

    db.commit()
    db.refresh(user)
    return user.jet_config


@router.delete("/", status_code=204)
async def delete_jet_config(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Remove as credenciais J&T do usuário."""
    if not user.jet_config:
        raise HTTPException(status_code=404, detail="Credenciais J&T não configuradas")
    db.delete(user.jet_config)
    db.commit()
