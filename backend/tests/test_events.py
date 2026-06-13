import asyncio

import fakeredis.aioredis

from doppel_api import events
from doppel_api.events import HEARTBEAT, publish, sse_comment, sse_format, subscription


async def test_publish_subscribe_roundtrip():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    received = []

    async def listen():
        async with subscription(redis, "av1") as stream:
            async for event, data in stream:
                if event == HEARTBEAT:
                    continue
                received.append((event, data))
                break

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    await publish(redis, "av1", "hello_ready", {"url": "memory://hello"})
    await asyncio.wait_for(task, timeout=2)
    assert received == [("hello_ready", {"url": "memory://hello"})]


async def test_no_lost_event_after_subscription_enter():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with subscription(redis, "av2") as stream:
        # published AFTER enter, BEFORE iteration starts: must not be lost
        await publish(redis, "av2", "hello_ready", {"n": 1})
        async for event, data in stream:
            if event == HEARTBEAT:
                continue
            assert (event, data) == ("hello_ready", {"n": 1})
            break


async def test_subscription_survives_idle_with_heartbeats(monkeypatch):
    # Regression: a bare listen() raises TimeoutError after ~5s idle on redis-py 8,
    # which broke the SSE during multi-minute provider waits. The iterator must
    # emit heartbeats on idle and still deliver the real event.
    monkeypatch.setattr(events, "HEARTBEAT_SECONDS", 0.02)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    got = []

    async def run():
        async with subscription(redis, "e1") as stream:
            async for event, _ in stream:
                got.append(event)
                if event == "done":
                    break

    task = asyncio.create_task(run())
    await asyncio.sleep(0.1)  # idle: heartbeats accumulate, stream must NOT break
    await publish(redis, "e1", "done", {})
    await asyncio.wait_for(task, timeout=2)
    assert HEARTBEAT in got  # survived idle
    assert "done" in got  # real event still delivered


def test_sse_format():
    out = sse_format("status", {"value": "processing"})
    assert out == 'event: status\ndata: {"value": "processing"}\n\n'


def test_sse_comment():
    assert sse_comment() == ": ping\n\n"
