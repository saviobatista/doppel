import pytest

from doppel_api.config import Settings
from doppel_api.storage import MemoryStorage, S3Storage


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


async def test_s3_presign_uses_public_endpoint(monkeypatch):
    # presigned URLs must point at the browser-reachable public endpoint, not the
    # internal compose hostname, so the browser can actually load the media.
    monkeypatch.setenv("DOPPEL_S3_ENDPOINT", "http://floci:4566")
    monkeypatch.setenv("DOPPEL_S3_PUBLIC_ENDPOINT", "http://localhost:4566")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    storage = S3Storage(Settings())
    url = await storage.presign_get("avatars/x/hello.mp4")
    assert "localhost:4566" in url
    assert "floci" not in url


async def test_s3_presign_falls_back_to_endpoint_when_no_public(monkeypatch):
    monkeypatch.setenv("DOPPEL_S3_ENDPOINT", "http://floci:4566")
    monkeypatch.delenv("DOPPEL_S3_PUBLIC_ENDPOINT", raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    storage = S3Storage(Settings())
    url = await storage.presign_get("k")
    assert "floci:4566" in url
