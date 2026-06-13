"""Doppel generation worker: consumes jobs and drives the managed providers."""
import asyncio
import os
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.events import publish  # tests rebind this name; keep it a module global
from doppel_api.models import Avatar, Job, Video
from doppel_api.queue import ack, ensure_groups, read_next
from doppel_api.storage import S3Storage, Storage


@dataclass
class WorkerContext:
    session_factory: async_sessionmaker[AsyncSession]
    storage: Storage
    redis: object
    consumer: str


STEP_DELAY = 0.5


def make_stub_video(path: Path, seconds: int, label: str) -> None:
    """Gera um mp4 9:16 com texto central e tom de audio. Requer ffmpeg no PATH.

    label e interpolado no filtro drawtext: nao pode conter aspas simples ou ':'.
    """
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=540x960:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
        "-vf", f"drawtext=text='{label}':fontcolor=white:fontsize=64:"
               "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr_tail = (e.stderr or b"")[-2000:]
        raise RuntimeError(f"ffmpeg failed ({e.returncode}): {stderr_tail!r}") from e


async def _render_and_upload(ctx: WorkerContext, key: str, seconds: int, label: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.mp4"
        await anyio.to_thread.run_sync(lambda: make_stub_video(out, seconds, label))
        await ctx.storage.put(key, out.read_bytes(), "video/mp4")


async def handle_avatar_prep(ctx: WorkerContext, payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})
    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    await _render_and_upload(ctx, hello_key, 6, "HELLO")
    await _render_and_upload(ctx, feedback_key, 4, "FEEDBACK")
    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {**avatar.assets, "hello": hello_key, "feedback": feedback_key}
        await s.commit()
    hello_url = await ctx.storage.presign_get(hello_key)
    feedback_url = await ctx.storage.presign_get(feedback_key)
    await publish(ctx.redis, avatar_id, "hello_ready",
                  {"hello_url": hello_url, "feedback_url": feedback_url})


async def handle_fast_generate(ctx: WorkerContext, payload: dict) -> None:
    video_id = payload["video_id"]
    await publish(ctx.redis, video_id, "progress", {"step": "scripting"})
    await asyncio.sleep(STEP_DELAY)  # artificial latency visible in UI
    for n in (1, 2, 3):
        await publish(ctx.redis, video_id, "progress", {"step": f"component_{n}_of_3"})
        await asyncio.sleep(STEP_DELAY)
    key = f"videos/{video_id}/fast.mp4"
    await _render_and_upload(ctx, key, 30, "DOPPEL FAST STUB")
    async with ctx.session_factory() as s:
        video = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        video.status_fast = "ready"
        video.assets = {**video.assets, "fast": key}
        video.script = {"narration": {"text": "stub"}, "scenes": [], "music": {}, "captions": {}}
        await s.commit()
    url = await ctx.storage.presign_get(key)
    await publish(ctx.redis, video_id, "fast_ready", {"fast_url": url})


HANDLERS = {"avatar_prep": handle_avatar_prep, "fast_generate": handle_fast_generate}


async def process_one(ctx: WorkerContext) -> bool:
    msg = await read_next(ctx.redis, consumer=ctx.consumer)
    if msg is None:
        return False
    async with ctx.session_factory() as s:
        job = (
            await s.execute(select(Job).where(Job.id == msg["job_id"]))
        ).scalar_one_or_none()
        if job is None:
            # orphan stream entry (stream message without a row): skip without killing worker
            print(f"orphan stream entry, skipping job_id={msg['job_id']}")
            await ack(ctx.redis, msg["lane"], msg["msg_id"])
            return True
        job.status = "running"
        await s.commit()
        kind, payload = job.kind, dict(job.payload)
    try:
        await HANDLERS[kind](ctx, payload)
        status = "done"
    except Exception as exc:  # worker must survive any job failure
        print(f"job {msg['job_id']} ({kind}) failed: {exc!r}")
        status = "failed"
        entity_id = payload.get("avatar_id") or payload.get("video_id") or ""
        async with ctx.session_factory() as s:
            if "avatar_id" in payload:
                avatar = (
                    await s.execute(select(Avatar).where(Avatar.id == payload["avatar_id"]))
                ).scalar_one_or_none()
                if avatar is not None:
                    avatar.status = "failed"
            elif "video_id" in payload:
                video = (
                    await s.execute(select(Video).where(Video.id == payload["video_id"]))
                ).scalar_one_or_none()
                if video is not None:
                    video.status_fast = "failed"
            await s.commit()
        if entity_id:
            await publish(ctx.redis, entity_id, "failed", {"kind": kind})
    async with ctx.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.id == msg["job_id"]))).scalar_one()
        job.status = status
        await s.commit()
    await ack(ctx.redis, msg["lane"], msg["msg_id"])
    return True


async def main() -> None:
    settings = get_settings()
    engine = make_engine()
    await init_db(engine)
    storage = S3Storage(settings)
    await storage.ensure_bucket()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await ensure_groups(redis)
    ctx = WorkerContext(
        session_factory=make_session_factory(engine), storage=storage,
        redis=redis, consumer=f"stub-{socket.gethostname()}-{os.getpid()}",
    )
    print(f"stub worker started as {ctx.consumer}")
    while True:
        try:
            worked = await process_one(ctx)
        except Exception as exc:
            print(f"worker loop error: {exc!r}")
            await asyncio.sleep(1.0)
            continue
        if not worked:
            await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())
