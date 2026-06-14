from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPEL_", extra="ignore")

    database_url: str = "postgresql+asyncpg://doppel:doppel@localhost:5432/doppel"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:4566"
    s3_public_endpoint: str | None = None  # browser-reachable endpoint for presigned URLs
    s3_bucket: str = "doppel-media"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"

    # Managed providers - raw env names (no DOPPEL_ prefix), so use validation_alias.
    anthropic_api_key: str = Field(default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY"))
    anthropic_model: str = Field(
        default="claude-sonnet-4-6", validation_alias=AliasChoices("ANTHROPIC_MODEL")
    )
    # Prompting prep (face-attribute extraction -> identity lock) wants the strongest
    # vision/reasoning model; script generation stays on the faster default above.
    anthropic_prompt_model: str = Field(
        default="claude-opus-4-7", validation_alias=AliasChoices("ANTHROPIC_PROMPT_MODEL")
    )
    # Web-search research step for the Video Agent (must support the web_search tool).
    anthropic_research_model: str = Field(
        default="claude-opus-4-8", validation_alias=AliasChoices("ANTHROPIC_RESEARCH_MODEL")
    )
    # Video Agent plan/artifact author. Sonnet generates the large structured plan
    # far faster than Opus (and without truncating), which dominates build latency.
    anthropic_planner_model: str = Field(
        default="claude-sonnet-4-6", validation_alias=AliasChoices("ANTHROPIC_PLANNER_MODEL")
    )
    elevenlabs_api_key: str = Field(default="", validation_alias=AliasChoices("ELEVENLABS_API_KEY"))
    elevenlabs_model: str = Field(
        default="eleven_multilingual_v2", validation_alias=AliasChoices("ELEVENLABS_MODEL")
    )
    # Optional extra voice-clone providers for the candidate A/B. Empty -> that
    # candidate slot is skipped (graceful, like the music candidates).
    fish_api_key: str = Field(default="", validation_alias=AliasChoices("FISH_API_KEY"))
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
    # Image-to-image EDIT model for avatar looks: keeps the person from the first
    # frame and restyles the scene/environment around them (identity-lock edit).
    fal_edit_model: str = Field(
        default="fal-ai/bytedance/seedream/v4.5/edit",
        validation_alias=AliasChoices("FAL_EDIT_MODEL"),
    )
    # Background-music generator (fal). Stable Audio 3 is instrumental + licensed.
    fal_music_model: str = Field(
        default="fal-ai/stable-audio-3/medium/text-to-audio",
        validation_alias=AliasChoices("FAL_MUSIC_MODEL"),
    )
    # SerpAPI key for real-media image search (scrape-first sourcing). Empty -> generate.
    serpapi_key: str = Field(default="", validation_alias=AliasChoices("SERPAPI_KEY"))
    # Research backend (default "serpapi_rest"): the agent builds the search query
    # from today's date + the brief in one fast call, then we run SerpAPI Google
    # (~4s total). "claude_mcp" lets the agent drive SerpAPI via the MCP connector
    # (correct but ~100s+), "anthropic" is model-only. Degrades rest -> anthropic.
    research_mode: str = Field(
        default="serpapi_rest", validation_alias=AliasChoices("RESEARCH_MODE")
    )
    # How many YouTube Shorts to pull as real footage per plan (0 disables).
    youtube_shorts_count: int = Field(
        default=2, validation_alias=AliasChoices("YOUTUBE_SHORTS_COUNT")
    )
    # Use a Claude vision pass to pick the best scraped image per scene (vs heuristic).
    media_vision_select: bool = Field(
        default=True, validation_alias=AliasChoices("MEDIA_VISION_SELECT")
    )
    # Minimum short-side px for scraped media — keep stills crisp at the video's
    # 1080-wide vertical target. Verified from the decoded bytes, not just metadata.
    media_min_dimension: int = Field(
        default=900, validation_alias=AliasChoices("MEDIA_MIN_DIMENSION")
    )
    # Text-to-image driver for avatar looks: "fal" (managed) or "flux2"
    # (self-hosted FLUX.2 on the Starya inference cluster).
    broll_t2i_driver: str = Field(
        default="fal", validation_alias=AliasChoices("BROLL_T2I_DRIVER")
    )
    broll_flux_api_base: str = Field(
        default="", validation_alias=AliasChoices("BROLL_FLUX_API_BASE")
    )
    avatar_looks_count: int = Field(
        default=3, validation_alias=AliasChoices("AVATAR_LOOKS_COUNT")
    )
    # Avatar-card looks generated at creation time, editing the first frame in its
    # own environment: "seedream" (fal image edit), "flux2" (self-hosted t2i), or
    # "none". How many looks to render for the card grid.
    avatar_looks_driver: str = Field(
        default="seedream", validation_alias=AliasChoices("AVATAR_LOOKS_DRIVER")
    )
    avatar_card_looks: int = Field(
        default=2, validation_alias=AliasChoices("AVATAR_CARD_LOOKS")
    )
    caption_font: str = Field(default="DejaVu Sans", validation_alias=AliasChoices("CAPTION_FONT"))
    pipeline_concurrency: int = Field(
        default=4, validation_alias=AliasChoices("PIPELINE_CONCURRENCY")
    )

    # --- Generation driver seam (plan_generate) -----------------------------
    # Each capability is swappable so the user's open-weight models (Starya
    # cluster) can drop in later without touching the orchestration. Per-request
    # `model_overrides` on POST /v1/plans/{id}/generate override these per run.
    # TTS: "elevenlabs" (cloned voice, word timestamps) — only driver today.
    tts_driver: str = Field(default="elevenlabs", validation_alias=AliasChoices("TTS_DRIVER"))
    # Talking-avatar lip-sync: "fabric" (fal veed/fabric) or "none" (skip, b-roll only).
    lipsync_driver: str = Field(default="fabric", validation_alias=AliasChoices("LIPSYNC_DRIVER"))
    # b-roll motion: "kenburns" (ffmpeg pan/zoom on a still — default, free, robust),
    # "kling" (fal image-to-video), or "selfhosted" (open-weight I2V, later).
    i2v_driver: str = Field(default="kenburns", validation_alias=AliasChoices("I2V_DRIVER"))
    # Which materialized music candidate to prefer when selections don't pin one.
    music_driver: str = Field(default="elevenlabs", validation_alias=AliasChoices("MUSIC_DRIVER"))
    # Still generator for b-roll scenes with no scraped media: "fal" (flux/schnell).
    t2i_driver: str = Field(default="fal", validation_alias=AliasChoices("T2I_DRIVER"))
    # Music bed gain (linear) and whether to duck it under the voiceover.
    music_gain: float = Field(default=0.22, validation_alias=AliasChoices("MUSIC_GAIN"))
    cache_dir: str = Field(default="cache", validation_alias=AliasChoices("CACHE_DIR"))
    video_target_seconds: int = Field(
        default=10, validation_alias=AliasChoices("VIDEO_TARGET_SECONDS")
    )

    @field_validator("s3_endpoint", "s3_public_endpoint", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
