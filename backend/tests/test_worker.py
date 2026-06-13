from collections import Counter
from pathlib import Path

import fakeredis.aioredis
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api import config
from doppel_api.constants import HELLO_LINE
from doppel_api.db import init_db, make_session_factory
from doppel_api.models import Avatar, Device, Job, Video
from doppel_api.providers import media
from doppel_api.providers.media import CaptionCue
from doppel_api.queue import ensure_groups, enqueue
from doppel_api.storage import MemoryStorage
from workers import worker
from workers.worker import WorkerContext, process_one


@pytest.fixture
async def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path / "cache"), raising=False)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_groups(redis)
    yield WorkerContext(
        session_factory=make_session_factory(engine),
        storage=MemoryStorage(),
        redis=redis,
        consumer="test-worker",
    )
    await engine.dispose()


def _patch_providers(monkeypatch, *, broll_ok=True, fail=None):
    counts = Counter()

    async def maybe(name):
        if fail == name:
            raise RuntimeError(f"{name} boom")

    async def fake_extract_frame(src, out):
        await maybe("extract_frame")
        Path(out).write_bytes(b"IMG")  # noqa: ASYNC240
        return out

    async def fake_extract_audio(src, out):
        Path(out).write_bytes(b"WAV")  # noqa: ASYNC240
        return out

    async def fake_fetch(url):
        return b"MP4"

    async def fake_compose(avatar_path, brolls, cues, out, font):
        Path(out).write_bytes(b"FINAL")  # noqa: ASYNC240
        return out

    monkeypatch.setattr(media, "extract_frame", fake_extract_frame)
    monkeypatch.setattr(media, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(media, "fetch", fake_fetch)
    monkeypatch.setattr(media, "compose_timeline", fake_compose)

    async def fake_clone(sample, name):
        await maybe("clone")
        counts["clone"] += 1
        return "voice-xyz"

    async def fake_tts(voice_id, text):
        counts["tts"] += 1
        return b"AUDIO-" + text.encode()  # distinct per line, like the real provider

    async def fake_tts_ts(voice_id, text):
        counts["tts_ts"] += 1
        return b"AUDIO", [CaptionCue(text="oi", start=0.0, end=0.5)]

    async def fake_stt(path):
        counts["stt"] += 1
        return "briefing transcrito"

    monkeypatch.setattr(worker.voice, "clone", fake_clone)
    monkeypatch.setattr(worker.voice, "tts", fake_tts)
    monkeypatch.setattr(worker.voice, "tts_with_timestamps", fake_tts_ts)
    monkeypatch.setattr(worker.voice, "stt", fake_stt)

    async def fake_build_script(transcript, target_seconds):
        counts["script"] += 1
        return {
            "narration": {"text": "Olá, sou eu aprimorado.", "tone": "confiante"},
            "scenes": [
                {"id": "s1", "start": 0.0, "end": 10.0, "type": "avatar"},
                {"id": "s2", "start": 10.0, "end": 20.0, "type": "broll",
                 "prompt": "cofre", "motion": "zoom"},
                {"id": "s3", "start": 20.0, "end": 30.0, "type": "avatar"},
            ],
            "captions": {"style": "tiktok"},
        }

    monkeypatch.setattr(worker.script, "build_script", fake_build_script)

    async def fake_upload(path):
        counts["upload"] += 1
        return f"https://fal.media/{path.split('/')[-1]}"

    async def fake_talking(image_url, audio_url, resolution="480p"):
        counts["talking"] += 1
        return "https://fal.media/talk.mp4"

    async def fake_image(prompt, image_size="portrait_16_9"):
        counts["image"] += 1
        if not broll_ok:
            raise RuntimeError("flux boom")
        return "https://fal.media/i.jpg"

    async def fake_broll(image_url, prompt, duration="5"):
        counts["broll"] += 1
        return "https://fal.media/b.mp4"

    monkeypatch.setattr(worker.video, "upload", fake_upload)
    monkeypatch.setattr(worker.video, "talking", fake_talking)
    monkeypatch.setattr(worker.video, "image", fake_image)
    monkeypatch.setattr(worker.video, "broll", fake_broll)
    return counts


async def _seed_avatar(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="t" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="processing", assets={"source": "raw/x/source.webm"})
        s.add(a)
        await s.flush()
        avatar_id = a.id
        await ctx.storage.put("raw/x/source.webm", b"SRC", "video/webm")
        await enqueue(ctx.redis, s, kind="avatar_prep", lane="interactive",
                      payload={"avatar_id": avatar_id})
        return avatar_id


async def _seed_ready_avatar_and_video(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="u" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="ready",
                   assets={"face_image": "avatars/a/face.png", "voice_id": "voice-xyz"})
        s.add(a)
        await s.flush()
        v = Video(device_id=d.id, avatar_id=a.id, assets={"briefing": "videos/v/briefing.webm"})
        s.add(v)
        await s.flush()
        video_id = v.id
        await ctx.storage.put("avatars/a/face.png", b"IMG", "image/png")
        await ctx.storage.put("videos/v/briefing.webm", b"AUD", "audio/webm")
        await enqueue(ctx.redis, s, kind="fast_generate", lane="interactive",
                      payload={"video_id": video_id})
        return video_id


async def _latest_video_id(ctx) -> str:
    async with ctx.session_factory() as s:
        return (await s.execute(select(Video))).scalars().first().id


async def test_process_one_returns_false_on_empty_queue(ctx):
    assert await process_one(ctx) is False


async def test_orphan_job_id_is_skipped_not_fatal(ctx):
    await ctx.redis.xadd("jobs:interactive", {"job_id": "nope"})
    assert await process_one(ctx) is True
    assert await process_one(ctx) is False


async def test_avatar_prep_produces_hello_and_feedback(ctx, monkeypatch):
    avatar_id = await _seed_avatar(ctx)
    events = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    _patch_providers(monkeypatch)
    monkeypatch.setattr(worker, "publish", capture)
    assert HELLO_LINE
    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
    assert avatar.status == "ready"
    assert avatar.assets["voice_id"] == "voice-xyz"
    assert avatar.assets["face_image"] == f"avatars/{avatar_id}/face.png"
    assert avatar.assets["hello"] == f"avatars/{avatar_id}/hello.mp4"
    assert await ctx.storage.get(avatar.assets["hello"]) == b"MP4"
    assert events[-1][0] == "hello_ready"
    assert "hello_url" in events[-1][1] and "feedback_url" in events[-1][1]


async def test_fast_generate_composes_video(ctx, monkeypatch):
    video_id = await _seed_ready_avatar_and_video(ctx)
    events = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    _patch_providers(monkeypatch)
    monkeypatch.setattr(worker, "publish", capture)
    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video))).scalar_one()
    assert v.status_fast == "ready"
    assert v.assets["fast"] == f"videos/{video_id}/fast.mp4"
    assert await ctx.storage.get(v.assets["fast"]) == b"FINAL"
    assert v.script["narration"]["text"]
    assert events[-1][0] == "fast_ready"
    assert "fast_url" in events[-1][1]


async def test_fast_generate_degrades_when_broll_fails(ctx, monkeypatch):
    await _seed_ready_avatar_and_video(ctx)
    _patch_providers(monkeypatch, broll_ok=False)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(worker, "publish", noop)
    assert await process_one(ctx) is True
    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video))).scalar_one()
    assert v.status_fast == "ready"


async def test_avatar_prep_failure_marks_failed(ctx, monkeypatch):
    await _seed_avatar(ctx)
    events = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    _patch_providers(monkeypatch, fail="clone")
    monkeypatch.setattr(worker, "publish", capture)
    assert await process_one(ctx) is True
    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
        job = (await s.execute(select(Job).where(Job.kind == "avatar_prep"))).scalar_one()
    assert avatar.status == "failed"
    assert job.status == "failed"
    assert events[-1] == ("failed", {"kind": "avatar_prep"})


async def test_avatar_prep_second_run_uses_cache(ctx, monkeypatch):
    avatar_id = await _seed_avatar(ctx)
    counts = _patch_providers(monkeypatch)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(worker, "publish", noop)
    await worker.handle_avatar_prep(ctx, {"avatar_id": avatar_id})
    assert counts["clone"] == 1 and counts["talking"] == 2
    counts.clear()
    await worker.handle_avatar_prep(ctx, {"avatar_id": avatar_id})
    assert sum(counts.values()) == 0  # everything served from the cache


async def test_fast_generate_second_run_uses_cache(ctx, monkeypatch):
    await _seed_ready_avatar_and_video(ctx)
    video_id = await _latest_video_id(ctx)
    counts = _patch_providers(monkeypatch)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(worker, "publish", noop)
    await worker.handle_fast_generate(ctx, {"video_id": video_id})
    assert counts["talking"] >= 1 and counts["script"] == 1
    counts.clear()
    await worker.handle_fast_generate(ctx, {"video_id": video_id})
    assert sum(counts.values()) == 0
