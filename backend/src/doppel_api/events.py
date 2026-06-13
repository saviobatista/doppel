import json
from collections.abc import AsyncIterator


def _channel(entity_id: str) -> str:
    return f"events:{entity_id}"


async def publish(redis, entity_id: str, event: str, data: dict) -> None:
    await redis.publish(_channel(entity_id), json.dumps({"event": event, "data": data}))


async def subscribe(redis, entity_id: str) -> AsyncIterator[tuple[str, dict]]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(entity_id))
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            payload = json.loads(message["data"])
            yield payload["event"], payload["data"]
    finally:
        await pubsub.unsubscribe(_channel(entity_id))


def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
