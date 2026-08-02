import os
import uuid
from pathlib import Path

import pytest

# Precisa ser definido ANTES de importar app.database, que lê a config no import.
TEST_DB = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["SECRET_KEY"] = "chave-de-teste-com-mais-de-32-bytes-para-hs256"
os.environ["BCRYPT_ROUNDS"] = "4"  # a suíte não precisa do custo de produção

from fastapi.testclient import TestClient  # noqa: E402

from app.database import create_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.utils import optimization  # noqa: E402

FAKE_OSRM_RESPONSE = {
    "code": "Ok",
    "routes": [
        {
            "distance": 4321.0,
            "duration": 600.0,
            "geometry": {"type": "LineString", "coordinates": []},
        }
    ],
    "waypoints": [],
}


@pytest.fixture(autouse=True)
def fresh_database():
    """Banco limpo a cada teste."""
    Base.metadata.drop_all(bind=engine)
    create_tables()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def no_network_osrm(monkeypatch):
    """Nenhum teste bate no servidor público do OSRM."""

    async def _fake_get_osrm_route(coordinates, client=None):
        if len(coordinates) < 2:
            return {"waypoints": [], "routes": []}
        return FAKE_OSRM_RESPONSE

    monkeypatch.setattr(optimization, "get_osrm_route", _fake_get_osrm_route)
    monkeypatch.setattr(
        "app.routes.routes.get_osrm_route", _fake_get_osrm_route
    )


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    """Registra um usuário novo e devolve o header Authorization."""
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/auth/register", json={"email": email, "password": "password123"}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_deliveries():
    return [
        {"address": "Rua A, 10", "latitude": -12.7406, "longitude": -60.1458},
        {"address": "Rua B, 20", "latitude": -12.7452, "longitude": -60.1391},
        {"address": "Rua C, 30", "latitude": -12.7377, "longitude": -60.1503},
    ]


def pytest_sessionfinish(session, exitstatus):
    if TEST_DB.exists():
        TEST_DB.unlink()
