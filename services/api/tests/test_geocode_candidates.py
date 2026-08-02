"""Candidatos do Google: quando há ambiguidade, ela escolhe em vez de adivinhar."""

import httpx
import pytest

from app.models import GEOCODE_NEEDS_CONFIRMATION, GEOCODE_RESOLVED, GeocodeCache
from app.database import SessionLocal
from app.utils import geocoding
from app.utils.geocoding import Messages, geocode_address, geocode_free_form


def result(lat, lng, formatted, location_type="ROOFTOP", partial=False):
    return {
        "geometry": {
            "location": {"lat": lat, "lng": lng},
            "location_type": location_type,
        },
        "formatted_address": formatted,
        "partial_match": partial,
    }


def payload(*results):
    return {"status": "OK", "results": list(results)}


class FakeGoogle:
    def __init__(self, responses):
        self.responses = list(responses)
        self.queries: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.queries.append(request.url.params.get("address", ""))
        payload_out = (
            self.responses.pop(0)
            if self.responses
            else {"status": "ZERO_RESULTS", "results": []}
        )
        return httpx.Response(200, json=payload_out)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ------------------------------------------------------------ candidatos


async def test_single_clear_result_returns_one_candidate(google_key):
    google = FakeGoogle(
        [payload(result(-12.74, -60.14, "Rua A, 10 - Centro, Vilhena - RO"))]
    )
    async with google.client() as client:
        found = await geocode_address("Rua A", "10", "Centro", client=client)

    assert found.status == GEOCODE_RESOLVED
    assert len(found.candidates) == 1
    assert found.candidates[0].formatted_address == "Rua A, 10 - Centro, Vilhena - RO"
    assert found.candidates[0].location_type == "ROOFTOP"


async def test_multiple_results_ask_her_to_choose(google_key):
    """Dois endereços parecidos: o app não escolhe sozinho."""
    google = FakeGoogle(
        [
            payload(
                result(-12.74, -60.14, "Rua Sete, 10 - Centro, Vilhena - RO"),
                result(-12.79, -60.19, "Rua Sete, 10 - Jardim Eldorado, Vilhena - RO"),
            )
        ]
    )
    async with google.client() as client:
        found = await geocode_address("Rua Sete", "10", "Centro", client=client)

    assert found.status == GEOCODE_NEEDS_CONFIRMATION
    assert found.message == Messages.MULTIPLE
    assert len(found.candidates) == 2
    assert [c.formatted_address for c in found.candidates] == [
        "Rua Sete, 10 - Centro, Vilhena - RO",
        "Rua Sete, 10 - Jardim Eldorado, Vilhena - RO",
    ]


async def test_divergent_cross_check_returns_both_with_addresses(google_key):
    google = FakeGoogle(
        [
            payload(result(-12.7406, -60.1458, "Rua Florença-Um, 10")),
            payload(result(-12.7510, -60.1458, "Rua Florença 1, 10")),
        ]
    )
    async with google.client() as client:
        found = await geocode_address(
            "Rua Florença Um", "10", "Centro", client=client
        )

    assert found.message == Messages.DIVERGENT
    assert len(found.candidates) == 2
    assert found.candidates[0].formatted_address == "Rua Florença-Um, 10"
    assert found.candidates[1].formatted_address == "Rua Florença 1, 10"


async def test_candidates_carry_distance_to_the_current_pin(google_key):
    """A opção certa costuma estar longe do ponto salvo por engano."""
    google = FakeGoogle(
        [
            payload(
                result(-12.7406, -60.1458, "Perto"),
                result(-12.7500, -60.1458, "Longe"),
            )
        ]
    )
    async with google.client() as client:
        found = await geocode_address(
            "Rua A", "10", "Centro", client=client, reference=(-12.7406, -60.1458)
        )

    assert found.candidates[0].distance_m == 0.0
    # ~1 km ao sul
    assert 900 < found.candidates[1].distance_m < 1200


async def test_candidates_have_no_distance_without_a_reference(google_key):
    google = FakeGoogle([payload(result(-12.74, -60.14, "Rua A"))])
    async with google.client() as client:
        found = await geocode_address("Rua A", "10", "Centro", client=client)

    assert found.candidates[0].distance_m is None


# ---------------------------------------------------------- busca livre


async def test_free_form_returns_every_option(google_key):
    google = FakeGoogle(
        [payload(result(-12.74, -60.14, "Opção 1"), result(-12.75, -60.15, "Opção 2"))]
    )
    async with google.client() as client:
        candidates, message = await geocode_free_form(
            "Rua Osório, 250 - Centro", reference=(-12.74, -60.14), client=client
        )

    assert message is None
    assert [c.formatted_address for c in candidates] == ["Opção 1", "Opção 2"]
    assert candidates[0].distance_m == 0.0
    assert "Vilhena" in google.queries[0]


async def test_free_form_without_api_key():
    candidates, message = await geocode_free_form("Rua A, 10 - Centro")
    assert candidates == []
    assert message == Messages.NOT_CONFIGURED


async def test_free_form_when_nothing_is_found(google_key):
    google = FakeGoogle([{"status": "ZERO_RESULTS", "results": []}])
    async with google.client() as client:
        candidates, message = await geocode_free_form("Rua Fantasma", client=client)

    assert candidates == []
    assert message == Messages.ADDRESS_NOT_FOUND


# -------------------------------------------------- endpoint de recheck


@pytest.fixture
def saved_entry(client, auth_headers, db):
    entry = GeocodeCache(
        user_id=1,
        address_key="rua osorio 250 centro vilhena",
        address="Rua Osório, 250 - Centro",
        latitude=-12.7406,
        longitude=-60.1458,
        source="manual",
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_recheck_lists_the_options(
    client, auth_headers, saved_entry, monkeypatch, google_key
):
    async def _call(query, http_client):
        return payload(
            result(-12.7406, -60.1458, "Rua Osório, 250 - Centro, Vilhena - RO"),
            result(-12.7500, -60.1458, "Rua Osório, 250 - Jardim, Vilhena - RO"),
        )

    monkeypatch.setattr(geocoding, "_call_google", _call)

    response = client.post(
        f"/api/geocode-cache/{saved_entry.id}/recheck", headers=auth_headers
    )
    assert response.status_code == 200

    body = response.json()
    assert body["current_latitude"] == -12.7406
    assert len(body["candidates"]) == 2
    assert body["candidates"][0]["formatted_address"].endswith("Vilhena - RO")
    # distância até o ponto salvo hoje
    assert body["candidates"][0]["distance_m"] == 0.0
    assert body["candidates"][1]["distance_m"] > 900


def test_recheck_without_api_key_explains_itself(client, auth_headers, saved_entry):
    body = client.post(
        f"/api/geocode-cache/{saved_entry.id}/recheck", headers=auth_headers
    ).json()

    assert body["candidates"] == []
    assert body["message"] == Messages.NOT_CONFIGURED
    # o ponto atual continua vindo, para ela ao menos arrastar o pin
    assert body["current_latitude"] == -12.7406


def test_recheck_is_scoped_to_owner(client, auth_headers, saved_entry):
    intruder = client.post(
        "/api/auth/register",
        json={"email": "curioso@example.com", "password": "password123"},
    ).json()["access_token"]

    response = client.post(
        f"/api/geocode-cache/{saved_entry.id}/recheck",
        headers={"Authorization": f"Bearer {intruder}"},
    )
    assert response.status_code == 404


def test_recheck_requires_authentication(client, saved_entry):
    assert client.post(f"/api/geocode-cache/{saved_entry.id}/recheck").status_code == 401
