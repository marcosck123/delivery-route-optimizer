"""Integração com a J&T Express.

A API de produção da J&T exige credenciais e acordo de integração — as
requisições são assinadas com um digest MD5 do corpo + a chave privada,
codificado em base64.

Enquanto as credenciais reais não estiverem disponíveis, o módulo opera em
modo *sandbox*: se ``JET_API_BASE_URL`` não estiver configurado, devolve
pedidos fictícios com o mesmo formato do retorno real, o que mantém o fluxo
da aplicação (sincronizar → otimizar → mapa) funcionando ponta a ponta.
"""

import base64
import hashlib
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

JET_API_BASE_URL = os.getenv("JET_API_BASE_URL", "").rstrip("/")
JET_TIMEOUT_SECONDS = float(os.getenv("JET_TIMEOUT_SECONDS", "15"))

# Pedidos de exemplo usados no modo sandbox (região de Vilhena/RO).
SANDBOX_ORDERS: list[dict[str, Any]] = [
    {
        "orderid": "PEDIDO-001",
        "address": "Rua A, 123, Vilhena",
        "latitude": -12.7406,
        "longitude": -60.1458,
    },
    {
        "orderid": "PEDIDO-002",
        "address": "Rua B, 456, Vilhena",
        "latitude": -12.7452,
        "longitude": -60.1391,
    },
    {
        "orderid": "PEDIDO-003",
        "address": "Av. Major Amarante, 789, Vilhena",
        "latitude": -12.7377,
        "longitude": -60.1503,
    },
]


def build_signature(body: str, api_key: str) -> str:
    """Digest exigido pela J&T: base64(md5(body + api_key))."""
    digest = hashlib.md5(f"{body}{api_key}".encode()).digest()
    return base64.b64encode(digest).decode()


def _normalize_order(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Converte um pedido da J&T no formato interno, ou ``None`` se incompleto."""
    address = raw.get("address") or raw.get("receiverAddress") or raw.get("recipientAddress")
    latitude = raw.get("latitude") or raw.get("lat")
    longitude = raw.get("longitude") or raw.get("lng") or raw.get("lon")

    if not address or latitude is None or longitude is None:
        logger.warning("Pedido J&T ignorado por falta de endereço/coordenadas: %s", raw)
        return None

    return {
        "orderid": str(raw.get("orderid") or raw.get("txlogisticId") or ""),
        "address": str(address),
        "latitude": float(latitude),
        "longitude": float(longitude),
    }


async def get_jet_orders(username: str, api_key: str) -> list[dict[str, Any]]:
    """Busca os pedidos pendentes do usuário na J&T Express.

    Devolve uma lista de dicts com ``orderid``, ``address``, ``latitude`` e
    ``longitude``.
    """
    if not JET_API_BASE_URL:
        logger.info("JET_API_BASE_URL não configurado — usando pedidos de sandbox")
        return [dict(order) for order in SANDBOX_ORDERS]

    body = f'{{"username":"{username}"}}'
    headers = {
        "Content-Type": "application/json",
        "apiAccount": username,
        "digest": build_signature(body, api_key),
    }

    async with httpx.AsyncClient(timeout=JET_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{JET_API_BASE_URL}/orders/pending", content=body, headers=headers
        )
        response.raise_for_status()
        payload = response.json()

    raw_orders = payload.get("data") or payload.get("orders") or []
    normalized = (_normalize_order(order) for order in raw_orders)
    return [order for order in normalized if order is not None]
