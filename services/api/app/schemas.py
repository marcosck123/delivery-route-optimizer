from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------- entregas


class AddressInput(BaseModel):
    """Brazilian address typed by the user. Coordinates come from geocoding."""

    street: str = Field(min_length=1, max_length=255)
    number: str = Field(min_length=1, max_length=50)
    neighborhood: str = Field(min_length=1, max_length=255)
    cep: Optional[str] = Field(default=None, max_length=20)
    complement: Optional[str] = Field(default=None, max_length=255)

    @field_validator("street", "number", "neighborhood")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Campo obrigatório")
        return value

    @field_validator("cep", "complement")
    @classmethod
    def strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class DeliveryCreate(AddressInput):
    jet_order_id: Optional[str] = Field(default=None, max_length=100)


class GeocodeCandidate(BaseModel):
    """One option Google returned for an address.

    ``formatted_address`` is what makes the choice possible: she recognizes
    the right one by reading it ("ah, esse é o bairro certo").
    """

    latitude: float
    longitude: float
    formatted_address: Optional[str] = None
    location_type: Optional[str] = None
    # Distance to the point currently saved, when there is one to compare with.
    distance_m: Optional[float] = None


class DeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    address: str
    street: Optional[str] = None
    number: Optional[str] = None
    neighborhood: Optional[str] = None
    cep: Optional[str] = None
    complement: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    geocode_status: str
    geocode_source: Optional[str] = None
    geocode_message: Optional[str] = None
    geocode_alternatives: Optional[list[GeocodeCandidate]] = None
    sequence_order: Optional[int] = None
    jet_order_id: Optional[str] = None


class OcrBlock(BaseModel):
    """One delivery read from a photo, before the user reviews it."""

    raw_text: str
    order_id: Optional[str] = None  # vira jet_order_id quando ela adiciona
    street: Optional[str] = None
    number: Optional[str] = None
    neighborhood: Optional[str] = None
    complement: Optional[str] = None
    cep: Optional[str] = None


class OcrUploadResponse(BaseModel):
    blocks: list[OcrBlock]
    message: str


class PinConfirm(BaseModel):
    """Sent when the user drags the pin to the right spot and confirms."""

    delivery_id: int
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GeocodeResult(BaseModel):
    """Internal result of a geocoding attempt. ``message`` is UI-ready PT-BR."""

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str
    source: Optional[str] = None
    message: Optional[str] = None
    # Every option worth showing. One item when the answer is unambiguous;
    # several when Google returned more than one or the cross-check diverged.
    candidates: list[GeocodeCandidate] = Field(default_factory=list)


# ------------------------------------------------------------------ rotas


class RouteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    deliveries: list[AddressInput] = Field(default_factory=list)


class RouteOptimize(BaseModel):
    route_id: int


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    deliveries: list[DeliveryResponse]
    optimization_result: Optional[dict[str, Any]] = None
    start_latitude: Optional[float] = None
    start_longitude: Optional[float] = None
    start_address: Optional[str] = None


class StartPointInput(BaseModel):
    """Where the route begins — an address to geocode, or a pin already chosen.

    Send the address components to have it looked up, or latitude/longitude
    straight away (confirmed pin, current location).
    """

    street: Optional[str] = Field(default=None, max_length=255)
    number: Optional[str] = Field(default=None, max_length=50)
    neighborhood: Optional[str] = Field(default=None, max_length=255)
    cep: Optional[str] = Field(default=None, max_length=20)
    complement: Optional[str] = Field(default=None, max_length=255)

    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    address: Optional[str] = Field(default=None, max_length=500)

    @property
    def has_pin(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def has_address(self) -> bool:
        return bool(self.street and self.number and self.neighborhood)


class StartPointResponse(BaseModel):
    """``saved`` is False when the point still needs her eyes on the map."""

    saved: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    status: str
    source: Optional[str] = None
    message: Optional[str] = None
    candidates: list[GeocodeCandidate] = Field(default_factory=list)


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


# ------------------------------------------------------ endereços salvos


class GeocodeCacheResponse(BaseModel):
    """One saved address, as shown on the "Endereços salvos" screen."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    address: Optional[str] = None
    address_key: str
    latitude: float
    longitude: float
    source: str  # google | manual
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GeocodeCacheUpdate(BaseModel):
    """New coordinates for a saved address, after she fixed the pin."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class GeocodeRecheckResponse(BaseModel):
    """Options for a saved address, to correct it by choosing instead of guessing."""

    candidates: list[GeocodeCandidate] = Field(default_factory=list)
    current_latitude: float
    current_longitude: float
    message: Optional[str] = None


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
