from doppel_api.config import Settings


def test_provider_settings_read_raw_env_names(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-secret")
    monkeypatch.setenv("FAL_T2I_MODEL", "fal-ai/flux/schnell")
    monkeypatch.setenv("PIPELINE_CONCURRENCY", "3")
    s = Settings()
    assert s.fal_key == "fal-secret"
    assert s.anthropic_api_key == "anthropic-secret"
    assert s.anthropic_model == "claude-sonnet-4-6"
    assert s.elevenlabs_api_key == "el-secret"
    assert s.fal_t2i_model == "fal-ai/flux/schnell"
    assert s.pipeline_concurrency == 3


def test_provider_settings_defaults():
    s = Settings()
    assert s.elevenlabs_model == "eleven_multilingual_v2"
    assert s.fal_lipsync_model == "veed/fabric-1.0"
    assert s.fal_broll_model == "fal-ai/kling-video/v2.1/standard/image-to-video"
    assert s.fal_t2i_model == "fal-ai/flux/schnell"
    assert s.caption_font == "DejaVu Sans"
    assert s.pipeline_concurrency == 4
    assert s.cache_dir == "cache"
    assert s.video_target_seconds == 10


def test_cache_and_duration_env(monkeypatch):
    monkeypatch.setenv("CACHE_DIR", "/app/cache")
    monkeypatch.setenv("VIDEO_TARGET_SECONDS", "30")
    s = Settings()
    assert s.cache_dir == "/app/cache"
    assert s.video_target_seconds == 30
