from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPEL_")

    database_url: str = "postgresql+asyncpg://doppel:doppel@localhost:5432/doppel"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:4566"
    s3_bucket: str = "doppel-media"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"

    @field_validator("s3_endpoint", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
