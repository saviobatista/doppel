import pytest

from doppel_api.config import Settings
from doppel_api.storage import MemoryStorage


def test_settings_defaults_and_env(monkeypatch):
    monkeypatch.setenv("DOPPEL_S3_BUCKET", "test-bucket")
    s = Settings()
    assert s.s3_bucket == "test-bucket"
    assert s.redis_url.startswith("redis://")


async def test_memory_storage_roundtrip():
    st = MemoryStorage()
    await st.ensure_bucket()
    await st.put("raw/a/source.webm", b"bytes", "video/webm")
    url = await st.presign_get("raw/a/source.webm")
    assert "raw/a/source.webm" in url
    assert await st.get("raw/a/source.webm") == b"bytes"


async def test_memory_storage_missing_key():
    st = MemoryStorage()
    with pytest.raises(KeyError):
        await st.get("nope")


def test_settings_empty_s3_endpoint_becomes_none(monkeypatch):
    monkeypatch.setenv("DOPPEL_S3_ENDPOINT", "")
    assert Settings().s3_endpoint is None


async def test_memory_storage_presign_accepts_expiry():
    st = MemoryStorage()
    await st.put("k", b"v", "text/plain")
    assert await st.presign_get("k", expires_in=60) == "memory://k"
