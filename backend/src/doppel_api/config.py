from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPEL_", extra="ignore")

    database_url: str = "postgresql+asyncpg://doppel:doppel@localhost:5432/doppel"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:4566"
    s3_bucket: str = "doppel-media"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"

    # Managed providers - raw env names (no DOPPEL_ prefix), so use validation_alias.
    anthropic_api_key: str = Field(default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY"))
    anthropic_model: str = Field(
        default="claude-sonnet-4-6", validation_alias=AliasChoices("ANTHROPIC_MODEL")
    )
    elevenlabs_api_key: str = Field(default="", validation_alias=AliasChoices("ELEVENLABS_API_KEY"))
    elevenlabs_model: str = Field(
        default="eleven_multilingual_v2", validation_alias=AliasChoices("ELEVENLABS_MODEL")
    )
    fal_key: str = Field(default="", validation_alias=AliasChoices("FAL_KEY"))
    fal_lipsync_model: str = Field(
        default="veed/fabric-1.0", validation_alias=AliasChoices("FAL_LIPSYNC_MODEL")
    )
    fal_broll_model: str = Field(
        default="fal-ai/kling-video/v2.1/standard/image-to-video",
        validation_alias=AliasChoices("FAL_BROLL_MODEL"),
    )
    fal_t2i_model: str = Field(
        default="fal-ai/flux/schnell", validation_alias=AliasChoices("FAL_T2I_MODEL")
    )
    caption_font: str = Field(default="DejaVu Sans", validation_alias=AliasChoices("CAPTION_FONT"))
    pipeline_concurrency: int = Field(
        default=4, validation_alias=AliasChoices("PIPELINE_CONCURRENCY")
    )

    @field_validator("s3_endpoint", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
