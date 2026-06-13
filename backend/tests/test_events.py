import asyncio

import fakeredis.aioredis

from doppel_api.events import publish, sse_format, subscribe


async def test_publish_subscribe_roundtrip():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    received = []

    async def listen():
        async for event, data in subscribe(redis, "av1"):
            received.append((event, data))
            break

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    await publish(redis, "av1", "hello_ready", {"url": "memory://hello"})
    await asyncio.wait_for(task, timeout=2)
    assert received == [("hello_ready", {"url": "memory://hello"})]


def test_sse_format():
    out = sse_format("status", {"value": "processing"})
    assert out == 'event: status\ndata: {"value": "processing"}\n\n'
