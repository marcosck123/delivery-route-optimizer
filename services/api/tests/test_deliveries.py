def create_route(client, auth_headers, deliveries, name="Rota"):
    response = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": name, "deliveries": deliveries},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_list_deliveries(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.get(
        f"/api/routes/{route['id']}/deliveries/", headers=auth_headers
    )
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_add_delivery(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries[:1])

    response = client.post(
        f"/api/routes/{route['id']}/deliveries/",
        headers=auth_headers,
        json={"street": "Rua Nova", "number": "99", "neighborhood": "Centro"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["address"] == "Rua Nova, 99 - Centro"
    assert body["geocode_status"] == "pending"

    route_data = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert len(route_data["deliveries"]) == 2


def test_add_delivery_invalidates_optimization(
    client, auth_headers, sample_deliveries, confirm_all
):
    route = create_route(client, auth_headers, sample_deliveries)
    confirm_all(route["id"])
    client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)

    client.post(
        f"/api/routes/{route['id']}/deliveries/",
        headers=auth_headers,
        json={"street": "Rua Nova", "number": "99", "neighborhood": "Centro"},
    )

    route_data = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert route_data["optimization_result"] is None


def test_delete_delivery(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    delivery_id = route["deliveries"][0]["id"]

    response = client.delete(
        f"/api/routes/{route['id']}/deliveries/{delivery_id}", headers=auth_headers
    )
    assert response.status_code == 204

    route_data = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert len(route_data["deliveries"]) == 2


def test_delete_unknown_delivery(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.delete(
        f"/api/routes/{route['id']}/deliveries/9999", headers=auth_headers
    )
    assert response.status_code == 404


def test_reorder_deliveries(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    ids = [d["id"] for d in route["deliveries"]]
    reversed_ids = list(reversed(ids))

    response = client.put(
        f"/api/routes/{route['id']}/deliveries/order",
        headers=auth_headers,
        json=reversed_ids,
    )
    assert response.status_code == 200
    assert [d["id"] for d in response.json()] == reversed_ids
    assert [d["sequence_order"] for d in response.json()] == [0, 1, 2]


def test_reorder_rejects_incomplete_list(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    ids = [d["id"] for d in route["deliveries"]]

    response = client.put(
        f"/api/routes/{route['id']}/deliveries/order",
        headers=auth_headers,
        json=ids[:2],
    )
    assert response.status_code == 400


# -------------------------------------------------------- confirm-pin


def confirm(client, auth_headers, route_id, delivery_id, lat=-12.75, lon=-60.15):
    return client.post(
        f"/api/routes/{route_id}/deliveries/{delivery_id}/confirm-pin",
        headers=auth_headers,
        json={"delivery_id": delivery_id, "latitude": lat, "longitude": lon},
    )


def test_confirm_pin_saves_manual_coordinates(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries[:1])
    delivery_id = route["deliveries"][0]["id"]

    response = confirm(client, auth_headers, route["id"], delivery_id)
    assert response.status_code == 200

    body = response.json()
    assert body["latitude"] == -12.75
    assert body["longitude"] == -60.15
    assert body["geocode_status"] == "confirmed"
    assert body["geocode_source"] == "manual"
    assert body["geocode_message"] is None


def test_confirm_pin_feeds_the_cache(client, auth_headers, sample_deliveries):
    """O mesmo endereço numa rota nova já nasce confirmado, sem chamar o Google."""
    route = create_route(client, auth_headers, sample_deliveries[:1])
    confirm(client, auth_headers, route["id"], route["deliveries"][0]["id"])

    other_route = create_route(
        client, auth_headers, sample_deliveries[:1], name="Outra rota"
    )
    geocoded = client.post(
        f"/api/routes/{other_route['id']}/geocode", headers=auth_headers
    ).json()

    assert geocoded[0]["geocode_status"] == "confirmed"
    assert geocoded[0]["geocode_source"] == "cache"
    assert geocoded[0]["latitude"] == -12.75


def test_confirm_pin_rejects_mismatched_body(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries[:1])
    delivery_id = route["deliveries"][0]["id"]

    response = client.post(
        f"/api/routes/{route['id']}/deliveries/{delivery_id}/confirm-pin",
        headers=auth_headers,
        json={"delivery_id": delivery_id + 999, "latitude": -12.7, "longitude": -60.1},
    )
    assert response.status_code == 400


def test_confirm_pin_rejects_invalid_coordinates(
    client, auth_headers, sample_deliveries
):
    route = create_route(client, auth_headers, sample_deliveries[:1])
    delivery_id = route["deliveries"][0]["id"]

    response = confirm(client, auth_headers, route["id"], delivery_id, lat=200)
    assert response.status_code == 422


def test_confirm_pin_unknown_delivery(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries[:1])

    response = confirm(client, auth_headers, route["id"], 9999)
    assert response.status_code == 404


def test_confirm_pin_is_scoped_to_owner(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries[:1])
    delivery_id = route["deliveries"][0]["id"]

    other = client.post(
        "/api/auth/register",
        json={"email": "invasor@example.com", "password": "password123"},
    ).json()["access_token"]

    response = client.post(
        f"/api/routes/{route['id']}/deliveries/{delivery_id}/confirm-pin",
        headers={"Authorization": f"Bearer {other}"},
        json={"delivery_id": delivery_id, "latitude": -12.7, "longitude": -60.1},
    )
    assert response.status_code == 404
