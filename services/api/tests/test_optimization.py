import httpx
import pytest

from app.utils.optimization import (
    MAX_OSRM_COORDINATES,
    get_osrm_route,
    haversine,
    simple_tsp_optimization,
    total_distance_km,
)


def test_haversine_known_distance():
    # Vilhena (RO) → Porto Velho (RO): ~603 km em linha reta
    distance = haversine(-12.7406, -60.1458, -8.7619, -63.9039)
    assert 590 < distance < 615


def test_haversine_same_point_is_zero():
    assert haversine(-12.74, -60.14, -12.74, -60.14) == 0


def test_tsp_empty():
    assert simple_tsp_optimization([]) == []


def test_tsp_single_point():
    assert simple_tsp_optimization([{"id": 7, "latitude": 0.0, "longitude": 0.0}]) == [7]


def test_tsp_picks_nearest_neighbor():
    deliveries = [
        {"id": 1, "latitude": 0.0, "longitude": 0.0},  # partida
        {"id": 2, "latitude": 0.0, "longitude": 5.0},  # longe
        {"id": 3, "latitude": 0.0, "longitude": 1.0},  # perto da partida
        {"id": 4, "latitude": 0.0, "longitude": 2.0},
    ]
    assert simple_tsp_optimization(deliveries) == [1, 3, 4, 2]


def test_tsp_keeps_all_ids():
    deliveries = [
        {"id": i, "latitude": -12.7 - i * 0.01, "longitude": -60.1 + i * 0.02}
        for i in range(1, 11)
    ]
    order = simple_tsp_optimization(deliveries)
    assert sorted(order) == [d["id"] for d in deliveries]


def test_total_distance_km():
    assert total_distance_km([]) == 0
    assert total_distance_km([(-60.1, -12.7)]) == 0
    assert total_distance_km([(-60.1, -12.7), (-60.2, -12.7)]) > 0


async def test_get_osrm_route_needs_two_points():
    result = await get_osrm_route([(-60.1, -12.7)])
    assert result == {"waypoints": [], "routes": []}


async def test_get_osrm_route_rejects_too_many_points():
    coordinates = [(-60.1 + i * 0.001, -12.7) for i in range(MAX_OSRM_COORDINATES + 1)]
    result = await get_osrm_route(coordinates)
    assert "excede o limite" in result["error"]


async def test_get_osrm_route_parses_response():
    payload = {"code": "Ok", "routes": [{"distance": 1234.5}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))

    async with httpx.AsyncClient(transport=transport) as client:
        result = await get_osrm_route([(-60.1, -12.7), (-60.2, -12.8)], client=client)

    assert result["routes"][0]["distance"] == 1234.5


async def test_get_osrm_route_handles_http_error():
    transport = httpx.MockTransport(lambda request: httpx.Response(429, text="rate limit"))

    async with httpx.AsyncClient(transport=transport) as client:
        result = await get_osrm_route([(-60.1, -12.7), (-60.2, -12.8)], client=client)

    assert result["error"] == "OSRM retornou status 429"


async def test_get_osrm_route_handles_network_failure():
    def _raise(request):
        raise httpx.ConnectError("sem rede")

    transport = httpx.MockTransport(_raise)

    async with httpx.AsyncClient(transport=transport) as client:
        result = await get_osrm_route([(-60.1, -12.7), (-60.2, -12.8)], client=client)

    assert "sem rede" in result["error"]
