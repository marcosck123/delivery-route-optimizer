"""Add the optional starting point to ``routes``.

Idempotent, same shape as 001: safe to run any number of times, on Postgres
(production) and SQLite (local).

Run from ``services/api``:

    python -m migrations.002_route_start_point

In production it runs by itself, through the ``release_command`` in fly.toml.
"""

import logging
import sys

from sqlalchemy import inspect, text

from app.database import engine
from app.models import Base

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migration")

TABLE = "routes"

# column name -> DDL type (portable between SQLite and Postgres)
NEW_COLUMNS = {
    "start_latitude": "FLOAT",
    "start_longitude": "FLOAT",
    "start_address": "VARCHAR(500)",
}


def existing_columns(connection, table: str) -> set[str]:
    return {column["name"] for column in inspect(connection).get_columns(table)}


def add_missing_columns(connection) -> int:
    present = existing_columns(connection, TABLE)
    added = 0

    for name, ddl_type in NEW_COLUMNS.items():
        if name in present:
            logger.info("  = %s already exists", name)
            continue
        connection.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {ddl_type}"))
        logger.info("  + %s added", name)
        added += 1

    return added


def run() -> None:
    logger.info("Migration 002_route_start_point — %s", engine.url.render_as_string())

    inspector = inspect(engine)
    if TABLE not in inspector.get_table_names():
        logger.info("Table %s does not exist yet; creating the whole schema.", TABLE)
        Base.metadata.create_all(bind=engine)
        logger.info("Done.")
        return

    with engine.begin() as connection:
        logger.info("Columns:")
        added = add_missing_columns(connection)

    logger.info("Migration finished (%s new columns).", added)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # pragma: no cover - surfaced to the operator
        logger.error("Migration failed: %s", exc)
        sys.exit(1)
