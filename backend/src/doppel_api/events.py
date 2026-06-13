import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


def _channel(entity_id: str) -> str:
    return f"events:{entity_id}"


async def publish(redis, entity_id: str, event: str, data: dict) -> None:
    await redis.publish(_channel(entity_id), json.dumps({"event": event, "data": data}))


async def _iterate(pubsub) -> AsyncIterator[tuple[str, dict]]:
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        payload = json.loads(message["data"])
        yield payload["event"], payload["data"]


@asynccontextmanager
async def subscription(redis, entity_id: str):
    """Eagerly subscribed event iterator.

    Subscribe happens on context enter, BEFORE the caller reads its DB snapshot,
    closing the lost-event window between snapshot and listen. The pubsub
    connection is released on exit.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(entity_id))
    try:
        yield _iterate(pubsub)
    finally:
        await pubsub.aclose()


def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
