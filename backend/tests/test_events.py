import asyncio

import fakeredis.aioredis

from doppel_api.events import publish, sse_format, subscription


async def test_publish_subscribe_roundtrip():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    received = []

    async def listen():
        async with subscription(redis, "av1") as events:
            async for event, data in events:
                received.append((event, data))
                break

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    await publish(redis, "av1", "hello_ready", {"url": "memory://hello"})
    await asyncio.wait_for(task, timeout=2)
    assert received == [("hello_ready", {"url": "memory://hello"})]


async def test_no_lost_event_after_subscription_enter():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    async with subscription(redis, "av2") as events:
        # published AFTER enter, BEFORE iteration starts: must not be lost
        await publish(redis, "av2", "hello_ready", {"n": 1})
        event, data = await asyncio.wait_for(anext(events), timeout=2)
    assert (event, data) == ("hello_ready", {"n": 1})


def test_sse_format():
    out = sse_format("status", {"value": "processing"})
    assert out == 'event: status\ndata: {"value": "processing"}\n\n'
