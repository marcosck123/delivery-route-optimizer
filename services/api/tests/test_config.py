import pytest
from sqlalchemy import create_engine

from app.config import Settings


@pytest.mark.parametrize(
    "raw,expected",
    [
        # formato gravado pelo `fly postgres attach`
        (
            "postgres://user:senha@app-db.internal:5432/optimizer",
            "postgresql://user:senha@app-db.internal:5432/optimizer",
        ),
        (
            "postgresql://user:senha@localhost:5432/optimizer",
            "postgresql://user:senha@localhost:5432/optimizer",
        ),
        ("sqlite:///./delivery.db", "sqlite:///./delivery.db"),
    ],
)
def test_normalize_database_url(raw, expected):
    assert Settings(database_url=raw).database_url == expected


def test_normalized_url_is_loadable_by_sqlalchemy():
    """Sem a normalização o SQLAlchemy 2.0 estoura NoSuchModuleError no boot."""
    settings = Settings(database_url="postgres://user:senha@host:5432/db")
    engine = create_engine(settings.database_url)
    assert engine.dialect.name == "postgresql"


def test_cors_origin_list():
    settings = Settings(cors_origins="https://app.vercel.app, http://localhost:3000")
    assert settings.cors_origin_list == [
        "https://app.vercel.app",
        "http://localhost:3000",
    ]


def test_cors_origin_list_wildcard():
    assert Settings(cors_origins="*").cors_origin_list == ["*"]
