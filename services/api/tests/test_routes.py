import io


def create_route(client, auth_headers, deliveries, name="Rota 1"):
    response = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={"name": name, "deliveries": deliveries},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_route(client, auth_headers, sample_deliveries):
    data = create_route(client, auth_headers, sample_deliveries[:2])
    assert data["name"] == "Rota 1"
    assert len(data["deliveries"]) == 2
    assert data["optimization_result"] is None


def test_create_route_rejects_invalid_coordinates(client, auth_headers):
    response = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={
            "name": "Inválida",
            "deliveries": [{"address": "X", "latitude": 200, "longitude": 0}],
        },
    )
    assert response.status_code == 422


def test_list_routes(client, auth_headers, sample_deliveries):
    create_route(client, auth_headers, sample_deliveries, name="Segunda de Manhã")

    response = client.get("/api/routes/", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Segunda de Manhã"
    assert body[0]["delivery_count"] == 3


def test_get_route(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.get(f"/api/routes/{route['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["id"] == route["id"]


def test_route_is_scoped_to_owner(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    other = client.post(
        "/api/auth/register",
        json={"email": "outro@example.com", "password": "password123"},
    ).json()["access_token"]

    response = client.get(
        f"/api/routes/{route['id']}", headers={"Authorization": f"Bearer {other}"}
    )
    assert response.status_code == 404


def test_delete_route(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    assert client.delete(f"/api/routes/{route['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/routes/{route['id']}", headers=auth_headers).status_code == 404


def test_optimize_route(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)
    assert response.status_code == 200

    body = response.json()
    result = body["optimization_result"]
    assert result is not None
    assert len(result["optimized_order"]) == 3
    assert result["estimated_distance_km"] > 0
    assert result["osrm"]["routes"][0]["distance"] == 4321.0

    orders = sorted(d["sequence_order"] for d in body["deliveries"])
    assert orders == [0, 1, 2]


def test_optimize_empty_route(client, auth_headers):
    route = create_route(client, auth_headers, [], name="Vazia")
    response = client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)
    assert response.status_code == 400


def test_optimize_missing_route(client, auth_headers):
    response = client.post("/api/routes/9999/optimize", headers=auth_headers)
    assert response.status_code == 404


def test_upload_csv(client, auth_headers):
    route = create_route(client, auth_headers, [], name="Via CSV")

    csv_content = (
        "address,latitude,longitude\n"
        "Rua A 10,-12.7406,-60.1458\n"
        "Rua B 20,-12.7452,-60.1391\n"
    )
    response = client.post(
        f"/api/routes/{route['id']}/upload-csv",
        headers=auth_headers,
        files={"file": ("entregas.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["added"] == 2

    route_data = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()
    assert len(route_data["deliveries"]) == 2


def test_upload_csv_missing_columns(client, auth_headers):
    route = create_route(client, auth_headers, [], name="CSV ruim")

    response = client.post(
        f"/api/routes/{route['id']}/upload-csv",
        headers=auth_headers,
        files={"file": ("ruim.csv", io.BytesIO(b"endereco,lat\nRua A,1\n"), "text/csv")},
    )
    assert response.status_code == 400
    assert "colunas obrigatórias" in response.json()["detail"]


def test_upload_csv_invalid_coordinates(client, auth_headers):
    route = create_route(client, auth_headers, [], name="CSV coords")

    csv_content = "address,latitude,longitude\nRua A,abc,-60.14\n"
    response = client.post(
        f"/api/routes/{route['id']}/upload-csv",
        headers=auth_headers,
        files={"file": ("ruim.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 400
    assert "Linha 2" in response.json()["detail"]
