"""Doppel generation worker: consumes jobs and drives the managed providers."""
import asyncio
import os
import socket
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.constants import FEEDBACK_LINE, HELLO_LINE
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.events import publish
from doppel_api.log import get_logger, kv, setup_logging
from doppel_api.models import Avatar, Job, Video
from doppel_api.providers import media, script, video, voice
from doppel_api.queue import ack, ensure_groups, read_next
from doppel_api.storage import S3Storage, Storage

log = get_logger("worker")


@dataclass
class WorkerContext:
    session_factory: async_sessionmaker[AsyncSession]
    storage: Storage
    redis: object
    consumer: str


def _fmt_exc(exc: Exception) -> str:
    # provider SDK errors (e.g. ElevenLabs ApiError) have an empty repr; surface .body
    body = getattr(exc, "body", None)
    return f"{type(exc).__name__}: {body or exc}"


async def _store_video(ctx: "WorkerContext", data: bytes, key: str) -> None:
    await ctx.storage.put(key, data, "video/mp4")


async def handle_avatar_prep(ctx: "WorkerContext", payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    log.info("avatar prep started %s", kv(avatar_id=avatar_id))
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        source_key = avatar.assets["source"]

    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    face_key = f"avatars/{avatar_id}/face.png"
    reference_key = f"avatars/{avatar_id}/reference_frame.png"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        t0 = time.monotonic()
        log.info("avatar prep stage %s", kv(avatar_id=avatar_id, stage="download_source", key=source_key))
        src = tmp / "source"
        src.write_bytes(await ctx.storage.get(source_key))

        log.info("avatar prep stage %s", kv(avatar_id=avatar_id, stage="extract_media"))
        face_path = tmp / "face.png"
        await media.extract_frame(str(src), str(face_path))
        ref_audio = await media.extract_audio(str(src), str(tmp / "ref.wav"))
        face_bytes = face_path.read_bytes()
        await ctx.storage.put(face_key, face_bytes, "image/png")
        await ctx.storage.put(reference_key, face_bytes, "image/png")

        log.info("avatar prep stage %s", kv(avatar_id=avatar_id, stage="voice_clone"))
        voice_id = await voice.clone(ref_audio, name=f"doppel-{avatar_id[:8]}")

        for line, key, name in (
            (HELLO_LINE, hello_key, "hello"),
            (FEEDBACK_LINE, feedback_key, "feedback"),
        ):
            log.info(
                "avatar prep stage %s",
                kv(avatar_id=avatar_id, stage=f"lipsync_{name}", voice_id=voice_id),
            )
            audio_path = tmp / f"{name}.mp3"
            audio_path.write_bytes(await voice.tts(voice_id, line))
            mp4 = await video.lipsync(str(src), str(audio_path))
            await _store_video(ctx, mp4, key)

        log.info(
            "avatar prep render complete %s",
            kv(avatar_id=avatar_id, duration_ms=int((time.monotonic() - t0) * 1000)),
        )

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {
            **avatar.assets,
            "face_image": face_key,
            "reference_frame": reference_key,
            "voice_id": voice_id,
            "hello": hello_key,
            "feedback": feedback_key,
        }
        await s.commit()

    await publish(ctx.redis, avatar_id, "hello_ready", {
        "hello_url": await ctx.storage.presign_get(hello_key),
        "feedback_url": await ctx.storage.presign_get(feedback_key),
    })
    log.info("avatar prep done %s", kv(avatar_id=avatar_id))


async def _gen_broll(ctx, scene, idx, total, tmp, video_id, reference_frame: bytes, sem) -> media.BrollClip | None:
    scene_id = scene.get("id", idx)
    async with sem:
        try:
            duration = float(scene["end"]) - float(scene["start"])
            log.info(
                "broll scene started %s",
                kv(video_id=video_id, scene_id=scene_id, index=idx + 1, total=total, duration_sec=duration),
            )
            mp4 = await video.broll_i2v(
                first_frame=reference_frame,
                prompt=scene.get("prompt", ""),
                negative_prompt=scene.get("negative", ""),
                duration_sec=duration,
            )
            path = str(tmp / f"broll{idx}.mp4")
            Path(path).write_bytes(mp4)
            await publish(ctx.redis, video_id, "progress",
                          {"step": f"component_{idx + 2}_of_{total}"})
            log.info("broll scene done %s", kv(video_id=video_id, scene_id=scene_id))
            return media.BrollClip(path=path, start=float(scene["start"]), end=float(scene["end"]))
        except Exception as exc:  # graceful degrade: drop this scene, keep the video
            log.warning(
                "broll scene dropped %s",
                kv(video_id=video_id, scene_id=scene_id, error=_fmt_exc(exc)),
            )
            return None


async def handle_fast_generate(ctx: "WorkerContext", payload: dict) -> None:
    video_id = payload["video_id"]
    settings = get_settings()
    log.info("fast generate started %s", kv(video_id=video_id))

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        briefing_key = v.assets["briefing"]
        avatar = (await s.execute(select(Avatar).where(Avatar.id == v.avatar_id))).scalar_one()
        voice_id = avatar.assets["voice_id"]
        source_key = avatar.assets["source"]
        reference_key = avatar.assets.get("reference_frame") or avatar.assets["face_image"]

    await publish(ctx.redis, video_id, "progress", {"step": "scripting"})
    fast_key = f"videos/{video_id}/fast.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        t0 = time.monotonic()

        log.info("fast generate stage %s", kv(video_id=video_id, stage="stt"))
        brief = tmp / "briefing"
        brief.write_bytes(await ctx.storage.get(briefing_key))
        transcript = await voice.stt(str(brief))
        log.info(
            "fast generate stage %s",
            kv(video_id=video_id, stage="script", transcript_chars=len(transcript)),
        )
        script_json = await script.build_script(transcript)

        log.info("fast generate stage %s", kv(video_id=video_id, stage="narration_tts"))
        narration_audio, cues = await voice.tts_with_timestamps(
            voice_id, script_json["narration"]["text"]
        )
        (tmp / "narration.mp3").write_bytes(narration_audio)

        source_local = tmp / "source"
        source_local.write_bytes(await ctx.storage.get(source_key))
        reference_frame = await ctx.storage.get(reference_key)

        broll_scenes = [sc for sc in script_json["scenes"] if sc["type"] == "broll"]
        total = 1 + len(broll_scenes)
        sem = asyncio.Semaphore(settings.pipeline_concurrency)
        log.info(
            "fast generate stage %s",
            kv(video_id=video_id, stage="parallel_render", broll_scenes=len(broll_scenes), total=total),
        )

        async def gen_avatar() -> str:
            await publish(ctx.redis, video_id, "progress", {"step": f"component_1_of_{total}"})
            log.info("fast generate stage %s", kv(video_id=video_id, stage="avatar_lipsync"))
            mp4 = await video.lipsync(str(source_local), str(tmp / "narration.mp3"))
            path = str(tmp / "avatar.mp4")
            Path(path).write_bytes(mp4)
            return path

        results = await asyncio.gather(
            gen_avatar(),
            *[_gen_broll(ctx, sc, i, total, tmp, video_id, reference_frame, sem)
              for i, sc in enumerate(broll_scenes)],
        )
        avatar_path = results[0]
        brolls = [b for b in results[1:] if b is not None]
        log.info(
            "fast generate stage %s",
            kv(video_id=video_id, stage="compose", broll_kept=len(brolls), broll_dropped=len(broll_scenes) - len(brolls)),
        )

        out = tmp / "fast.mp4"
        await media.compose_timeline(avatar_path, brolls, cues, str(out), settings.caption_font)
        await ctx.storage.put(fast_key, out.read_bytes(), "video/mp4")
        log.info(
            "fast generate render complete %s",
            kv(video_id=video_id, duration_ms=int((time.monotonic() - t0) * 1000), output_key=fast_key),
        )

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        v.status_fast = "ready"
        v.assets = {**v.assets, "fast": fast_key}
        v.script = script_json
        await s.commit()

    await publish(ctx.redis, video_id, "fast_ready", {
        "fast_url": await ctx.storage.presign_get(fast_key),
    })
    log.info("fast generate done %s", kv(video_id=video_id))


HANDLERS = {"avatar_prep": handle_avatar_prep, "fast_generate": handle_fast_generate}


async def process_one(ctx: WorkerContext) -> bool:
    msg = await read_next(ctx.redis, consumer=ctx.consumer)
    if msg is None:
        return False
    job_id = msg["job_id"]
    lane = msg["lane"]
    async with ctx.session_factory() as s:
        job = (
            await s.execute(select(Job).where(Job.id == job_id))
        ).scalar_one_or_none()
        if job is None:
            log.warning("orphan stream entry %s", kv(job_id=job_id, lane=lane))
            await ack(ctx.redis, lane, msg["msg_id"])
            return True
        job.status = "running"
        await s.commit()
        kind, payload = job.kind, dict(job.payload)
    entity_id = payload.get("avatar_id") or payload.get("video_id") or ""
    log.info("job started %s", kv(job_id=job_id, kind=kind, lane=lane, entity_id=entity_id))
    t0 = time.monotonic()
    try:
        await HANDLERS[kind](ctx, payload)
        status = "done"
    except Exception as exc:  # worker must survive any job failure
        err = _fmt_exc(exc)
        log.exception(
            "job failed %s",
            kv(job_id=job_id, kind=kind, entity_id=entity_id, duration_ms=int((time.monotonic() - t0) * 1000), error=err),
        )
        status = "failed"
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
            await publish(ctx.redis, entity_id, "failed", {"kind": kind, "error": err})
    else:
        log.info(
            "job done %s",
            kv(job_id=job_id, kind=kind, entity_id=entity_id, duration_ms=int((time.monotonic() - t0) * 1000)),
        )
    async with ctx.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.id == job_id))).scalar_one()
        job.status = status
        await s.commit()
    await ack(ctx.redis, lane, msg["msg_id"])
    return True


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
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
    log.info(
        "worker started %s",
        kv(consumer=ctx.consumer, redis_url=settings.redis_url, log_level=settings.log_level),
    )
    idle_ticks = 0
    while True:
        try:
            worked = await process_one(ctx)
        except Exception as exc:
            log.exception("worker loop error %s", kv(error=repr(exc)))
            await asyncio.sleep(1.0)
            continue
        if not worked:
            idle_ticks += 1
            if idle_ticks % 150 == 0:  # ~30s at 0.2s sleep
                log.debug("worker idle %s", kv(consumer=ctx.consumer))
            await asyncio.sleep(0.2)
        else:
            idle_ticks = 0


if __name__ == "__main__":
    asyncio.run(main())
