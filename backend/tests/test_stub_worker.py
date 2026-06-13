import fakeredis.aioredis
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api.db import init_db, make_session_factory
from doppel_api.models import Avatar, Device, Job, Video
from doppel_api.queue import ensure_groups, enqueue
from doppel_api.storage import MemoryStorage
from workers import stub_worker
from workers.stub_worker import WorkerContext, process_one


@pytest.fixture
async def ctx(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_groups(redis)
    monkeypatch.setattr(
        stub_worker, "make_stub_video",
        lambda path, seconds, label: path.write_bytes(b"MP4" + label.encode()),
    )
    monkeypatch.setattr(stub_worker, "STEP_DELAY", 0)
    yield WorkerContext(
        session_factory=make_session_factory(engine),
        storage=MemoryStorage(),
        redis=redis,
        consumer="test-worker",
    )
    await engine.dispose()


async def _seed_avatar(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="t" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="processing", assets={"source": "raw/x/source.webm"})
        s.add(a)
        await s.flush()
        avatar_id = a.id
        await enqueue(
            ctx.redis, s, kind="avatar_prep", lane="interactive",
            payload={"avatar_id": avatar_id},
        )
        return avatar_id


async def _seed_video(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="u" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="ready")
        s.add(a)
        await s.flush()
        v = Video(device_id=d.id, avatar_id=a.id)
        s.add(v)
        await s.flush()
        video_id = v.id
        await enqueue(
            ctx.redis, s, kind="fast_generate", lane="interactive",
            payload={"video_id": video_id},
        )
        return video_id


async def test_process_one_returns_false_on_empty_queue(ctx):
    assert await process_one(ctx) is False


async def test_avatar_prep_produces_hello_and_feedback(ctx, monkeypatch):
    avatar_id = await _seed_avatar(ctx)

    events: list[tuple[str, dict]] = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    monkeypatch.setattr(stub_worker, "publish", capture)
    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
    assert avatar.status == "ready"
    assert avatar.assets["hello"] == f"avatars/{avatar_id}/hello.mp4"
    assert avatar.assets["feedback"] == f"avatars/{avatar_id}/feedback.mp4"
    assert await ctx.storage.get(avatar.assets["hello"]) == b"MP4HELLO"

    names = [e for e, _ in events]
    assert names[-1] == "hello_ready"
    assert "hello_url" in events[-1][1]
    assert "feedback_url" in events[-1][1]


async def test_fast_generate_produces_video_and_script(ctx, monkeypatch):
    video_id = await _seed_video(ctx)

    events: list[tuple[str, dict]] = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    monkeypatch.setattr(stub_worker, "publish", capture)
    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        video = (await s.execute(select(Video))).scalar_one()
    assert video.status_fast == "ready"
    assert video.assets["fast"] == f"videos/{video_id}/fast.mp4"
    assert video.script is not None

    names = [e for e, _ in events]
    assert "progress" in names
    assert names[-1] == "fast_ready"
    assert "fast_url" in events[-1][1]


async def test_orphan_job_id_is_skipped_not_fatal(ctx):
    await ctx.redis.xadd("jobs:interactive", {"job_id": "doesnotexist"})
    assert await process_one(ctx) is True  # consumed, acked, skipped
    assert await process_one(ctx) is False  # queue drained, worker alive


async def test_handler_failure_marks_entity_failed_and_worker_survives(ctx, monkeypatch):
    await _seed_avatar(ctx)

    def boom(path, seconds, label):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(stub_worker, "make_stub_video", boom)

    events: list[tuple[str, dict]] = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    monkeypatch.setattr(stub_worker, "publish", capture)

    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
        job = (await s.execute(select(Job).where(Job.kind == "avatar_prep"))).scalar_one()
    assert avatar.status == "failed"
    assert job.status == "failed"
    assert events[-1] == ("failed", {"kind": "avatar_prep"})
    assert await process_one(ctx) is False  # queue drained, worker alive
