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


def test_create_route_starts_pending_without_coordinates(
    client, auth_headers, sample_deliveries
):
    data = create_route(client, auth_headers, sample_deliveries)

    for delivery in data["deliveries"]:
        assert delivery["geocode_status"] == "pending"
        assert delivery["latitude"] is None
        assert delivery["longitude"] is None


def test_create_route_assembles_full_address(client, auth_headers):
    data = create_route(
        client,
        auth_headers,
        [
            {
                "street": "Rua Residencial Florença Um",
                "number": "8046",
                "neighborhood": "Residencial Florença",
                "complement": "CASA",
            }
        ],
    )
    delivery = data["deliveries"][0]
    assert delivery["address"] == (
        "Rua Residencial Florença Um, 8046 - CASA - Residencial Florença"
    )
    assert delivery["street"] == "Rua Residencial Florença Um"
    assert delivery["number"] == "8046"


def test_create_route_requires_street_number_neighborhood(client, auth_headers):
    response = client.post(
        "/api/routes/",
        headers=auth_headers,
        json={
            "name": "Inválida",
            "deliveries": [{"street": "Rua A", "number": "", "neighborhood": "Centro"}],
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


# ----------------------------------------------------------- otimização


def test_optimize_route(client, auth_headers, sample_deliveries, confirm_all):
    route = create_route(client, auth_headers, sample_deliveries)
    confirm_all(route["id"])

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


def test_optimize_blocked_while_addresses_are_pending(
    client, auth_headers, sample_deliveries
):
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)
    assert response.status_code == 400

    detail = response.json()["detail"]
    assert "Confirme todos os endereços antes de otimizar" in detail
    # nomeia exatamente quais faltam
    for delivery in sample_deliveries:
        assert delivery["street"] in detail


def test_optimize_lists_only_the_missing_addresses(
    client, auth_headers, sample_deliveries, confirm_all
):
    route = create_route(client, auth_headers, sample_deliveries)
    full = client.get(f"/api/routes/{route['id']}", headers=auth_headers).json()

    # confirma só as duas primeiras
    for delivery in full["deliveries"][:2]:
        client.post(
            f"/api/routes/{route['id']}/deliveries/{delivery['id']}/confirm-pin",
            headers=auth_headers,
            json={
                "delivery_id": delivery["id"],
                "latitude": -12.74,
                "longitude": -60.14,
            },
        )

    detail = client.post(
        f"/api/routes/{route['id']}/optimize", headers=auth_headers
    ).json()["detail"]

    assert full["deliveries"][2]["street"] in detail
    assert full["deliveries"][0]["street"] not in detail


def test_optimize_empty_route(client, auth_headers):
    route = create_route(client, auth_headers, [], name="Vazia")
    response = client.post(f"/api/routes/{route['id']}/optimize", headers=auth_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Rota sem entregas"


def test_optimize_missing_route(client, auth_headers):
    response = client.post("/api/routes/9999/optimize", headers=auth_headers)
    assert response.status_code == 404


# ------------------------------------------------------------- geocode


def test_geocode_endpoint_without_key_marks_failed(
    client, auth_headers, sample_deliveries
):
    """Sem GOOGLE_MAPS_API_KEY o app continua de pé e explica o problema."""
    route = create_route(client, auth_headers, sample_deliveries)

    response = client.post(f"/api/routes/{route['id']}/geocode", headers=auth_headers)
    assert response.status_code == 200

    for delivery in response.json():
        assert delivery["geocode_status"] == "failed"
        assert delivery["geocode_message"] == "Busca de endereços não configurada"


def test_geocode_endpoint_is_scoped_to_owner(client, auth_headers, sample_deliveries):
    route = create_route(client, auth_headers, sample_deliveries)
    other = client.post(
        "/api/auth/register",
        json={"email": "intruso@example.com", "password": "password123"},
    ).json()["access_token"]

    response = client.post(
        f"/api/routes/{route['id']}/geocode",
        headers={"Authorization": f"Bearer {other}"},
    )
    assert response.status_code == 404


def test_geocode_skips_already_confirmed_deliveries(
    client, auth_headers, sample_deliveries, confirm_all
):
    route = create_route(client, auth_headers, sample_deliveries)
    confirm_all(route["id"])

    response = client.post(f"/api/routes/{route['id']}/geocode", headers=auth_headers)

    for delivery in response.json():
        assert delivery["geocode_status"] == "confirmed"
        assert delivery["latitude"] is not None


# ------------------------------------------------------------------ CSV


def test_upload_csv(client, auth_headers):
    route = create_route(client, auth_headers, [], name="Via CSV")

    csv_content = (
        "street,number,neighborhood,cep,complement\n"
        "Avenida Major Amarante,1000,Centro,76980-075,\n"
        "Rua Osório Duque Estrada,250,Jardim América,,Fundos\n"
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
    assert route_data["deliveries"][0]["neighborhood"] == "Centro"
    assert route_data["deliveries"][1]["complement"] == "Fundos"
    assert all(d["geocode_status"] == "pending" for d in route_data["deliveries"])


def test_upload_csv_missing_columns(client, auth_headers):
    route = create_route(client, auth_headers, [], name="CSV ruim")

    response = client.post(
        f"/api/routes/{route['id']}/upload-csv",
        headers=auth_headers,
        files={"file": ("ruim.csv", io.BytesIO(b"address,latitude\nRua A,1\n"), "text/csv")},
    )
    assert response.status_code == 400
    assert "colunas obrigatórias" in response.json()["detail"]


def test_upload_csv_missing_required_value(client, auth_headers):
    route = create_route(client, auth_headers, [], name="CSV incompleto")

    csv_content = "street,number,neighborhood\nRua A,,Centro\n"
    response = client.post(
        f"/api/routes/{route['id']}/upload-csv",
        headers=auth_headers,
        files={"file": ("ruim.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert response.status_code == 400
    assert "Linha 2" in response.json()["detail"]
