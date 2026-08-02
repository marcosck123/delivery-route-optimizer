def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register(client):
    response = client.post(
        "/api/auth/register",
        json={"email": "newuser@example.com", "password": "pass123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_register_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "pass123"}
    assert client.post("/api/auth/register", json=payload).status_code == 200

    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "Email já registrado"


def test_register_normalizes_email(client):
    client.post(
        "/api/auth/register",
        json={"email": "  MiXeD@Example.com ", "password": "pass123"},
    )
    response = client.post(
        "/api/auth/login", json={"email": "mixed@example.com", "password": "pass123"}
    )
    assert response.status_code == 200


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register", json={"email": "short@example.com", "password": "123"}
    )
    assert response.status_code == 422


def test_login(client):
    client.post(
        "/api/auth/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_wrong_password(client):
    client.post(
        "/api/auth/register",
        json={"email": "wrong@example.com", "password": "password123"},
    )
    response = client.post(
        "/api/auth/login", json={"email": "wrong@example.com", "password": "errada"}
    )
    assert response.status_code == 401


def test_me(client, auth_headers):
    response = client.get("/api/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert "@example.com" in response.json()["email"]


def test_protected_route_without_token(client):
    assert client.get("/api/routes/").status_code == 401


def test_protected_route_with_garbage_token(client):
    response = client.get(
        "/api/routes/", headers={"Authorization": "Bearer nao-e-um-jwt"}
    )
    assert response.status_code == 401
