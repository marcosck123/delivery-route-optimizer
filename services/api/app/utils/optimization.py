"""Otimização de rota: TSP nearest-neighbor + consulta ao OSRM."""

import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any, Optional, Sequence

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0

# O servidor público do OSRM limita o número de coordenadas por requisição.
MAX_OSRM_COORDINATES = 100


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos (lat/lon em graus)."""
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * asin(sqrt(a)) * EARTH_RADIUS_KM


def simple_tsp_optimization(
    deliveries: Sequence[dict[str, Any]],
    start: Optional[tuple[float, float]] = None,
) -> list[int]:
    """TSP por vizinho mais próximo.

    Recebe dicts com ``id``, ``latitude`` e ``longitude``; devolve os ``id``
    na ordem de visita.

    ``start`` é o ponto de partida da rota, em ``(latitude, longitude)``: a
    primeira entrega passa a ser a mais próxima dele. O ponto de partida não é
    uma entrega e não entra na lista devolvida. Sem ele, a rota começa pela
    primeira entrega, como antes.
    """
    if not deliveries:
        return []

    if start is None:
        order = [0]
        unvisited = set(range(1, len(deliveries)))
        current_lat = deliveries[0]["latitude"]
        current_lon = deliveries[0]["longitude"]
    else:
        order = []
        unvisited = set(range(len(deliveries)))
        current_lat, current_lon = start

    while unvisited:
        nearest = min(
            unvisited,
            key=lambda i: haversine(
                current_lat,
                current_lon,
                deliveries[i]["latitude"],
                deliveries[i]["longitude"],
            ),
        )
        order.append(nearest)
        unvisited.remove(nearest)
        current_lat = deliveries[nearest]["latitude"]
        current_lon = deliveries[nearest]["longitude"]

    return [deliveries[i]["id"] for i in order]


def total_distance_km(coordinates: Sequence[tuple[float, float]]) -> float:
    """Soma das distâncias em linha reta ao longo da sequência ``(lon, lat)``."""
    total = 0.0
    for (lon_a, lat_a), (lon_b, lat_b) in zip(coordinates, coordinates[1:]):
        total += haversine(lat_a, lon_a, lat_b, lon_b)
    return round(total, 3)


async def get_osrm_route(
    coordinates: Sequence[tuple[float, float]],
    client: Optional[httpx.AsyncClient] = None,
) -> dict[str, Any]:
    """Consulta o OSRM para obter a geometria e a distância real da rota.

    ``coordinates`` usa a ordem ``(longitude, latitude)`` — a mesma do OSRM.
    Em caso de falha devolve ``{"error": ...}`` em vez de estourar: a
    otimização já é útil sem a geometria da malha viária.
    """
    if len(coordinates) < 2:
        return {"waypoints": [], "routes": []}

    if len(coordinates) > MAX_OSRM_COORDINATES:
        return {
            "error": (
                f"Rota com {len(coordinates)} pontos excede o limite de "
                f"{MAX_OSRM_COORDINATES} do servidor público do OSRM"
            )
        }

    coords_str = ";".join(f"{lon},{lat}" for lon, lat in coordinates)
    url = (
        f"{settings.osrm_base_url.rstrip('/')}/route/v1/driving/{coords_str}"
        "?overview=full&geometries=geojson&steps=false"
    )

    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.osrm_timeout_seconds)
    try:
        response = await client.get(url, timeout=settings.osrm_timeout_seconds)
        if response.status_code != 200:
            logger.warning("OSRM respondeu %s: %s", response.status_code, response.text[:200])
            return {"error": f"OSRM retornou status {response.status_code}"}
        return response.json()
    except Exception as exc:  # rede fora do ar, timeout, JSON inválido...
        logger.warning("Falha ao consultar OSRM: %s", exc)
        return {"error": str(exc)}
    finally:
        if owns_client:
            await client.aclose()
