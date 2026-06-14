from sqlalchemy.ext.asyncio import AsyncSession

from doppel_api.models import Job

STREAMS = {"interactive": "jobs:interactive", "background": "jobs:background"}
GROUP = "workers"
MAXLEN = 10_000
# Messages still pending (delivered, un-ACKed) longer than this were stranded by a
# crashed/restarted worker; a live worker reclaims them so jobs never hang forever.
# Must exceed the longest healthy job so an in-flight job is never stolen.
STALE_MS = 8 * 60 * 1000


async def ensure_groups(redis) -> None:
    from redis.exceptions import ResponseError

    for stream in STREAMS.values():
        try:
            await redis.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise


async def enqueue(redis, session: AsyncSession, kind: str, lane: str, payload: dict) -> Job:
    """Create the durable Job row, COMMIT the session, then notify the stream.

    Commit-before-xadd ordering: a worker must never receive a job_id whose row
    is not yet visible. The residual failure mode (committed row, xadd failed)
    leaves a job in status=queued, which is observable and re-enqueueable.
    Requires a redis client with decode_responses=True.
    """
    if lane not in STREAMS:
        raise ValueError(f"unknown lane: {lane}")
    job = Job(kind=kind, lane=lane, payload=payload)
    session.add(job)
    await session.commit()
    await redis.xadd(STREAMS[lane], {"job_id": job.id}, maxlen=MAXLEN, approximate=True)
    return job


async def _claim_stale(redis, consumer: str) -> dict | None:
    """Reclaim a message stranded by a dead worker (pending > STALE_MS)."""
    for lane in ("interactive", "background"):
        try:
            _cursor, messages, *_ = await redis.xautoclaim(
                STREAMS[lane], GROUP, consumer, STALE_MS, start_id="0-0", count=1
            )
        except Exception:
            continue
        for msg_id, fields in messages or []:
            if fields and fields.get("job_id"):
                print(f"reclaimed stale job {fields['job_id']} (msg {msg_id}, lane {lane})")
                return {"msg_id": msg_id, "lane": lane, "job_id": fields["job_id"]}
    return None


async def read_next(redis, consumer: str) -> dict | None:
    """New messages first (interactive before background); when idle, reclaim a
    message orphaned by a crashed/restarted worker. decode_responses=True required."""
    for lane in ("interactive", "background"):
        resp = await redis.xreadgroup(
            GROUP, consumer, {STREAMS[lane]: ">"}, count=1, block=100
        )
        if resp:
            _stream, messages = resp[0]
            msg_id, fields = messages[0]
            return {"msg_id": msg_id, "lane": lane, "job_id": fields["job_id"]}
    return await _claim_stale(redis, consumer)


async def ack(redis, lane: str, msg_id: str) -> None:
    await redis.xack(STREAMS[lane], GROUP, msg_id)
