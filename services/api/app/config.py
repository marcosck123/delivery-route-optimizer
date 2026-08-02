"""Configuração da aplicação, carregada de variáveis de ambiente / .env."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLite para o MVP local, Postgres em produção
    database_url: str = "sqlite:///./delivery.db"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        """`fly postgres attach` grava a URL como `postgres://`, esquema que o
        SQLAlchemy 2.0 não reconhece. Normaliza para `postgresql://`."""
        if value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://") :]
        return value

    secret_key: str = "chave-secreta-de-desenvolvimento-troque-em-producao"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 7 * 24 * 60  # 7 dias

    # Custo do bcrypt: 12 em produção, valor baixo nos testes para não travar a suíte
    bcrypt_rounds: int = 12

    # Servidor OSRM público (grátis, com rate limit). Trocar por instância
    # própria se o volume crescer.
    osrm_base_url: str = "https://router.project-osrm.org"
    osrm_timeout_seconds: float = 10.0

    # Origens liberadas no CORS, separadas por vírgula ("*" libera todas)
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
