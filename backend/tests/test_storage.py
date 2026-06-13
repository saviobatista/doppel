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
