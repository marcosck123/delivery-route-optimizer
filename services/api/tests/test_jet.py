import base64
import hashlib

import pytest

from app.utils.jet_integration import build_signature, get_jet_orders


def test_build_signature():
    expected = base64.b64encode(hashlib.md5(b'{"a":1}chave').digest()).decode()
    assert build_signature('{"a":1}', "chave") == expected


async def test_get_jet_orders_sandbox_mode():
    orders = await get_jet_orders("usuario", "chave")
    assert len(orders) >= 1
    for order in orders:
        assert {"orderid", "address", "latitude", "longitude"} <= set(order)


def test_jet_config_requires_auth(client):
    assert client.get("/api/jet-config/").status_code == 401


def test_jet_config_not_configured(client, auth_headers):
    assert client.get("/api/jet-config/", headers=auth_headers).status_code == 404


def test_upsert_jet_config(client, auth_headers):
    response = client.put(
        "/api/jet-config/",
        headers=auth_headers,
        json={"jet_username": "entregadora", "jet_api_key": "chave-secreta"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["jet_username"] == "entregadora"
    # a chave nunca volta na resposta
    assert "jet_api_key" not in body

    updated = client.put(
        "/api/jet-config/",
        headers=auth_headers,
        json={"jet_username": "entregadora2", "jet_api_key": "outra"},
    )
    assert updated.json()["jet_username"] == "entregadora2"
    assert updated.json()["id"] == body["id"]


def test_delete_jet_config(client, auth_headers):
    client.put(
        "/api/jet-config/",
        headers=auth_headers,
        json={"jet_username": "entregadora", "jet_api_key": "chave"},
    )
    assert client.delete("/api/jet-config/", headers=auth_headers).status_code == 204
    assert client.get("/api/jet-config/", headers=auth_headers).status_code == 404


def test_sync_jet_without_credentials(client, auth_headers):
    route = client.post(
        "/api/routes/", headers=auth_headers, json={"name": "J&T", "deliveries": []}
    ).json()

    response = client.post(
        f"/api/routes/{route['id']}/sync-jet", headers=auth_headers
    )
    assert response.status_code == 400
    assert "J&T" in response.json()["detail"]


def test_sync_jet_replaces_deliveries(client, auth_headers, sample_deliveries):
    route = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": "J&T", "deliveries": sample_deliveries},
    ).json()

    client.put(
        "/api/jet-config/",
        headers=auth_headers,
        json={"jet_username": "entregadora", "jet_api_key": "chave"},
    )

    response = client.post(f"/api/routes/{route['id']}/sync-jet", headers=auth_headers)
    assert response.status_code == 200

    deliveries = response.json()["deliveries"]
    assert all(d["jet_order_id"] for d in deliveries)
    assert all("Rua A, 10" != d["address"] for d in deliveries)
