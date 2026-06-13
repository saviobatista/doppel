"""Doppel generation worker: consumes jobs and drives the managed providers."""
import asyncio
import os
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.constants import FEEDBACK_LINE, HELLO_LINE
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.events import publish
from doppel_api.models import Avatar, Job, Video
from doppel_api.providers import media, script, video, voice
from doppel_api.queue import ack, ensure_groups, read_next
from doppel_api.storage import S3Storage, Storage


@dataclass
class WorkerContext:
    session_factory: async_sessionmaker[AsyncSession]
    storage: Storage
    redis: object
    consumer: str


async def _store_fal_video(ctx: "WorkerContext", url: str, key: str, tmp: Path, name: str) -> None:
    local = tmp / name
    await media.download(url, str(local))
    await ctx.storage.put(key, local.read_bytes(), "video/mp4")


async def handle_avatar_prep(ctx: "WorkerContext", payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        source_key = avatar.assets["source"]

    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    face_key = f"avatars/{avatar_id}/face.png"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "source"
        src.write_bytes(await ctx.storage.get(source_key))

        face_path = tmp / "face.png"
        face = await media.extract_frame(str(src), str(face_path))
        ref_audio = await media.extract_audio(str(src), str(tmp / "ref.wav"))
        await ctx.storage.put(face_key, face_path.read_bytes(), "image/png")

        voice_id = await voice.clone(ref_audio, name=f"doppel-{avatar_id[:8]}")
        face_url = await video.upload(face)

        for line, key, name in (
            (HELLO_LINE, hello_key, "hello"),
            (FEEDBACK_LINE, feedback_key, "feedback"),
        ):
            audio_bytes = await voice.tts(voice_id, line)
            audio_path = tmp / f"{name}.mp3"
            audio_path.write_bytes(audio_bytes)
            audio_url = await video.upload(str(audio_path))
            talk_url = await video.talking(face_url, audio_url)
            await _store_fal_video(ctx, talk_url, key, tmp, f"{name}.mp4")

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {
            **avatar.assets,
            "face_image": face_key,
            "voice_id": voice_id,
            "hello": hello_key,
            "feedback": feedback_key,
        }
        await s.commit()

    await publish(ctx.redis, avatar_id, "hello_ready", {
        "hello_url": await ctx.storage.presign_get(hello_key),
        "feedback_url": await ctx.storage.presign_get(feedback_key),
    })


async def _gen_broll(ctx, scene, idx, total, tmp, video_id, sem) -> media.BrollClip | None:
    async with sem:
        try:
            img_url = await video.image(scene.get("prompt", ""))
            clip_url = await video.broll(img_url, scene.get("motion") or scene.get("prompt", ""))
            path = str(tmp / f"broll{idx}.mp4")
            await media.download(clip_url, path)
            await publish(ctx.redis, video_id, "progress",
                          {"step": f"component_{idx + 2}_of_{total}"})
            return media.BrollClip(path=path, start=float(scene["start"]), end=float(scene["end"]))
        except Exception as exc:  # graceful degrade: drop this scene, keep the video
            print(f"broll scene {scene.get('id')} failed, dropping: {exc!r}")
            return None


async def handle_fast_generate(ctx: "WorkerContext", payload: dict) -> None:
    video_id = payload["video_id"]
    settings = get_settings()

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        briefing_key = v.assets["briefing"]
        avatar = (await s.execute(select(Avatar).where(Avatar.id == v.avatar_id))).scalar_one()
        voice_id = avatar.assets["voice_id"]
        face_key = avatar.assets["face_image"]

    await publish(ctx.redis, video_id, "progress", {"step": "scripting"})
    fast_key = f"videos/{video_id}/fast.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        brief = tmp / "briefing"
        brief.write_bytes(await ctx.storage.get(briefing_key))
        transcript = await voice.stt(str(brief))
        script_json = await script.build_script(transcript)

        narration_audio, cues = await voice.tts_with_timestamps(
            voice_id, script_json["narration"]["text"]
        )
        (tmp / "narration.mp3").write_bytes(narration_audio)

        face_local = tmp / "face.png"
        face_local.write_bytes(await ctx.storage.get(face_key))
        face_url = await video.upload(str(face_local))
        narration_url = await video.upload(str(tmp / "narration.mp3"))

        broll_scenes = [sc for sc in script_json["scenes"] if sc["type"] == "broll"]
        total = 1 + len(broll_scenes)
        sem = asyncio.Semaphore(settings.pipeline_concurrency)

        async def gen_avatar() -> str:
            await publish(ctx.redis, video_id, "progress", {"step": f"component_1_of_{total}"})
            url = await video.talking(face_url, narration_url)
            path = str(tmp / "avatar.mp4")
            await media.download(url, path)
            return path

        results = await asyncio.gather(
            gen_avatar(),
            *[_gen_broll(ctx, sc, i, total, tmp, video_id, sem)
              for i, sc in enumerate(broll_scenes)],
        )
        avatar_path = results[0]
        brolls = [b for b in results[1:] if b is not None]

        out = tmp / "fast.mp4"
        await media.compose_timeline(avatar_path, brolls, cues, str(out), settings.caption_font)
        await ctx.storage.put(fast_key, out.read_bytes(), "video/mp4")

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        v.status_fast = "ready"
        v.assets = {**v.assets, "fast": fast_key}
        v.script = script_json
        await s.commit()

    await publish(ctx.redis, video_id, "fast_ready", {
        "fast_url": await ctx.storage.presign_get(fast_key),
    })


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
                vid = (
                    await s.execute(select(Video).where(Video.id == payload["video_id"]))
                ).scalar_one_or_none()
                if vid is not None:
                    vid.status_fast = "failed"
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
        redis=redis, consumer=f"worker-{socket.gethostname()}-{os.getpid()}",
    )
    print(f"worker started as {ctx.consumer}")
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
