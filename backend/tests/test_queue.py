import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api.db import init_db, make_session_factory
from doppel_api.queue import ack, ensure_groups, enqueue, read_next


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return make_session_factory(engine)


async def test_enqueue_creates_job_row_and_stream_entry(redis, session_factory):
    await ensure_groups(redis)
    async with session_factory() as s:
        job = await enqueue(redis, s, kind="avatar_prep", lane="interactive", payload={"x": 1})
        await s.commit()
    assert job.id
    msg = await read_next(redis, consumer="w1")
    assert msg is not None
    assert msg["job_id"] == job.id
    assert msg["lane"] == "interactive"


async def test_interactive_lane_drains_first(redis, session_factory):
    await ensure_groups(redis)
    async with session_factory() as s:
        bg = await enqueue(redis, s, kind="hq", lane="background", payload={})
        it = await enqueue(redis, s, kind="fast", lane="interactive", payload={})
        await s.commit()
    first = await read_next(redis, consumer="w1")
    assert first["job_id"] == it.id
    second = await read_next(redis, consumer="w1")
    assert second["job_id"] == bg.id
    await ack(redis, first["lane"], first["msg_id"])
    await ack(redis, second["lane"], second["msg_id"])


async def test_read_next_returns_none_when_empty(redis):
    await ensure_groups(redis)
    assert await read_next(redis, consumer="w1") is None
