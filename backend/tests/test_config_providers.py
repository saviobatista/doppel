from doppel_api.config import Settings


def test_settings_loads_inference_env(monkeypatch):
    monkeypatch.setenv("INFERENCE_API_KEY", "inf-secret")
    monkeypatch.setenv("AVATAR_API_BASE", "http://latentsync:8080")
    monkeypatch.setenv("BROLL_API_BASE", "http://cosmos:8000")
    monkeypatch.setenv("BROLL_FAST_STEPS", "20")
    s = Settings()
    assert s.inference_api_key == "inf-secret"
    assert s.avatar_api_base == "http://latentsync:8080"
    assert s.broll_api_base == "http://cosmos:8000"
    assert s.broll_fast_steps == 20


def test_settings_inference_defaults():
    s = Settings()
    assert s.broll_fast_size == "480x832"
    assert s.broll_fast_fps == 24.0
    assert s.avatar_inference_steps == 20
    assert "/latentsync" in s.avatar_api_base
    assert "/cosmos3" in s.broll_api_base
