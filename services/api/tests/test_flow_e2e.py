"""End-to-end: address form -> geocode -> pin confirmation -> optimize.

Google is mocked at the HTTP seam; OSRM is mocked by the global fixture.
Everything else (routing, auth, persistence, cache) is the real stack.
"""

import pytest

from app.utils import geocoding

ADDRESSES = [
    {
        "street": "Avenida Major Amarante",
        "number": "1000",
        "neighborhood": "Centro",
    },
    {
        "street": "Rua Residencial Florença Um",  # extenso -> dispara cross-check
        "number": "8046",
        "neighborhood": "Residencial Florença",
        "complement": "CASA",
    },
    {
        "street": "Rua Inexistente",
        "number": "1",
        "neighborhood": "Centro",
    },
]


def ok(lat, lng, location_type="ROOFTOP", partial=False):
    return {
        "status": "OK",
        "results": [
            {
                "geometry": {
                    "location": {"lat": lat, "lng": lng},
                    "location_type": location_type,
                },
                "partial_match": partial,
            }
        ],
    }


ZERO = {"status": "ZERO_RESULTS", "results": []}


@pytest.fixture
def fake_google(monkeypatch, google_key):
    """Replies per query: um endereço resolve, um diverge, um falha."""
    calls: list[str] = []

    async def _call(query: str, client):
        calls.append(query)
        if "Major Amarante" in query:
            return ok(-12.7406, -60.1458)
        if "Florença Um" in query:  # grafia original
            return ok(-12.7500, -60.1600)
        if "Florença 1" in query:  # variante com dígito, ~1 km longe
            return ok(-12.7600, -60.1700)
        if "Rua Inexistente" in query:
            return ZERO
        if query.startswith("Centro,"):  # diagnóstico: bairro existe
            return ok(-12.7406, -60.1458)
        return ZERO

    monkeypatch.setattr(geocoding, "_call_google", _call)
    return calls


def test_full_flow_from_address_to_optimized_route(
    client, auth_headers, fake_google
):
    # 1. cria a rota só com endereços (sem coordenada nenhuma)
    route = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "Segunda de Manhã", "deliveries": ADDRESSES},
    ).json()
    route_id = route["id"]
    assert all(d["geocode_status"] == "pending" for d in route["deliveries"])

    # 2. geocodifica
    geocoded = client.post(
        f"/api/routes/{route_id}/geocode", headers=auth_headers
    ).json()
    by_street = {d["street"]: d for d in geocoded}

    resolved = by_street["Avenida Major Amarante"]
    assert resolved["geocode_status"] == "resolved"
    assert resolved["latitude"] == -12.7406

    divergent = by_street["Rua Residencial Florença Um"]
    assert divergent["geocode_status"] == "needs_confirmation"
    assert divergent["geocode_message"] == "Dois resultados diferentes — confirme no mapa"
    assert len(divergent["geocode_alternatives"]) == 2

    failed = by_street["Rua Inexistente"]
    assert failed["geocode_status"] == "failed"
    assert failed["geocode_message"] == "Rua não encontrada"
    assert failed["latitude"] is None

    # 3. otimizar ainda está bloqueado, nomeando quem falta
    blocked = client.post(f"/api/routes/{route_id}/optimize", headers=auth_headers)
    assert blocked.status_code == 400
    assert "Rua Inexistente" in blocked.json()["detail"]
    assert "Major Amarante" not in blocked.json()["detail"]  # esse já está pronto

    # 4. a usuária confirma os pins que faltam
    for delivery, (lat, lon) in [
        (divergent, (-12.7500, -60.1600)),
        (failed, (-12.7450, -60.1500)),
    ]:
        confirmed = client.post(
            f"/api/routes/{route_id}/deliveries/{delivery['id']}/confirm-pin",
            headers=auth_headers,
            json={
                "delivery_id": delivery["id"],
                "latitude": lat,
                "longitude": lon,
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["geocode_status"] == "confirmed"

    # 5. agora otimiza
    optimized = client.post(
        f"/api/routes/{route_id}/optimize", headers=auth_headers
    )
    assert optimized.status_code == 200

    body = optimized.json()
    assert len(body["optimization_result"]["optimized_order"]) == 3
    assert sorted(d["sequence_order"] for d in body["deliveries"]) == [0, 1, 2]
    assert all(d["latitude"] is not None for d in body["deliveries"])


def test_second_route_with_same_addresses_reuses_the_cache(
    client, auth_headers, fake_google
):
    """A segunda rota com os mesmos endereços não gasta chamada no Google."""
    first = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "Rota 1", "deliveries": ADDRESSES[:1]},
    ).json()
    client.post(f"/api/routes/{first['id']}/geocode", headers=auth_headers)
    calls_after_first = len(fake_google)
    assert calls_after_first > 0

    second = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "Rota 2", "deliveries": ADDRESSES[:1]},
    ).json()
    geocoded = client.post(
        f"/api/routes/{second['id']}/geocode", headers=auth_headers
    ).json()

    assert len(fake_google) == calls_after_first  # nenhuma chamada nova
    assert geocoded[0]["geocode_source"] == "cache"
    assert geocoded[0]["geocode_status"] == "resolved"


def test_manual_correction_wins_on_the_next_route(
    client, auth_headers, fake_google
):
    """Ela corrigiu o pin; o mesmo endereço já nasce corrigido depois."""
    first = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "Rota 1", "deliveries": ADDRESSES[:1]},
    ).json()
    client.post(f"/api/routes/{first['id']}/geocode", headers=auth_headers)
    delivery_id = first["deliveries"][0]["id"]

    client.post(
        f"/api/routes/{first['id']}/deliveries/{delivery_id}/confirm-pin",
        headers=auth_headers,
        json={"delivery_id": delivery_id, "latitude": -12.9, "longitude": -60.9},
    )

    second = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "Rota 2", "deliveries": ADDRESSES[:1]},
    ).json()
    geocoded = client.post(
        f"/api/routes/{second['id']}/geocode", headers=auth_headers
    ).json()

    assert geocoded[0]["latitude"] == -12.9  # a correção humana venceu o Google
    assert geocoded[0]["geocode_status"] == "confirmed"
