"""As migrações rodam a cada deploy (release_command) — precisam ser idempotentes.

Cada teste monta um banco no schema ANTIGO, com dados dentro, e roda a
migração duas vezes: a segunda não pode falhar nem perder dado.
"""

import importlib
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

LEGACY_ROUTES_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY, email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL, created_at DATETIME
);
CREATE TABLE routes (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name VARCHAR(255) NOT NULL,
    optimization_result JSON, created_at DATETIME, updated_at DATETIME
);
CREATE TABLE deliveries (
    id INTEGER PRIMARY KEY, route_id INTEGER NOT NULL, address VARCHAR(500) NOT NULL,
    latitude FLOAT NOT NULL, longitude FLOAT NOT NULL,
    sequence_order INTEGER, jet_order_id VARCHAR(100)
);
INSERT INTO users VALUES (1, 'a@b.com', 'x', '2026-08-01');
INSERT INTO routes VALUES (1, 1, 'Rota antiga', NULL, '2026-08-01', '2026-08-01');
INSERT INTO deliveries VALUES (1, 1, 'Av. Major Amarante, 1000', -12.7406, -60.1458, 0, NULL);
"""


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """Banco no schema antigo, com dados, apontado pela app."""
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(LEGACY_ROUTES_SCHEMA)
    connection.commit()
    connection.close()

    engine = create_engine(f"sqlite:///{path}")
    # as migrações leem o engine do app.database no import
    import app.database

    monkeypatch.setattr(app.database, "engine", engine)
    return engine


def run_migration(module_name: str, engine):
    module = importlib.import_module(module_name)
    # o módulo importou o engine antigo por valor
    module.engine = engine
    module.run()


def columns(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def test_001_adds_address_fields_and_backfills(legacy_db):
    run_migration("migrations.001_address_fields", legacy_db)

    delivery_columns = columns(legacy_db, "deliveries")
    assert {"street", "number", "neighborhood", "geocode_status"} <= delivery_columns
    assert "geocode_cache" in inspect(legacy_db).get_table_names()

    with legacy_db.connect() as connection:
        status = connection.execute(
            text("SELECT geocode_status FROM deliveries WHERE id = 1")
        ).scalar()
    # entrega antiga já tinha coordenadas: continua otimizável
    assert status == "resolved"


def test_002_adds_the_route_start_point(legacy_db):
    run_migration("migrations.002_route_start_point", legacy_db)

    assert {"start_latitude", "start_longitude", "start_address"} <= columns(
        legacy_db, "routes"
    )


def test_migrations_are_idempotent(legacy_db):
    for _ in range(2):
        run_migration("migrations.001_address_fields", legacy_db)
        run_migration("migrations.002_route_start_point", legacy_db)

    with legacy_db.connect() as connection:
        # nenhum dado perdido no caminho
        assert connection.execute(text("SELECT COUNT(*) FROM routes")).scalar() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM deliveries")).scalar() == 1


def test_run_all_lists_every_migration():
    """Uma migração nova precisa entrar no runner, senão não roda no deploy."""
    from migrations import run_all

    assert run_all.MIGRATIONS == [
        "migrations.001_address_fields",
        "migrations.002_route_start_point",
    ]
