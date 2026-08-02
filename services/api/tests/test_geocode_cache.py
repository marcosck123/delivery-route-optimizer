"""Endereços salvos: listar, excluir e corrigir o cache de geocoding."""

import pytest

from app.database import SessionLocal
from app.models import GeocodeCache
from app.utils import geocoding


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def fake_google(monkeypatch, google_key):
    """Conta as chamadas: é assim que se prova que o cache foi usado."""
    calls: list[str] = []

    async def _call(query, client):
        calls.append(query)
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
    return calls


ADDRESS = {"street": "Rua Osório", "number": "250", "neighborhood": "Centro"}


def geocode_an_address(client, auth_headers, address=None):
    """Cria rota + endereço e geocodifica, deixando uma entrada no cache."""
    route = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "Rota", "deliveries": [address or ADDRESS]},
    ).json()
    client.post(f"/api/routes/{route['id']}/geocode", headers=auth_headers)
    return route


def other_user_headers(client, email="outra@example.com"):
    token = client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ listar


def test_list_is_empty_at_first(client, auth_headers):
    response = client.get("/api/geocode-cache/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_geocoding_an_address_saves_it(client, auth_headers, fake_google):
    geocode_an_address(client, auth_headers)

    entries = client.get("/api/geocode-cache/", headers=auth_headers).json()
    assert len(entries) == 1
    assert entries[0]["source"] == "google"
    assert entries[0]["latitude"] == -12.7300
    # texto legível, não só a chave normalizada
    assert entries[0]["address"] == "Rua Osório, 250 - Centro"
    assert entries[0]["address_key"] == "rua osorio 250 centro vilhena"


def test_list_requires_authentication(client):
    assert client.get("/api/geocode-cache/").status_code == 401


def test_entries_are_private_to_each_user(client, auth_headers, fake_google):
    geocode_an_address(client, auth_headers)

    intruder = other_user_headers(client)
    assert client.get("/api/geocode-cache/", headers=intruder).json() == []


def test_one_users_correction_does_not_move_anothers_delivery(
    client, auth_headers, fake_google
):
    """Era o risco do cache global: correção de um mexia na entrega do outro."""
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    client.patch(
        f"/api/geocode-cache/{entry['id']}",
        headers=auth_headers,
        json={"latitude": -12.99, "longitude": -60.99},
    )

    intruder = other_user_headers(client)
    route = geocode_an_address(client, intruder)
    deliveries = client.get(
        f"/api/routes/{route['id']}", headers=intruder
    ).json()["deliveries"]

    assert deliveries[0]["latitude"] == -12.7300  # o do Google, não a correção alheia


# ---------------------------------------------------------------- excluir


def test_delete_removes_the_entry(client, auth_headers, fake_google):
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    assert (
        client.delete(
            f"/api/geocode-cache/{entry['id']}", headers=auth_headers
        ).status_code
        == 204
    )
    assert client.get("/api/geocode-cache/", headers=auth_headers).json() == []


def test_deleted_address_is_looked_up_again(client, auth_headers, fake_google):
    """É esse o efeito prático de excluir: o Google é consultado de novo."""
    geocode_an_address(client, auth_headers)
    calls_after_first = len(fake_google)

    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]
    client.delete(f"/api/geocode-cache/{entry['id']}", headers=auth_headers)

    geocode_an_address(client, auth_headers)
    assert len(fake_google) > calls_after_first


def test_cached_address_does_not_call_google_again(client, auth_headers, fake_google):
    geocode_an_address(client, auth_headers)
    calls_after_first = len(fake_google)

    geocode_an_address(client, auth_headers)
    assert len(fake_google) == calls_after_first


def test_delete_of_someone_elses_entry_is_not_found(
    client, auth_headers, fake_google
):
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    intruder = other_user_headers(client)
    response = client.delete(f"/api/geocode-cache/{entry['id']}", headers=intruder)
    assert response.status_code == 404


def test_delete_unknown_entry(client, auth_headers):
    assert (
        client.delete("/api/geocode-cache/9999", headers=auth_headers).status_code
        == 404
    )


# --------------------------------------------------------------- corrigir


def test_patch_updates_the_pin_and_marks_it_manual(
    client, auth_headers, fake_google
):
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    response = client.patch(
        f"/api/geocode-cache/{entry['id']}",
        headers=auth_headers,
        json={"latitude": -12.80, "longitude": -60.20},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["latitude"] == -12.80
    assert body["longitude"] == -60.20
    assert body["source"] == "manual"


def test_corrected_address_is_used_by_the_next_route(
    client, auth_headers, fake_google
):
    """O ponto de a correção existir: a próxima rota já nasce certa."""
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    client.patch(
        f"/api/geocode-cache/{entry['id']}",
        headers=auth_headers,
        json={"latitude": -12.80, "longitude": -60.20},
    )

    route = geocode_an_address(client, auth_headers)
    delivery = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()[
        "deliveries"
    ][0]

    assert delivery["latitude"] == -12.80
    assert delivery["geocode_status"] == "confirmed"


def test_patch_rejects_invalid_coordinates(client, auth_headers, fake_google):
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    response = client.patch(
        f"/api/geocode-cache/{entry['id']}",
        headers=auth_headers,
        json={"latitude": 200, "longitude": -60.20},
    )
    assert response.status_code == 422


def test_patch_of_someone_elses_entry_is_not_found(client, auth_headers, fake_google):
    geocode_an_address(client, auth_headers)
    entry = client.get("/api/geocode-cache/", headers=auth_headers).json()[0]

    intruder = other_user_headers(client)
    response = client.patch(
        f"/api/geocode-cache/{entry['id']}",
        headers=intruder,
        json={"latitude": -12.80, "longitude": -60.20},
    )
    assert response.status_code == 404


# ------------------------------------------------- entradas antigas (sem dono)


def test_legacy_shared_entries_are_visible_and_claimable(client, auth_headers, db):
    """Entradas anteriores à posse ficam compartilhadas — e corrigíveis."""
    db.add(
        GeocodeCache(
            user_id=None,
            address_key="rua antiga 1 centro vilhena",
            address="Rua Antiga, 1 - Centro",
            latitude=-12.5,
            longitude=-60.5,
            source="google",
        )
    )
    db.commit()

    entries = client.get("/api/geocode-cache/", headers=auth_headers).json()
    assert len(entries) == 1

    corrected = client.patch(
        f"/api/geocode-cache/{entries[0]['id']}",
        headers=auth_headers,
        json={"latitude": -12.6, "longitude": -60.6},
    ).json()
    assert corrected["source"] == "manual"

    # ao corrigir, a entrada passa a ser dela — some para os outros
    intruder = other_user_headers(client)
    assert client.get("/api/geocode-cache/", headers=intruder).json() == []
