"""Add address components + geocoding state to ``deliveries``; create the cache.

Idempotent: safe to run any number of times, on Postgres (production) and
SQLite (local). ``create_all`` never alters existing tables, so this script is
what brings a database that already has data up to the new schema.

Run from ``services/api``:

    python -m migrations.001_address_fields

In production (Fly.io):

    fly ssh console -a delivery-route-optimizer-api -C "python -m migrations.001_address_fields"
"""

import logging
import sys

from sqlalchemy import inspect, text

from app.database import engine
from app.models import Base, GeocodeCache

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migration")

TABLE = "deliveries"

# column name -> DDL type (portable between SQLite and Postgres)
NEW_COLUMNS = {
    "street": "VARCHAR(255)",
    "number": "VARCHAR(50)",
    "neighborhood": "VARCHAR(255)",
    "cep": "VARCHAR(20)",
    "complement": "VARCHAR(255)",
    "geocode_status": "VARCHAR(30) DEFAULT 'pending'",
    "geocode_source": "VARCHAR(20)",
    "geocode_message": "VARCHAR(255)",
    "geocode_alternatives": "JSON",
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


def drop_coordinate_not_null(connection) -> None:
    """Coordinates are filled in only after geocoding, so they must be nullable.

    SQLite cannot ALTER a column; local databases are disposable, so we just
    report it there.
    """
    dialect = connection.dialect.name
    if dialect != "postgresql":
        logger.info("  = %s: NOT NULL on lat/lon left as is (dialect limitation)", dialect)
        return

    for column in ("latitude", "longitude"):
        connection.execute(
            text(f"ALTER TABLE {TABLE} ALTER COLUMN {column} DROP NOT NULL")
        )
        logger.info("  ~ %s is now nullable", column)


def backfill_geocode_status(connection) -> int:
    """Rows that already had coordinates are trustworthy: mark them resolved."""
    result = connection.execute(
        text(
            f"UPDATE {TABLE} SET geocode_status = 'resolved' "
            "WHERE (geocode_status IS NULL OR geocode_status = 'pending') "
            "AND latitude IS NOT NULL AND longitude IS NOT NULL"
        )
    )
    return result.rowcount or 0


def run() -> None:
    logger.info("Migration 001_address_fields — %s", engine.url.render_as_string())

    inspector = inspect(engine)
    if TABLE not in inspector.get_table_names():
        logger.info("Table %s does not exist yet; creating the whole schema.", TABLE)
        Base.metadata.create_all(bind=engine)
        logger.info("Done.")
        return

    with engine.begin() as connection:
        logger.info("Columns:")
        added = add_missing_columns(connection)

        logger.info("Constraints:")
        drop_coordinate_not_null(connection)

        logger.info("Backfill:")
        updated = backfill_geocode_status(connection)
        logger.info("  ~ %s existing deliveries marked as resolved", updated)

    logger.info("Cache table:")
    GeocodeCache.__table__.create(bind=engine, checkfirst=True)
    logger.info("  = geocode_cache ready")

    logger.info("Migration finished (%s new columns).", added)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # pragma: no cover - surfaced to the operator
        logger.error("Migration failed: %s", exc)
        sys.exit(1)
