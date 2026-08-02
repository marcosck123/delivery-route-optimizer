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
        json={"address": "Rua Nova, 99", "latitude": -12.74, "longitude": -60.14},
    )
    assert response.status_code == 201
    assert response.json()["address"] == "Rua Nova, 99"

    route_data = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert len(route_data["deliveries"]) == 2


def test_add_delivery_invalidates_optimization(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)

    client.post(
        f"/api/routes/{route['id']}/deliveries/",
        headers=auth_headers,
        json={"address": "Rua Nova, 99", "latitude": -12.74, "longitude": -60.14},
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
