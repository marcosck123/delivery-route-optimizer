"""Run every migration, in order.

This is what ``release_command`` in fly.toml calls, so a deploy can never go
out with the code ahead of the schema. Every migration is idempotent, so
running the whole list on each deploy is harmless.

Add new migrations to ``MIGRATIONS`` — order matters.
"""

import importlib
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migration")

MIGRATIONS = [
    "migrations.001_address_fields",
    "migrations.002_route_start_point",
]


def run() -> None:
    for name in MIGRATIONS:
        logger.info("--- %s", name)
        importlib.import_module(name).run()


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # pragma: no cover - surfaced to the operator
        logger.error("Migrations failed: %s", exc)
        sys.exit(1)
