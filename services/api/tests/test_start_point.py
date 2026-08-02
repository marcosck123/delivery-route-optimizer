"""Ponto de partida da rota: define de onde o trajeto começa."""

import pytest

from app.utils import geocoding


def create_route(client, auth_headers, deliveries, name="Rota"):
    response = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": name, "deliveries": deliveries},
    )
    assert response.status_code == 200, response.text
    return response.json()


def set_pin(client, auth_headers, route_id, latitude, longitude, **extra):
    return client.post(
        f"/api/routes/{route_id}/start-point",
        headers=auth_headers,
        json={"latitude": latitude, "longitude": longitude, **extra},
    )


@pytest.fixture
def fake_google(monkeypatch, google_key):
    """Todo endereço resolve num ponto fixo, com precisão máxima."""

    async def _call(query, client):
        return {
            "status": "OK",
            "results": [
                {
                    "geometry": {
                        "location": {"lat": -12.7300, "lng": -60.1400},
                        "location_type": "ROOFTOP",
                    },
                    "partial_match": False,
                }
            ],
        }

    monkeypatch.setattr(geocoding, "_call_google", _call)


# ------------------------------------------------------------ definição


def test_start_point_from_a_pin_is_saved_immediately(
    client, auth_headers, sample_deliveries
):
    route = create_route(client, auth_headers, sample_deliveries)

    response = set_pin(
        client, auth_headers, route["id"], -12.75, -60.15, address="Minha casa"
    )
    assert response.status_code == 200

    body = response.json()
    assert body["saved"] is True
    assert body["status"] == "confirmed"
    assert body["source"] == "manual"

    saved = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert saved["start_latitude"] == -12.75
    assert saved["start_longitude"] == -60.15
    assert saved["start_address"] == "Minha casa"


def test_start_point_from_an_address_is_geocoded(
    client, auth_headers, sample_deliveries, fake_google
):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.post(
        f"/api/routes/{route['id']}/start-point",
        headers=auth_headers,
        json={"street": "Rua da Partida", "number": "10", "neighborhood": "Centro"},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["saved"] is True
    assert body["status"] == "resolved"
    assert body["latitude"] == -12.7300
    assert body["address"] == "Rua da Partida, 10 - Centro"


def test_ambiguous_start_address_waits_for_confirmation(
    client, auth_headers, sample_deliveries, monkeypatch, google_key
):
    """Endereço aproximado não é gravado às cegas — volta para ela conferir."""

    async def _approximate(query, client):
        return {
            "status": "OK",
            "results": [
                {
                    "geometry": {
                        "location": {"lat": -12.73, "lng": -60.14},
                        "location_type": "APPROXIMATE",
                    },
                    "partial_match": True,
                }
            ],
        }

    monkeypatch.setattr(geocoding, "_call_google", _approximate)
    route = create_route(client, auth_headers, sample_deliveries)

    body = client.post(
        f"/api/routes/{route['id']}/start-point",
        headers=auth_headers,
        json={"street": "Rua Duvidosa", "number": "1", "neighborhood": "Centro"},
    ).json()

    assert body["saved"] is False
    assert body["status"] == "needs_confirmation"
    assert body["message"]  # mensagem humana para a UI
    assert body["latitude"] is not None  # o palpite vai para o mapa

    saved = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert saved["start_latitude"] is None  # nada gravado ainda


def test_start_point_requires_address_or_pin(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.post(
        f"/api/routes/{route['id']}/start-point",
        headers=auth_headers,
        json={"street": "Rua sem número"},
    )
    assert response.status_code == 400
    assert "marque o ponto no mapa" in response.json()["detail"]


def test_start_point_pin_feeds_the_cache(
    client, auth_headers, sample_deliveries, fake_google
):
    """Confirmar o pin do ponto de partida vale para as próximas rotas."""
    route = create_route(client, auth_headers, sample_deliveries)

    set_pin(
        client,
        auth_headers,
        route["id"],
        -12.99,
        -60.99,
        street="Rua da Partida",
        number="10",
        neighborhood="Centro",
    )

    other = create_route(client, auth_headers, [], name="Outra")
    body = client.post(
        f"/api/routes/{other['id']}/start-point",
        headers=auth_headers,
        json={"street": "Rua da Partida", "number": "10", "neighborhood": "Centro"},
    ).json()

    assert body["latitude"] == -12.99  # veio do cache, não do Google
    assert body["saved"] is True


def test_start_point_is_scoped_to_owner(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    other = client.post(
        "/api/auth/register",
        json={"email": "outro@example.com", "password": "password123"},
    ).json()["access_token"]

    response = client.post(
        f"/api/routes/{route['id']}/start-point",
        headers={"Authorization": f"Bearer {other}"},
        json={"latitude": -12.7, "longitude": -60.1},
    )
    assert response.status_code == 404


def test_clear_start_point(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    set_pin(client, auth_headers, route["id"], -12.75, -60.15)

    assert (
        client.delete(
            f"/api/routes/{route['id']}/start-point", headers=auth_headers
        ).status_code
        == 204
    )

    saved = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert saved["start_latitude"] is None
    assert saved["start_address"] is None


# ------------------------------------------------------------ otimização


@pytest.fixture
def route_with_spread_deliveries(client, auth_headers, confirm_all):
    """Três entregas em linha, para a ordem depender de onde a rota começa."""
    addresses = [
        {"street": "Rua A", "number": "1", "neighborhood": "Centro"},
        {"street": "Rua B", "number": "2", "neighborhood": "Centro"},
        {"street": "Rua C", "number": "3", "neighborhood": "Centro"},
    ]
    route = create_route(client, auth_headers, addresses)
    # A = norte, B = meio, C = sul
    confirm_all(route["id"], coordinates=[(-12.70, -60.14), (-12.75, -60.14), (-12.80, -60.14)])
    return client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()


def test_optimize_without_start_point_keeps_the_old_behaviour(
    client, auth_headers, route_with_spread_deliveries
):
    route = route_with_spread_deliveries
    ids = [d["id"] for d in route["deliveries"]]

    body = client.post(
        f"/api/routes/{route['id']}/optimize", headers=auth_headers
    ).json()

    # começa pela primeira entrega cadastrada, como antes
    assert body["optimization_result"]["optimized_order"][0] == ids[0]
    assert body["optimization_result"]["start_point"] is None


def test_optimize_starts_from_the_nearest_delivery_to_the_start_point(
    client, auth_headers, route_with_spread_deliveries
):
    route = route_with_spread_deliveries
    ids = [d["id"] for d in route["deliveries"]]

    # partida ao sul: a rota tem que começar por C e subir
    set_pin(client, auth_headers, route["id"], -12.85, -60.14, address="Depósito")

    body = client.post(
        f"/api/routes/{route['id']}/optimize", headers=auth_headers
    ).json()

    order = body["optimization_result"]["optimized_order"]
    assert order == [ids[2], ids[1], ids[0]]


def test_start_point_is_not_a_delivery(
    client, auth_headers, route_with_spread_deliveries
):
    route = route_with_spread_deliveries
    set_pin(client, auth_headers, route["id"], -12.85, -60.14, address="Depósito")

    body = client.post(
        f"/api/routes/{route['id']}/optimize", headers=auth_headers
    ).json()

    assert len(body["deliveries"]) == 3  # continua com três paradas
    assert len(body["optimization_result"]["optimized_order"]) == 3
    assert body["optimization_result"]["start_point"]["address"] == "Depósito"


def test_optimized_route_starts_at_the_start_point(
    client, auth_headers, route_with_spread_deliveries, monkeypatch
):
    """O traçado enviado ao OSRM sai do ponto de partida."""
    seen: dict = {}

    async def _capture(coordinates, client=None):
        seen["coordinates"] = list(coordinates)
        return {"routes": [{"distance": 1000.0, "geometry": {"coordinates": []}}]}

    monkeypatch.setattr("app.routes.routes.get_osrm_route", _capture)

    route = route_with_spread_deliveries
    set_pin(client, auth_headers, route["id"], -12.85, -60.14, address="Depósito")
    client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)

    assert seen["coordinates"][0] == (-60.14, -12.85)  # (lon, lat) do OSRM
    assert len(seen["coordinates"]) == 4  # partida + 3 entregas


def test_setting_a_start_point_invalidates_the_previous_optimization(
    client, auth_headers, route_with_spread_deliveries
):
    route = route_with_spread_deliveries
    client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)

    set_pin(client, auth_headers, route["id"], -12.85, -60.14)

    saved = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert saved["optimization_result"] is None
