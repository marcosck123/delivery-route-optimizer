"""Geocoding tests — the real Google API is never called."""

import httpx
import pytest

from app.database import SessionLocal
from app.models import GEOCODE_FAILED, GEOCODE_NEEDS_CONFIRMATION, GEOCODE_RESOLVED
from app.utils import geocoding
from app.utils.geocoding import Messages, geocode_address, resolve_address

VILHENA = (-12.7406, -60.1458)


def google_payload(lat, lng, location_type="ROOFTOP", partial_match=False):
    return {
        "status": "OK",
        "results": [
            {
                "geometry": {
                    "location": {"lat": lat, "lng": lng},
                    "location_type": location_type,
                },
                "partial_match": partial_match,
            }
        ],
    }


ZERO_RESULTS = {"status": "ZERO_RESULTS", "results": []}


class FakeGoogle:
    """Records every query and replies with queued payloads."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.queries: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.queries.append(request.url.params.get("address", ""))
        payload = (
            self.responses.pop(0) if self.responses else {"status": "ZERO_RESULTS", "results": []}
        )
        return httpx.Response(200, json=payload)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def test_returns_failed_without_api_key():
    result = await geocode_address("Rua A", "10", "Centro")
    assert result.status == GEOCODE_FAILED
    assert result.message == Messages.NOT_CONFIGURED
    assert result.latitude is None


async def test_rooftop_result_is_resolved(google_key):
    google = FakeGoogle([google_payload(*VILHENA)])
    async with google.client() as client:
        result = await geocode_address("Rua A", "10", "Centro", client=client)

    assert result.status == GEOCODE_RESOLVED
    assert result.source == "google"
    assert (result.latitude, result.longitude) == VILHENA
    assert "Vilhena" in google.queries[0] and "RO" in google.queries[0]


async def test_partial_match_needs_confirmation(google_key):
    google = FakeGoogle([google_payload(*VILHENA, partial_match=True)])
    async with google.client() as client:
        result = await geocode_address("Rua A", "10", "Centro", client=client)

    assert result.status == GEOCODE_NEEDS_CONFIRMATION
    assert result.message == Messages.APPROXIMATE
    assert result.latitude == VILHENA[0]  # ainda mostra o palpite no mapa


async def test_approximate_location_type_needs_confirmation(google_key):
    google = FakeGoogle([google_payload(*VILHENA, location_type="APPROXIMATE")])
    async with google.client() as client:
        result = await geocode_address("Rua A", "10", "Centro", client=client)

    assert result.status == GEOCODE_NEEDS_CONFIRMATION


async def test_zero_results_with_cep_retries_without_cep(google_key):
    # 1ª com CEP -> ZERO_RESULTS; 2ª sem CEP -> encontra
    google = FakeGoogle([ZERO_RESULTS, google_payload(*VILHENA)])
    async with google.client() as client:
        result = await geocode_address(
            "Rua A", "10", "Centro", cep="99999-999", client=client
        )

    assert len(google.queries) == 2
    assert "CEP 99999-999" in google.queries[0]
    assert "CEP" not in google.queries[1]
    assert result.status == GEOCODE_RESOLVED


async def test_bad_cep_message_when_retry_also_fails(google_key):
    google = FakeGoogle([ZERO_RESULTS, ZERO_RESULTS])
    async with google.client() as client:
        result = await geocode_address(
            "Rua A", "10", "Centro", cep="99999-999", client=client
        )

    assert result.status == GEOCODE_FAILED
    assert result.message == Messages.BAD_CEP


async def test_street_not_found_when_neighborhood_exists(google_key):
    # endereço falha, mas o bairro sozinho geocoda -> a rua é o problema
    google = FakeGoogle([ZERO_RESULTS, google_payload(*VILHENA)])
    async with google.client() as client:
        result = await geocode_address("Rua Inexistente", "10", "Centro", client=client)

    assert result.status == GEOCODE_FAILED
    assert result.message == Messages.STREET_NOT_FOUND


async def test_neighborhood_not_found(google_key):
    google = FakeGoogle([ZERO_RESULTS, ZERO_RESULTS])
    async with google.client() as client:
        result = await geocode_address("Rua A", "10", "Bairro Fantasma", client=client)

    assert result.status == GEOCODE_FAILED
    assert result.message == Messages.NEIGHBORHOOD_NOT_FOUND


async def test_over_query_limit_gives_generic_message(google_key):
    google = FakeGoogle([{"status": "OVER_QUERY_LIMIT", "results": []}])
    async with google.client() as client:
        result = await geocode_address("Rua A", "10", "Centro", client=client)

    assert result.status == GEOCODE_FAILED
    assert result.message == Messages.UNAVAILABLE
    # nada técnico vaza para a UI
    assert "QUERY" not in (result.message or "")


# ------------------------------------------------------- cross-check


async def test_cross_check_agreeing_results_are_resolved(google_key):
    # extenso e dígito apontam para pontos a ~20 m -> concordam
    google = FakeGoogle(
        [
            google_payload(-12.7406, -60.1458, location_type="GEOMETRIC_CENTER"),
            google_payload(-12.74078, -60.1458),  # ~20 m ao sul, ROOFTOP
        ]
    )
    async with google.client() as client:
        result = await geocode_address(
            "Rua três mil e quinhentos", "10", "Centro", client=client
        )

    assert len(google.queries) == 2
    assert "Rua 3500" in google.queries[1]
    assert result.status == GEOCODE_RESOLVED
    # fica com o ponto mais preciso (ROOFTOP vence GEOMETRIC_CENTER)
    assert result.latitude == -12.74078


async def test_cross_check_divergent_results_need_confirmation(google_key):
    # ~1,2 km de distância -> divergem
    google = FakeGoogle(
        [google_payload(-12.7406, -60.1458), google_payload(-12.7510, -60.1458)]
    )
    async with google.client() as client:
        result = await geocode_address(
            "Rua três mil e quinhentos", "10", "Centro", client=client
        )

    assert result.status == GEOCODE_NEEDS_CONFIRMATION
    assert result.message == Messages.DIVERGENT
    assert len(result.alternatives) == 2
    assert result.alternatives[0]["latitude"] == -12.7406
    assert result.alternatives[1]["latitude"] == -12.7510


async def test_no_cross_check_when_street_has_no_spelled_out_number(google_key):
    google = FakeGoogle([google_payload(*VILHENA)])
    async with google.client() as client:
        await geocode_address("Avenida Major Amarante", "1000", "Centro", client=client)

    assert len(google.queries) == 1


# ------------------------------------------------------------- cache


async def test_cache_hit_does_not_call_google(db, google_key):
    google = FakeGoogle([google_payload(*VILHENA)])
    async with google.client() as client:
        first = await resolve_address(db, "Rua A", "10", "Centro", client=client)
        db.commit()
        second = await resolve_address(db, "Rua A", "10", "Centro", client=client)

    assert len(google.queries) == 1  # a segunda veio do cache
    assert first.source == "google"
    assert second.source == "cache"
    assert second.status == GEOCODE_RESOLVED
    assert (second.latitude, second.longitude) == VILHENA


async def test_cache_key_ignores_case_and_accents(db, google_key):
    google = FakeGoogle([google_payload(*VILHENA)])
    async with google.client() as client:
        await resolve_address(db, "Rua Osório", "10", "Centro", client=client)
        db.commit()
        calls_before = len(google.queries)
        cached = await resolve_address(db, "  rua osorio ", "10", "centro", client=client)

    assert len(google.queries) == calls_before  # nenhuma chamada nova
    assert cached.source == "cache"


async def test_failed_geocode_is_not_cached(db, google_key):
    google = FakeGoogle([ZERO_RESULTS, ZERO_RESULTS, ZERO_RESULTS, ZERO_RESULTS])
    async with google.client() as client:
        await resolve_address(db, "Rua A", "10", "Centro", client=client)
        db.commit()
        queries_after_first = len(google.queries)
        await resolve_address(db, "Rua A", "10", "Centro", client=client)

    assert len(google.queries) > queries_after_first  # tentou de novo


def test_manual_entry_overwrites_google_in_cache(db):
    geocoding.save_to_cache(db, "Rua A", "10", "Centro", -12.0, -60.0, source="google")
    db.commit()
    geocoding.save_to_cache(db, "Rua A", "10", "Centro", -12.5, -60.5, source="manual")
    db.commit()

    entry = geocoding.lookup_cache(db, "Rua A", "10", "Centro")
    assert (entry.latitude, entry.longitude, entry.source) == (-12.5, -60.5, "manual")


def test_google_never_downgrades_a_manual_entry(db):
    geocoding.save_to_cache(db, "Rua A", "10", "Centro", -12.5, -60.5, source="manual")
    db.commit()
    geocoding.save_to_cache(db, "Rua A", "10", "Centro", -12.0, -60.0, source="google")
    db.commit()

    entry = geocoding.lookup_cache(db, "Rua A", "10", "Centro")
    assert (entry.latitude, entry.source) == (-12.5, "manual")


async def test_manual_cache_hit_comes_back_as_confirmed(db, google_key):
    geocoding.save_to_cache(db, "Rua A", "10", "Centro", -12.5, -60.5, source="manual")
    db.commit()

    result = await resolve_address(db, "Rua A", "10", "Centro")
    assert result.status == "confirmed"
    assert result.source == "cache"
