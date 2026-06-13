import pathlib

from doppel_api import cache, config


def _corrupt_json(directory: pathlib.Path) -> None:
    f = next(directory.glob("*.json"))
    f.write_text("not json{")


async def test_blob_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    calls = []

    async def producer():
        calls.append(1)
        return b"DATA"

    p1 = await cache.blob("ns", ["a", "b"], "bin", producer)
    p2 = await cache.blob("ns", ["a", "b"], "bin", producer)
    assert p1 == p2
    with open(p1, "rb") as f:  # noqa: ASYNC230
        assert f.read() == b"DATA"
    assert len(calls) == 1  # second call was a cache hit


async def test_blob_key_depends_on_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)

    async def make(tag):
        return tag.encode()

    pa = await cache.blob("ns", ["x"], "bin", lambda: make("A"))
    pb = await cache.blob("ns", ["y"], "bin", lambda: make("B"))
    assert pa != pb
    with open(pa, "rb") as f:  # noqa: ASYNC230
        assert f.read() == b"A"
    with open(pb, "rb") as f:  # noqa: ASYNC230
        assert f.read() == b"B"


async def test_value_roundtrip_and_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    calls = []

    async def producer():
        calls.append(1)
        return {"voice_id": "v1"}

    v1 = await cache.value("clone", [b"audio"], producer)
    v2 = await cache.value("clone", [b"audio"], producer)
    assert v1 == v2 == {"voice_id": "v1"}
    assert len(calls) == 1


async def test_value_corrupt_reproduces(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)

    async def ret(obj):
        return obj

    await cache.value("ns", ["k"], lambda: ret({"a": 1}))
    _corrupt_json(pathlib.Path(tmp_path, "ns"))
    out = await cache.value("ns", ["k"], lambda: ret({"a": 2}))
    assert out == {"a": 2}


async def test_blob_with_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    calls = []

    async def producer():
        calls.append(1)
        return b"AUDIO", [{"text": "oi", "start": 0.0, "end": 0.5}]

    p1, m1 = await cache.blob_with_meta("tts_ts", ["v", "t"], "mp3", producer)
    _p2, m2 = await cache.blob_with_meta("tts_ts", ["v", "t"], "mp3", producer)
    with open(p1, "rb") as f:  # noqa: ASYNC230
        assert f.read() == b"AUDIO"
    assert m1 == m2 == [{"text": "oi", "start": 0.0, "end": 0.5}]
    assert len(calls) == 1


def test_put_blob_writes_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    p = cache.put_blob("source", ["av1"], "webm", b"REC")
    with open(p, "rb") as f:
        assert f.read() == b"REC"
    p2 = cache.put_blob("source", ["av1"], "webm", b"DIFFERENT")
    assert p2 == p
    with open(p2, "rb") as f:
        assert f.read() == b"REC"  # not overwritten on hit
