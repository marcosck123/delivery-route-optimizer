"""Give the geocode cache an owner.

The cache was global: one person's manual correction would move everyone
else's deliveries. Entries now belong to a user.

Two things have to change together:

* the new ``user_id`` (and ``address`` for display);
* the UNIQUE on ``address_key`` alone, which would forbid two users from ever
  saving the same address. It is replaced by UNIQUE (user_id, address_key).

Rows created before this migration keep ``user_id`` NULL on purpose: they are
treated as shared, readable by everyone. Assigning them to an arbitrary user
would hide good data from the others.

Idempotent. Run from ``services/api``:

    python -m migrations.003_geocode_cache_user
"""

import logging
import sys

from sqlalchemy import inspect, text

from app.database import engine
from app.models import Base

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migration")

TABLE = "geocode_cache"

NEW_COLUMNS = {
    "user_id": "INTEGER",
    "address": "VARCHAR(500)",
}

COMPOSITE_UNIQUE = "uq_geocode_cache_user_address"


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


def fix_unique_constraints(connection) -> None:
    """Swap UNIQUE(address_key) for UNIQUE(user_id, address_key).

    SQLite cannot drop a constraint; local databases are disposable and are
    created from the model, which already has the composite one.
    """
    dialect = connection.dialect.name
    if dialect != "postgresql":
        logger.info(
            "  = %s: constraints left as is (created from the model)", dialect
        )
        return

    # Drop whatever single-column unique exists on address_key.
    stale = connection.execute(
        text(
            """
            SELECT con.conname
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_attribute att ON att.attrelid = rel.oid
                                 AND att.attnum = ANY(con.conkey)
            WHERE rel.relname = :table
              AND con.contype = 'u'
              AND array_length(con.conkey, 1) = 1
              AND att.attname = 'address_key'
            """
        ),
        {"table": TABLE},
    ).fetchall()

    for (name,) in stale:
        connection.execute(text(f'ALTER TABLE {TABLE} DROP CONSTRAINT "{name}"'))
        logger.info("  - unique %s dropped (address_key alone)", name)

    already = connection.execute(
        text(
            "SELECT 1 FROM pg_constraint WHERE conname = :name"
        ),
        {"name": COMPOSITE_UNIQUE},
    ).scalar()

    if already:
        logger.info("  = %s already exists", COMPOSITE_UNIQUE)
        return

    connection.execute(
        text(
            f"ALTER TABLE {TABLE} ADD CONSTRAINT {COMPOSITE_UNIQUE} "
            "UNIQUE (user_id, address_key)"
        )
    )
    logger.info("  + %s added", COMPOSITE_UNIQUE)


def run() -> None:
    logger.info("Migration 003_geocode_cache_user — %s", engine.url.render_as_string())

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
        fix_unique_constraints(connection)

    logger.info("Migration finished (%s new columns).", added)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # pragma: no cover - surfaced to the operator
        logger.error("Migration failed: %s", exc)
        sys.exit(1)
