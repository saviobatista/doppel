import contextlib

from redis.exceptions import ResponseError
from sqlalchemy.ext.asyncio import AsyncSession

from doppel_api.models import Job

STREAMS = {"interactive": "jobs:interactive", "background": "jobs:background"}
GROUP = "workers"


async def ensure_groups(redis) -> None:
    for stream in STREAMS.values():
        with contextlib.suppress(ResponseError):
            await redis.xgroup_create(stream, GROUP, id="0", mkstream=True)


async def enqueue(redis, session: AsyncSession, kind: str, lane: str, payload: dict) -> Job:
    job = Job(kind=kind, lane=lane, payload=payload)
    session.add(job)
    await session.flush()
    await redis.xadd(STREAMS[lane], {"job_id": job.id})
    return job


async def read_next(redis, consumer: str) -> dict | None:
    for lane in ("interactive", "background"):
        resp = await redis.xreadgroup(
            GROUP, consumer, {STREAMS[lane]: ">"}, count=1, block=100
        )
        if resp:
            _stream, messages = resp[0]
            msg_id, fields = messages[0]
            return {"msg_id": msg_id, "lane": lane, "job_id": fields["job_id"]}
    return None


async def ack(redis, lane: str, msg_id: str) -> None:
    await redis.xack(STREAMS[lane], GROUP, msg_id)
