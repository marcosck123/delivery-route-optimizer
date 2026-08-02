from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------- entregas


class DeliveryCreate(BaseModel):
    address: str = Field(min_length=1, max_length=500)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    jet_order_id: Optional[str] = Field(default=None, max_length=100)

    @field_validator("address")
    @classmethod
    def strip_address(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Endereço não pode ser vazio")
        return value


class DeliveryResponse(DeliveryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    sequence_order: Optional[int] = None


# ------------------------------------------------------------------ rotas


class RouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    deliveries: list[DeliveryCreate] = Field(default_factory=list)


class RouteOptimize(BaseModel):
    route_id: int


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    deliveries: list[DeliveryResponse]
    optimization_result: Optional[dict[str, Any]] = None


class RouteListResponse(BaseModel):
    id: int
    name: str
    created_at: datetime
    delivery_count: int


# ------------------------------------------------------------- usuários


class UserRegister(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("Email inválido")
        return value


class UserLogin(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ------------------------------------------------------------- J&T Express


class JetConfigCreate(BaseModel):
    jet_username: str = Field(min_length=1, max_length=255)
    jet_api_key: str = Field(min_length=1, max_length=255)


class JetConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    jet_username: str
    created_at: datetime
    # a api_key nunca é devolvida ao cliente
