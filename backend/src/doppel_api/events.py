import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# Sentinel yielded by the subscription iterator when no real message arrived
# within HEARTBEAT_SECONDS. The SSE routes turn it into an SSE comment to keep
# the connection alive. Kept under 5s because redis-py 8's pubsub raises
# TimeoutError on a bare listen() after ~5s idle; get_message(timeout=...)
# returns None instead of raising, which is what makes long waits survivable.
HEARTBEAT = "__heartbeat__"
HEARTBEAT_SECONDS = 4.0


def _channel(entity_id: str) -> str:
    return f"events:{entity_id}"


async def publish(redis, entity_id: str, event: str, data: dict) -> None:
    await redis.publish(_channel(entity_id), json.dumps({"event": event, "data": data}))


async def _iterate(pubsub) -> AsyncIterator[tuple[str, dict]]:
    while True:
        message = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=HEARTBEAT_SECONDS
        )
        if message is None:  # idle window elapsed: heartbeat, do NOT break
            yield HEARTBEAT, {}
            continue
        if message["type"] != "message":
            continue
        payload = json.loads(message["data"])
        yield payload["event"], payload["data"]


@asynccontextmanager
async def subscription(redis, entity_id: str):
    """Eagerly subscribed event iterator.

    Subscribe happens on context enter, BEFORE the caller reads its DB snapshot,
    closing the lost-event window between snapshot and listen. The iterator yields
    real (event, data) pairs and a HEARTBEAT sentinel on each idle window. The
    pubsub connection is released on exit.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(entity_id))
    try:
        yield _iterate(pubsub)
    finally:
        await pubsub.aclose()


def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def sse_comment(text: str = "ping") -> str:
    return f": {text}\n\n"
