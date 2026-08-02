from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    routes = relationship(
        "Route", back_populates="user", cascade="all, delete-orphan"
    )
    jet_config = relationship(
        "JetConfig",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class JetConfig(Base):
    """Credenciais da J&T Express de um usuário."""

    __tablename__ = "jet_configs"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    jet_username = Column(String(255), nullable=False)
    jet_api_key = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="jet_config")


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    optimization_result = Column(JSON, nullable=True)  # rota otimizada + payload OSRM

    # Optional starting point: where the trip begins (her home, the depot...).
    # It anchors the optimization but is never a stop to be delivered.
    start_latitude = Column(Float, nullable=True)
    start_longitude = Column(Float, nullable=True)
    start_address = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="routes")
    deliveries = relationship(
        "Delivery",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="Delivery.id",
    )


# Geocoding lifecycle of a delivery address.
GEOCODE_PENDING = "pending"
GEOCODE_RESOLVED = "resolved"
GEOCODE_NEEDS_CONFIRMATION = "needs_confirmation"
GEOCODE_FAILED = "failed"
GEOCODE_CONFIRMED = "confirmed"

# Statuses that carry trustworthy coordinates and allow route optimization.
GEOCODE_READY_STATUSES = (GEOCODE_RESOLVED, GEOCODE_CONFIRMED)


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False, index=True)

    # Full address text, assembled from the components below. Kept for display
    # and as the human-readable label everywhere in the UI.
    address = Column(String(500), nullable=False)

    # Address components typed by the user (Brazilian format).
    street = Column(String(255), nullable=True)
    number = Column(String(50), nullable=True)
    neighborhood = Column(String(255), nullable=True)
    cep = Column(String(20), nullable=True)
    complement = Column(String(255), nullable=True)

    # Coordinates are only filled in after geocoding, hence nullable.
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    geocode_status = Column(String(30), nullable=False, default=GEOCODE_PENDING)
    geocode_source = Column(String(20), nullable=True)  # google | cache | manual | jet
    # PT-BR message shown to the user; persisted so the review screen survives
    # a page reload.
    geocode_message = Column(String(255), nullable=True)
    # Divergent candidates ([{latitude, longitude}, ...]) when results disagree.
    geocode_alternatives = Column(JSON, nullable=True)

    sequence_order = Column(Integer, nullable=True)  # posição na rota otimizada
    jet_order_id = Column(String(100), nullable=True)  # ID do pedido na J&T

    route = relationship("Route", back_populates="deliveries")

    @property
    def is_ready_for_optimization(self) -> bool:
        return (
            self.latitude is not None
            and self.longitude is not None
            and self.geocode_status in GEOCODE_READY_STATUSES
        )


class GeocodeCache(Base):
    """Addresses already resolved, so the same address is never billed twice.

    A manual fix by the user overwrites a Google result: the human correction
    is the source of truth.
    """

    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True)
    address_key = Column(String(500), unique=True, nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    source = Column(String(20), nullable=False)  # google | manual
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
