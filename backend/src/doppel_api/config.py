from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPEL_", extra="ignore")

    database_url: str = "postgresql+asyncpg://doppel:doppel@localhost:5432/doppel"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:4566"
    s3_public_endpoint: str | None = "http://localhost:4566"
    s3_bucket: str = "doppel-media"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Managed providers - raw env names (no DOPPEL_ prefix), so use validation_alias.
    anthropic_api_key: str = Field(default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY"))
    anthropic_model: str = Field(
        default="claude-sonnet-4-6", validation_alias=AliasChoices("ANTHROPIC_MODEL")
    )
    elevenlabs_api_key: str = Field(default="", validation_alias=AliasChoices("ELEVENLABS_API_KEY"))
    elevenlabs_model: str = Field(
        default="eleven_multilingual_v2", validation_alias=AliasChoices("ELEVENLABS_MODEL")
    )
    inference_api_key: str = Field(
        default="", validation_alias=AliasChoices("INFERENCE_API_KEY")
    )
    avatar_api_base: str = Field(
        default=(
            "http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com"
            "/latentsync"
        ),
        validation_alias=AliasChoices("AVATAR_API_BASE"),
    )
    broll_api_base: str = Field(
        default=(
            "http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com"
            "/cosmos3"
        ),
        validation_alias=AliasChoices("BROLL_API_BASE"),
    )
    broll_fast_steps: int = Field(default=30, validation_alias=AliasChoices("BROLL_FAST_STEPS"))
    broll_fast_fps: float = Field(default=24.0, validation_alias=AliasChoices("BROLL_FAST_FPS"))
    broll_fast_size: str = Field(default="480x832", validation_alias=AliasChoices("BROLL_FAST_SIZE"))
    avatar_guidance_scale: float = Field(
        default=1.5, validation_alias=AliasChoices("AVATAR_GUIDANCE_SCALE")
    )
    avatar_inference_steps: int = Field(
        default=20, validation_alias=AliasChoices("AVATAR_INFERENCE_STEPS")
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
