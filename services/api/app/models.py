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
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="routes")
    deliveries = relationship(
        "Delivery",
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="Delivery.id",
    )


class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False, index=True)
    address = Column(String(500), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    sequence_order = Column(Integer, nullable=True)  # posição na rota otimizada
    jet_order_id = Column(String(100), nullable=True)  # ID do pedido na J&T

    route = relationship("Route", back_populates="deliveries")
