"""Doppel generation worker: consumes jobs and drives the managed providers."""
import asyncio
import os
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api import cache
from doppel_api.config import get_settings
from doppel_api.constants import FEEDBACK_LINE, HELLO_LINE
from doppel_api.db import make_engine, make_session_factory
from doppel_api.events import publish
from doppel_api.models import Avatar, Job, Plan, Video, Voice
from doppel_api.providers import compose, flux2, identity, media, music, overlays
from doppel_api.providers import plan as plan_provider
from doppel_api.providers import research, script, sourcing, video, voice, voice_clone
from doppel_api.queue import ack, ensure_groups, read_next
from doppel_api.storage import S3Storage, Storage


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


async def _fabric_bytes(face_path: str, audio_path: str) -> bytes:
    face_url = await video.upload(face_path)
    audio_url = await video.upload(audio_path)
    return await media.fetch(await video.talking(face_url, audio_url))


async def _flux_bytes(prompt: str) -> bytes:
    return await media.fetch(await video.image(prompt))


async def _kling_bytes(image_path: str, motion: str) -> bytes:
    image_url = await video.upload(image_path)
    return await media.fetch(await video.broll(image_url, motion))


async def _flux2_bytes(prompt: str) -> bytes:
    return await flux2.generate(prompt)


async def _seedream_bytes(face_url: str, prompt: str) -> bytes:
    """Identity-lock image edit (fal seedream): person from the frame, new scene."""
    return await media.fetch(await video.edit_image(face_url, prompt))


async def _best_face_frame(src_path: str, tmp: Path) -> str:
    """Pick the avatar's first frame: sample candidate frames across the recording
    and let Claude Vision choose the most front-facing, centered, in-focus one
    (subject looking straight at the camera). Degrades to the plain t=1s frame."""
    settings = get_settings()
    out = str(tmp / "face.png")
    cands = await _safe(
        "candidate frames", media.extract_candidate_frames(src_path, str(tmp / "cand"), count=8))
    if cands and len(cands) > 1 and settings.anthropic_api_key:
        frames = [Path(p).read_bytes() for p in cands]  # noqa: ASYNC240
        idx = await _safe("pick best frame", script.pick_best_frame(frames))
        if isinstance(idx, int) and 0 <= idx < len(cands):
            print(f"avatar first frame: picked candidate #{idx}/{len(cands)}")
            if await _safe("transcode frame", media.transcode_image(cands[idx], out)):
                return out
    if cands and await _safe("transcode frame", media.transcode_image(cands[0], out)):
        return out
    # Ultimate fallback: the original single-frame extractor.
    return await media.extract_frame(src_path, out)


async def _generate_looks(
    ctx: "WorkerContext", avatar_id: str, face_bytes: bytes
) -> tuple[dict | None, str | None, list[dict]]:
    """Identity-lock orchestration: first frame -> face attributes -> identity-lock
    base prompt -> render N look options by swapping the scene block.

    Returns (face_attributes, identity_prompt, looks). Self-hosted FLUX.2 only
    (live cluster); any failure degrades gracefully so the avatar still goes ready.
    The identity_prompt is persisted and reused for every later scene generation.
    """
    settings = get_settings()
    if settings.broll_t2i_driver != "flux2" or not settings.broll_flux_api_base:
        return None, None, []
    try:
        await publish(ctx.redis, avatar_id, "progress", {"step": "generating_looks"})
        attrs = await cache.value(
            "face_attrs", [face_bytes],
            lambda: script.extract_face_attributes(face_bytes),
        )
        identity_prompt = identity.build_identity_prompt(attrs)

        looks: list[dict] = []
        for i, scene in enumerate(identity.LOOK_SCENES[: settings.avatar_looks_count]):
            final_prompt = identity.apply_scene(identity_prompt, scene["scene_block"])
            img_path = await cache.blob(
                "flux2", [final_prompt, "832x480"], "png",
                lambda p=final_prompt: _flux2_bytes(p),
            )
            img_bytes = Path(img_path).read_bytes()  # noqa: ASYNC240
            look_key = f"avatars/{avatar_id}/looks/{i}.png"
            await ctx.storage.put(look_key, img_bytes, "image/png")
            looks.append({
                "label": scene["label"],
                "scene_block": scene["scene_block"],
                "prompt": final_prompt,
                "key": look_key,
            })
        return attrs, identity_prompt, looks
    except Exception as exc:  # graceful degrade: keep the avatar, drop the looks
        print(f"avatar looks generation failed, skipping: {_fmt_exc(exc)}")
        return None, None, []


async def _ensure_avatar_looks(ctx: "WorkerContext", avatar_id: str, face_bytes: bytes) -> None:
    """Run the identity-lock orchestration once per avatar (at the first video
    generation — the future onboarding step). Idempotent and best-effort: never
    fails the video that triggers it.
    """
    try:
        async with ctx.session_factory() as s:
            avatar = (
                await s.execute(select(Avatar).where(Avatar.id == avatar_id))
            ).scalar_one()
            if avatar.assets.get("identity_prompt"):
                return  # already generated

        face_attrs, identity_prompt, looks = await _generate_looks(ctx, avatar_id, face_bytes)
        if not identity_prompt:
            return

        async with ctx.session_factory() as s:
            avatar = (
                await s.execute(select(Avatar).where(Avatar.id == avatar_id))
            ).scalar_one()
            avatar.assets = {
                **avatar.assets,
                "face_attributes": face_attrs,
                "identity_prompt": identity_prompt,
                "looks": looks,
            }
            await s.commit()
        await publish(ctx.redis, avatar_id, "looks_ready", {"count": len(looks)})
    except Exception as exc:  # onboarding looks must never break the video
        print(f"avatar looks step failed, continuing video: {_fmt_exc(exc)}")


async def _ensure_avatar_card_looks(
    ctx: "WorkerContext", avatar_id: str, face_bytes: bytes
) -> None:
    """Generate the avatar-card looks at creation: describe the first frame's
    environment, then edit the frame (seedream) into N looks of the same person in
    that space. Reuses the clone-extraction identity lock. Best-effort: never fails
    the avatar; publishes `looks_ready` and stores `looks` on the avatar.
    """
    settings = get_settings()
    if settings.avatar_looks_driver != "seedream" or not settings.fal_key:
        return
    try:
        async with ctx.session_factory() as s:
            avatar = (
                await s.execute(select(Avatar).where(Avatar.id == avatar_id))
            ).scalar_one()
            if avatar.assets.get("looks"):
                return  # already generated

        await publish(ctx.redis, avatar_id, "progress", {"step": "generating_looks"})
        attrs = await cache.value(
            "face_attrs", [face_bytes], lambda: script.extract_face_attributes(face_bytes)
        )
        environment = await cache.value(
            "face_env", [face_bytes], lambda: script.extract_environment(face_bytes)
        )
        identity_prompt = identity.build_identity_prompt(attrs)
        scenes = identity.look_scenes_for_environment(environment)[: settings.avatar_card_looks]

        with tempfile.TemporaryDirectory() as tmpdir:
            face_path = Path(tmpdir) / "face.png"
            await anyio.to_thread.run_sync(lambda: face_path.write_bytes(face_bytes))
            face_url = await video.upload(str(face_path))

            looks: list[dict] = []
            for i, scene in enumerate(scenes):
                final_prompt = identity.apply_scene(identity_prompt, scene["scene_block"])
                img_path = await cache.blob(
                    "seedream", [face_bytes, final_prompt], "png",
                    lambda fu=face_url, p=final_prompt: _seedream_bytes(fu, p),
                )
                img_bytes = await anyio.to_thread.run_sync(Path(img_path).read_bytes)
                look_key = f"avatars/{avatar_id}/looks/{i}.png"
                await ctx.storage.put(look_key, img_bytes, "image/png")
                looks.append({"label": scene["label"], "prompt": final_prompt, "key": look_key})

        if not looks:
            return
        async with ctx.session_factory() as s:
            avatar = (
                await s.execute(select(Avatar).where(Avatar.id == avatar_id))
            ).scalar_one()
            avatar.assets = {
                **avatar.assets,
                "face_attributes": attrs,
                "environment": environment,
                "identity_prompt": identity_prompt,
                "looks": looks,
            }
            await s.commit()
        await publish(ctx.redis, avatar_id, "looks_ready", {"count": len(looks)})
    except Exception as exc:  # onboarding looks must never break the avatar
        print(f"avatar card looks failed, continuing: {_fmt_exc(exc)}")


async def handle_avatar_prep(ctx: "WorkerContext", payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    settings = get_settings()
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        source_key = avatar.assets["source"]

    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    face_key = f"avatars/{avatar_id}/face.png"
    audio_key = f"avatars/{avatar_id}/audio.wav"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        source_bytes = await ctx.storage.get(source_key)
        ext = "mp4" if source_key.endswith(".mp4") else "webm"
        cache.put_blob("source", [avatar_id], ext, source_bytes)

        src = tmp / "source"
        src.write_bytes(source_bytes)
        face_path = await _best_face_frame(str(src), tmp)
        ref_path = await media.extract_audio(str(src), str(tmp / "ref.wav"))
        face_bytes = Path(face_path).read_bytes()  # noqa: ASYNC240
        ref_bytes = Path(ref_path).read_bytes()  # noqa: ASYNC240
        await ctx.storage.put(face_key, face_bytes, "image/png")
        # Extract + persist the recording audio (used for the voice clone, and
        # kept on the avatar for downstream lip-sync / re-voicing).
        await ctx.storage.put(audio_key, ref_bytes, "audio/wav")
        cache.put_blob("audio", [avatar_id], "wav", ref_bytes)

        voice_id = await cache.value(
            "clone", [ref_bytes],
            lambda: voice.clone(ref_path, name=f"doppel-{avatar_id[:8]}"),
        )
        model = settings.elevenlabs_model
        for line, key, name in (
            (HELLO_LINE, hello_key, f"{avatar_id}-hello"),
            (FEEDBACK_LINE, feedback_key, f"{avatar_id}-feedback"),
        ):
            audio_path = await cache.blob(
                "tts", [voice_id, line, model], "mp3",
                lambda v=voice_id, ln=line: voice.tts(v, ln),
            )
            audio_bytes = Path(audio_path).read_bytes()  # noqa: ASYNC240
            talk_path = await cache.blob(
                "fabric", [face_bytes, audio_bytes, "480p"], "mp4",
                lambda fp=face_path, ap=audio_path: _fabric_bytes(fp, ap),
            )
            talk_bytes = Path(talk_path).read_bytes()  # noqa: ASYNC240
            cache.save_render(name, "mp4", talk_bytes)  # human-friendly local copy
            await ctx.storage.put(key, talk_bytes, "video/mp4")

        # Idle "live" clip: the avatar holds eye contact and blinks while the user
        # decides what to do. Best-effort — the screen loops `hello` if it fails.
        idle_key: str | None = None
        try:
            silent = await media.silent_wav(str(tmp / "silence.wav"), 5.0)
            idle_path = await cache.blob(
                "fabric", [face_bytes, "idle-5s-silent"], "mp4",
                lambda fp=face_path, ap=silent: _fabric_bytes(fp, ap),
            )
            # Boomerang so the standby loop has no visible seam at the loop point.
            loop_path = await media.boomerang(idle_path, str(tmp / "idle_loop.mp4"))
            idle_bytes = Path(loop_path).read_bytes()  # noqa: ASYNC240
            idle_key = f"avatars/{avatar_id}/idle.mp4"
            await ctx.storage.put(idle_key, idle_bytes, "video/mp4")
        except Exception as exc:
            print(f"idle clip failed, continuing: {_fmt_exc(exc)}")

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {
            **avatar.assets,
            "face_image": face_key,
            "voice_id": voice_id,
            "audio": audio_key,
            "hello": hello_key,
            "feedback": feedback_key,
            **({"idle": idle_key} if idle_key else {}),
        }
        await s.commit()

    hello_payload = {
        "hello_url": await ctx.storage.presign_get(hello_key),
        "feedback_url": await ctx.storage.presign_get(feedback_key),
    }
    if idle_key:
        hello_payload["idle_url"] = await ctx.storage.presign_get(idle_key)
    await publish(ctx.redis, avatar_id, "hello_ready", hello_payload)

    # The avatar is usable now (voice screen proceeds); generate the card looks
    # afterwards so "ready" isn't delayed. Best-effort, publishes looks_ready.
    await _ensure_avatar_card_looks(ctx, avatar_id, face_bytes)


async def _gen_broll(ctx, scene, idx, total, video_id, sem) -> media.BrollClip | None:
    async with sem:
        try:
            prompt = scene.get("prompt", "")
            motion = scene.get("motion") or prompt
            img_path = await cache.blob(
                "flux", [prompt, "portrait_16_9"], "jpg", lambda p=prompt: _flux_bytes(p)
            )
            img_bytes = Path(img_path).read_bytes()  # noqa: ASYNC240
            clip_path = await cache.blob(
                "kling", [img_bytes, motion, "5"], "mp4",
                lambda ip=img_path, m=motion: _kling_bytes(ip, m),
            )
            await publish(ctx.redis, video_id, "progress",
                          {"step": f"component_{idx + 2}_of_{total}"})
            return media.BrollClip(
                path=clip_path, start=float(scene["start"]), end=float(scene["end"])
            )
        except Exception as exc:  # graceful degrade: drop this scene, keep the video
            print(f"broll scene {scene.get('id')} failed, dropping: {_fmt_exc(exc)}")
            return None


async def handle_fast_generate(ctx: "WorkerContext", payload: dict) -> None:
    video_id = payload["video_id"]
    settings = get_settings()

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        briefing_key = v.assets["briefing"]
        avatar_id = v.avatar_id
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        voice_id = avatar.assets["voice_id"]
        face_key = avatar.assets["face_image"]

    await publish(ctx.redis, video_id, "progress", {"step": "scripting"})
    target = settings.video_target_seconds

    briefing_bytes = await ctx.storage.get(briefing_key)
    with tempfile.TemporaryDirectory() as tmpdir:
        brief = Path(tmpdir) / "briefing"
        brief.write_bytes(briefing_bytes)
        transcript = await cache.value("stt", [briefing_bytes], lambda: voice.stt(str(brief)))
    script_json = await cache.value(
        "script", [transcript, str(target)],
        lambda: script.build_script(transcript, target),
    )

    await _render_from_script(ctx, video_id, script_json, voice_id, face_key, avatar_id)


async def _render_from_script(
    ctx: "WorkerContext", video_id: str, script_json: dict,
    voice_id: str, face_key: str, avatar_id: str,
) -> None:
    """Shared render: narration TTS + avatar lip-sync + b-roll + composite + persist.

    Drives both the spoken-briefing path (`fast_generate`) and the Video Agent
    plan path (`plan_generate`); the only difference upstream is how `script_json`
    was produced.
    """
    settings = get_settings()
    fast_key = f"videos/{video_id}/fast.mp4"
    model = settings.elevenlabs_model
    narration_text = script_json["narration"]["text"]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        async def _tts_ts_producer():
            audio, cues = await voice.tts_with_timestamps(voice_id, narration_text)
            return audio, [{"text": c.text, "start": c.start, "end": c.end} for c in cues]

        narration_path, cue_dicts = await cache.blob_with_meta(
            "tts_ts", [voice_id, narration_text, model], "mp3", _tts_ts_producer
        )
        cues = [media.CaptionCue(**c) for c in cue_dicts]

        face_bytes = await ctx.storage.get(face_key)
        face_path = tmp / "face.png"
        face_path.write_bytes(face_bytes)
        # First video for this avatar generates the identity-lock + look options
        # (future onboarding step). Idempotent and best-effort.
        await _ensure_avatar_looks(ctx, avatar_id, face_bytes)
        narration_bytes = Path(narration_path).read_bytes()  # noqa: ASYNC240

        broll_scenes = [sc for sc in script_json["scenes"] if sc["type"] == "broll"]
        total = 1 + len(broll_scenes)
        sem = asyncio.Semaphore(settings.pipeline_concurrency)

        async def gen_avatar() -> str:
            await publish(ctx.redis, video_id, "progress", {"step": f"component_1_of_{total}"})
            return await cache.blob(
                "fabric", [face_bytes, narration_bytes, "480p"], "mp4",
                lambda: _fabric_bytes(str(face_path), narration_path),
            )

        results = await asyncio.gather(
            gen_avatar(),
            *[_gen_broll(ctx, sc, i, total, video_id, sem)
              for i, sc in enumerate(broll_scenes)],
        )
        avatar_path = results[0]
        brolls = [b for b in results[1:] if b is not None]

        out = str(tmp / "fast.mp4")
        await media.compose_timeline(avatar_path, brolls, cues, out, settings.caption_font)
        final_bytes = Path(out).read_bytes()  # noqa: ASYNC240
        cache.save_render(video_id, "mp4", final_bytes)  # final video, friendly local name
        await ctx.storage.put(fast_key, final_bytes, "video/mp4")

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        v.status_fast = "ready"
        v.assets = {**v.assets, "fast": fast_key}
        v.script = script_json
        await s.commit()

    await publish(ctx.redis, video_id, "fast_ready", {
        "fast_url": await ctx.storage.presign_get(fast_key),
    })


_OVERLAY_KINDS = {
    "lower_third", "title_card", "stat_card", "scoreboard", "score_bug",
    "ticker", "timer", "quote", "bullet_list", "logo_bug",
}


def _resolve_anchor(anchor: str, scene_kind: str | None, has_cues: bool) -> str:
    """Keep overlays off the avatar's face and the caption band: an avatar scene
    never centers an overlay (covers the face), and captioned scenes don't drop
    one into the bottom band (collides with the subtitles)."""
    a = anchor or "lower"
    if scene_kind == "avatar" and a == "center":
        a = "upper"
    if has_cues and a == "bottom":
        a = "lower"
    return a


async def _overlay_clip_bytes(png: bytes, anchor: str, anim: str) -> bytes:
    """Render the overlay PNG to an animated black-background preview MP4."""
    with tempfile.TemporaryDirectory() as td:
        pin, pout = Path(td) / "ov.png", Path(td) / "ov.mp4"
        pin.write_bytes(png)
        await compose.render_overlay_preview(str(pin), str(pout), anchor=anchor, anim=anim)
        return pout.read_bytes()


def _backfill_resources(artifact: dict) -> None:
    """Guarantee the Resources panel is populated: derive design_elements from the
    overlay ids referenced in scenes and media from broll scene prompts whenever
    the model left those manifests empty. Model-provided entries are preserved.
    """
    res = artifact.setdefault("resources", {})
    scenes = (artifact.get("script") or {}).get("scenes", [])

    defined = {d.get("id"): d for d in (res.get("design_elements") or []) if d.get("id")}
    for sc in scenes:
        for ov in sc.get("overlays") or []:
            if ov in defined:
                continue
            stub = ov.removeprefix("overlay_").removeprefix("design_")
            kind = next((k for k in _OVERLAY_KINDS if k in stub), "title_card")
            label = stub.replace("_", " ").strip().title() or "Overlay"
            # No model-provided content here: seed it from the scene's real
            # on-screen text so the overlay is still dynamic, not just the id.
            content = {"title": sc["on_screen_text"]} if sc.get("on_screen_text") else {}
            defined[ov] = {"id": ov, "label": label, "kind": kind, "content": content}
    if defined:
        res["design_elements"] = list(defined.values())

    if not res.get("media"):
        media_items = []
        for sc in scenes:
            direction = sc.get("direction") or {}
            prompt = direction.get("b_roll_prompt")
            if sc.get("kind") == "broll" and prompt:
                media_items.append({
                    "label": sc.get("title") or sc.get("id"),
                    "kind": "image",
                    "prompt": prompt,
                    "search_query": sc.get("on_screen_text") or sc.get("title"),
                    "scene_id": sc.get("id"),
                })
        if media_items:
            res["media"] = media_items


async def _media_still_bytes(prompt: str) -> bytes:
    return await media.fetch(await video.image(prompt, "portrait_16_9"))


async def _safe(label: str, coro):
    try:
        return await coro
    except Exception as exc:
        print(f"{label} failed: {_fmt_exc(exc)}")
        return None


async def _store(ctx, key: str, data: bytes, content_type: str, local: str, ext: str) -> str:
    await ctx.storage.put(key, data, content_type)
    cache.save_render(local, ext, data)
    return await ctx.storage.presign_get(key)


async def _materialize_resources(ctx: "WorkerContext", plan_id: str, artifact: dict) -> None:
    """Turn the resource MANIFEST into real assets, all stored in S3 (presigned
    `preview_url`) and saved to local renders/ for inspection. Best-effort:

      - media images: scrape-first (SerpAPI real photos) with fal-generation
        fallback, chosen by meta.media_strategy;
      - design-element overlays: Pillow-rendered PNGs (dynamic per plan);
      - real footage: a couple of YouTube Shorts for the topic (yt-dlp);
      - background music: 3 candidates (fal / ElevenLabs / scraped) to A/B.
    """
    settings = get_settings()
    resources = artifact.setdefault("resources", {})
    meta = artifact.get("meta") or {}
    strategy = meta.get("media_strategy", "generate")
    can_scrape = bool(settings.serpapi_key)
    sem = asyncio.Semaphore(settings.pipeline_concurrency)
    used_urls: set[str] = set()  # cross-scene dedup so two scenes never reuse a photo
    used_lock = asyncio.Lock()

    async def _do_media(i: int, item: dict) -> None:
        # Every manifest item gets a still preview (scraped or generated). Real
        # video clips are appended separately by the YouTube step.
        query = item.get("search_query") or item.get("label") or item.get("prompt")
        gen_prompt = item.get("prompt") or query
        description = " — ".join(x for x in (item.get("label"), item.get("prompt")) if x) or query
        async with sem:
            data, source = None, None
            if strategy in ("scrape", "hybrid") and can_scrape and query:
                async with used_lock:
                    exclude = set(used_urls)
                picked = await _safe(f"media scrape {i}", sourcing.choose_image(
                    query, description, exclude_urls=exclude,
                    vision=settings.media_vision_select))
                if picked:
                    data, cand = picked
                    source, item["source_link"] = "scraped", cand.get("link")
                    if cand.get("url"):
                        async with used_lock:
                            used_urls.add(cand["url"])
            if data is None and gen_prompt:
                p = await _safe(
                    f"media still {i}",
                    cache.blob("media_still", [gen_prompt], "jpg",
                               lambda pr=gen_prompt: _media_still_bytes(pr)),
                )
                if p:
                    data, source = Path(p).read_bytes(), "generated"  # noqa: ASYNC240
            if data is None:
                return
            item["preview_url"] = await _store(
                ctx, f"plans/{plan_id}/media/{i}.jpg", data, "image/jpeg",
                f"plan-{plan_id}/media-{i}", "jpg")
            item["key"], item["source"] = f"plans/{plan_id}/media/{i}.jpg", source

    theme = artifact.get("overlay_style") or None

    async def _do_overlay(el: dict) -> None:
        el_id = el.get("id") or "el"
        png = await _safe(f"overlay {el_id}", anyio.to_thread.run_sync(
            lambda: overlays.render(
                el.get("kind", "title_card"), el.get("label", ""), el.get("content") or {},
                theme=theme, accent=el.get("accent"))))
        if not png:
            return
        key = f"plans/{plan_id}/overlays/{el_id}.png"
        # Still PNG: composited into scenes (el["key"]) and used as the clip poster.
        el["preview_url"] = await _store(
            ctx, key, png, "image/png", f"plan-{plan_id}/overlay-{el_id}", "png")
        el["key"] = key
        # Animated preview on a black 9:16 frame — exactly how it will animate/sit
        # in the final video — so the plan panel previews the real element.
        clip = await _safe(f"overlay clip {el_id}", _overlay_clip_bytes(
            png, el.get("placement") or "lower", el.get("animation") or "fade"))
        if clip:
            ckey = f"plans/{plan_id}/overlays/{el_id}.mp4"
            el["clip_url"] = await _store(
                ctx, ckey, clip, "video/mp4", f"plan-{plan_id}/overlay-{el_id}", "mp4")

    await asyncio.gather(
        *[_do_media(i, it) for i, it in enumerate(resources.get("media") or [])],
        *[_do_overlay(el) for el in resources.get("design_elements") or []],
    )

    # Footage links are fast (a SerpAPI call + thumbnails); music is slow and is
    # generated AFTER the plan goes ready (see _generate_music), so it never blocks.
    footage = await _fetch_youtube_links(ctx, plan_id, artifact)
    if footage:
        resources["footage"] = footage


async def _fetch_youtube_links(ctx, plan_id: str, artifact: dict) -> list[dict]:
    """Real, recent YouTube videos for the topic as LINKS + thumbnails (via SerpAPI).
    The actual video is NOT downloaded here — that is deferred to generation time."""
    settings = get_settings()
    if settings.youtube_shorts_count <= 0:
        return []
    lang = (artifact.get("meta") or {}).get("language", "pt-BR")
    # Prefer the planner's concrete, real-world query; fall back to the title.
    query = (artifact.get("footage_query") or "").strip() or \
        f"{artifact.get('title') or ''} melhores momentos".strip()
    vids = await sourcing.search_youtube(query, n=settings.youtube_shorts_count, language=lang)
    out: list[dict] = []
    for j, v in enumerate(vids):
        preview, thumb_key = None, None
        thumb = await sourcing.fetch_thumbnail(v.get("thumbnail"))
        if thumb:
            thumb_key = f"plans/{plan_id}/footage/{j}.jpg"
            preview = await _safe(f"footage thumb {j}", _store(
                ctx, thumb_key, thumb, "image/jpeg", f"plan-{plan_id}/footage-{j}", "jpg"))
        out.append({
            "label": v.get("title") or f"Clipe {j + 1}", "kind": "video", "source": "youtube",
            "video_url": v.get("link"), "source_link": v.get("link"), "preview_url": preview,
            "thumb_key": thumb_key if preview else None,
            "channel": v.get("channel"), "published": v.get("published"),
            "views": v.get("views"), "length": v.get("length"), "deferred": True,
        })
    return out


async def _build_bundle(ctx, plan_id: str, artifact: dict) -> dict:
    """Finalize the session's artifact: snapshot the plan JSON to S3 and assemble a
    durable manifest of every asset key. Stored on plan.bundle and revisitable.
    """
    import json as _json

    res = artifact.get("resources") or {}
    assets: list[dict] = []
    for it in res.get("media") or []:
        if it.get("key"):
            assets.append({"kind": "media", "key": it["key"], "label": it.get("label"),
                           "content_type": "image/jpeg"})
    for el in res.get("design_elements") or []:
        if el.get("key"):
            assets.append({"kind": "overlay", "key": el["key"], "label": el.get("label"),
                           "content_type": "image/png"})
    for tr in res.get("audio") or []:
        if tr.get("key"):
            assets.append({"kind": "audio", "key": tr["key"], "label": tr.get("label"),
                           "content_type": "audio/mpeg"})
    for fo in res.get("footage") or []:
        if fo.get("thumb_key"):
            assets.append({"kind": "footage_thumb", "key": fo["thumb_key"],
                           "label": fo.get("label"), "content_type": "image/jpeg"})

    plan_key = f"plans/{plan_id}/bundle/plan.json"
    await _safe("bundle plan snapshot", ctx.storage.put(
        plan_key, _json.dumps(artifact, ensure_ascii=False).encode("utf-8"),
        "application/json"))

    return {
        "plan_id": plan_id,
        "title": artifact.get("title"),
        "plan_key": plan_key,
        "counts": {
            "scenes": len((artifact.get("script") or {}).get("scenes") or []),
            "media": len(res.get("media") or []),
            "overlays": len(res.get("design_elements") or []),
            "audio": len(res.get("audio") or []),
            "footage": len(res.get("footage") or []),
        },
        "assets": assets,
        "language": (artifact.get("meta") or {}).get("language"),
    }


async def _generate_music(ctx, plan_id: str, artifact: dict, bundle: dict) -> None:
    """Post-ready: generate the 3 music candidates, persist them into the plan's
    resources + bundle, and stream them to the client via an `audio` SSE event.
    Best-effort: failures just leave the plan without tracks."""
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    tracks = await _fetch_music(ctx, plan_id, artifact)
    if not tracks:
        return
    async with ctx.session_factory() as s:
        p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one_or_none()
        if p is None:
            return
        # Deep-copy: a shallow copy shares the nested `resources`/`assets` objects, so
        # SQLAlchemy's JSON column would not register the in-place mutation as dirty.
        plan_json = copy.deepcopy(p.plan or artifact)
        plan_json.setdefault("resources", {})["audio"] = tracks
        bundle_json = copy.deepcopy(p.bundle or bundle)
        assets = [a for a in (bundle_json.get("assets") or []) if a.get("kind") != "audio"]
        assets += [{"kind": "audio", "key": t["key"], "label": t.get("label"),
                    "content_type": "audio/mpeg"} for t in tracks if t.get("key")]
        bundle_json["assets"] = assets
        bundle_json.setdefault("counts", {})["audio"] = len(tracks)
        p.plan = plan_json
        p.bundle = bundle_json
        flag_modified(p, "plan")
        flag_modified(p, "bundle")
        await s.commit()
    await publish(ctx.redis, plan_id, "audio", {"audio": tracks})


async def _fetch_music(ctx, plan_id: str, artifact: dict) -> list[dict]:
    m = (artifact.get("audio") or {}).get("music") or {}
    mood = m.get("mood") or "energetic"
    prompt = m.get("prompt") or (
        f"{mood} instrumental background music, {int(m.get('bpm') or 120)} BPM, "
        "for a short social video"
    )
    fal_b, el_b = await asyncio.gather(
        _safe("fal music", music.fal_music(prompt)),
        _safe("elevenlabs music", music.elevenlabs_music(prompt)),
    )
    out: list[dict] = []
    blobs = [
        ("fal", "fal Stable Audio", fal_b, None),
        ("elevenlabs", "ElevenLabs Music", el_b, None),
    ]
    for source, label, data, link in blobs:
        if not data:
            continue
        url = await _store(ctx, f"plans/{plan_id}/audio/{source}.mp3", data, "audio/mpeg",
                           f"plan-{plan_id}/music-{source}", "mp3")
        out.append({"label": label, "source": source, "kind": "music",
                    "preview_url": url, "key": f"plans/{plan_id}/audio/{source}.mp3",
                    "source_link": link})
    return out


async def handle_plan_build(ctx: "WorkerContext", payload: dict) -> None:
    plan_id = payload["plan_id"]
    async with ctx.session_factory() as s:
        p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one()
        brief = dict(p.brief)
        avatar_id = p.avatar_id

    prompt = brief.get("prompt", "")
    language = brief.get("language") or "pt-BR"
    duration = int(brief.get("duration_seconds") or 40)
    orientation = brief.get("orientation") or "portrait"
    avatar_label = brief.get("avatar_label") or "Avatar"
    voice_label = brief.get("voice_label") or avatar_label

    try:
        await publish(ctx.redis, plan_id, "progress", {"step": "researching"})
        # Not cached: research is time-sensitive (a cached result serves stale news,
        # e.g. yesterday's game), and the agent should re-evaluate each run.
        research_out = await research.research(prompt, language=language)
        await publish(ctx.redis, plan_id, "research", {
            "sources": research_out.get("sources", []),
            "text": research_out.get("text", ""),
        })

        await publish(ctx.redis, plan_id, "progress", {"step": "scripting"})

        async def _emit_partial(partial: dict) -> None:
            await publish(ctx.redis, plan_id, "plan_partial", {"plan": partial})

        artifact = await plan_provider.build_plan(
            prompt, research_out, duration_seconds=duration, orientation=orientation,
            language=language, avatar_label=avatar_label, voice_label=voice_label,
            on_partial=_emit_partial,
        )
        artifact.setdefault("meta", {}).update({
            "duration_seconds": duration, "orientation": orientation, "language": language,
        })
        _backfill_resources(artifact)
        resources = artifact["resources"]
        if avatar_id:
            resources["avatars"] = [{"id": avatar_id, "label": avatar_label}]
        resources["voices"] = [{"id": brief.get("voice_id") or "", "label": voice_label}]

        # Materialize the manifest into real, inspectable assets before going ready.
        await publish(ctx.redis, plan_id, "progress", {"step": "rendering_assets"})
        await _materialize_resources(ctx, plan_id, artifact)
        # Finalize the session's durable artifact bundle (manifest + plan snapshot).
        bundle = await _build_bundle(ctx, plan_id, artifact)

        async with ctx.session_factory() as s:
            p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one()
            p.plan = artifact
            p.bundle = bundle
            p.status = "ready"
            await s.commit()

        await publish(ctx.redis, plan_id, "plan", {"plan": artifact})
        await publish(ctx.redis, plan_id, "ready", {})

        # Music is the slowest asset; generate it AFTER ready so the artifact shows
        # immediately, then stream the tracks in. Best-effort: never fails the plan.
        await _generate_music(ctx, plan_id, artifact, bundle)
    except Exception:
        import traceback
        traceback.print_exc()
        async with ctx.session_factory() as s:
            p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one()
            p.status = "failed"
            await s.commit()
        await publish(ctx.redis, plan_id, "failed", {"step": "plan_build"})
        raise


@dataclass
class GenConfig:
    """Per-run generation drivers — resolved from settings, then overridden by the
    request's `model_overrides`. The swappable seam for the user's open-weight
    models (Starya cluster): each capability picks an implementation by name."""

    tts: str
    lipsync: str
    i2v: str
    music: str
    t2i: str
    music_gain: float
    duck: bool


def _gen_config(overrides: dict | None) -> GenConfig:
    s = get_settings()
    o = overrides or {}
    return GenConfig(
        tts=o.get("tts_driver", s.tts_driver),
        lipsync=o.get("lipsync_driver", s.lipsync_driver),
        i2v=o.get("i2v_driver", s.i2v_driver),
        music=o.get("music_driver", s.music_driver),
        t2i=o.get("t2i_driver", s.t2i_driver),
        music_gain=float(o.get("music_gain", s.music_gain)),
        duck=bool(o.get("ducking", True)),
    )


async def _key_to_tmp(ctx, tmp: Path, key: str, name: str) -> str:
    """Pull a durable S3 asset down to a local temp file for ffmpeg."""
    data = await ctx.storage.get(key)
    path = tmp / name
    await anyio.to_thread.run_sync(lambda: path.write_bytes(data))
    return str(path)


async def _scene_tts(
    voice_id: str, text: str, tts_sem: asyncio.Semaphore
) -> tuple[str, list[media.CaptionCue]]:
    model = get_settings().elevenlabs_model

    async def _producer() -> tuple[bytes, list[dict]]:
        # ElevenLabs caps concurrent requests (3 on this tier) — gate the actual
        # network call so a wide scene fan-out never trips the rate limit.
        async with tts_sem:
            audio, cues = await voice.tts_with_timestamps(voice_id, text)
        return audio, [{"text": c.text, "start": c.start, "end": c.end} for c in cues]

    path, cue_dicts = await cache.blob_with_meta(
        "tts_ts", [voice_id, text, model], "mp3", _producer
    )
    return path, [media.CaptionCue(**c) for c in cue_dicts]


async def _scene_still(
    ctx, tmp: Path, sid: str, scene: dict, media_by_scene: dict, cfg: GenConfig, face_path: str
) -> str:
    """The still a b-roll scene pans over: the scene's scraped/materialized image,
    else a freshly generated one, else the avatar frame as a safe fallback."""
    m = media_by_scene.get(sid)
    if m and m.get("key"):
        got = await _safe(
            f"scene still {sid}", _key_to_tmp(ctx, tmp, m["key"], f"still_{sid}.jpg"))
        return got or face_path
    direction = scene.get("direction") or {}
    prompt = direction.get("b_roll_prompt") or scene.get("on_screen_text") or scene.get("title")
    if prompt and cfg.t2i == "fal":
        p = await _safe(
            f"scene gen still {sid}",
            cache.blob("media_still", [prompt], "jpg", lambda: _media_still_bytes(prompt)),
        )
        if p:
            return p
    return face_path


async def _build_scene(
    ctx, tmp: Path, scene: dict, idx: int, total: int, video_id: str, voice_id: str,
    face_path: str, face_bytes: bytes, media_by_scene: dict, overlays_by_id: dict,
    cfg: GenConfig, sem: asyncio.Semaphore, tts_sem: asyncio.Semaphore,
) -> compose.Segment:
    """Render one scene to a normalized clip: per-scene TTS for real timing/captions,
    a talking-avatar (lip-sync) or Ken-Burns b-roll visual, the scene's overlay PNG
    and burned captions."""
    async with sem:
        sid = scene.get("id") or f"scene_{idx + 1}"
        settings = get_settings()
        text = (scene.get("narration") or "").strip()

        cues: list[media.CaptionCue] = []
        audio_path: str | None = None
        dur = float(scene.get("duration_seconds") or 5)
        if text and cfg.tts == "elevenlabs":
            audio_path, cues = await _scene_tts(voice_id, text, tts_sem)
            dur = await compose.probe_duration(audio_path) or dur

        overlay_png = None
        ov_anchor, ov_anim = "lower", "fade"
        for ov_id in scene.get("overlays") or []:
            el = overlays_by_id.get(ov_id)
            if el and el.get("key"):
                overlay_png = await _safe(
                    f"overlay {ov_id}", _key_to_tmp(ctx, tmp, el["key"], f"ov_{sid}.png"))
                ov_anchor = _resolve_anchor(
                    el.get("placement") or "lower", scene.get("kind"), bool(cues))
                ov_anim = el.get("animation") or "fade"
                break

        spec = compose.SceneSpec(
            out_path=str(tmp / f"scene_{idx:02d}.mp4"), duration=dur, audio_path=audio_path,
            overlay_png=overlay_png, overlay_anchor=ov_anchor, overlay_anim=ov_anim,
            cues=cues, kb_index=idx, font=settings.caption_font,
        )
        if scene.get("kind") == "avatar" and cfg.lipsync == "fabric" and audio_path:
            audio_bytes = Path(audio_path).read_bytes()  # noqa: ASYNC240
            spec.video_path = await cache.blob(
                "fabric", [face_bytes, audio_bytes, "480p"], "mp4",
                lambda ap=audio_path: _fabric_bytes(face_path, ap),
            )
        else:
            spec.image_path = await _scene_still(
                ctx, tmp, sid, scene, media_by_scene, cfg, face_path)

        await compose.render_scene(spec)
        await publish(ctx.redis, video_id, "progress",
                      {"step": f"scene_{idx + 1}_of_{total}"})
        trans = scene.get("transition_out") or {}
        return compose.Segment(
            path=spec.out_path, duration=dur,
            transition=trans.get("type") or "cut",
            trans_dur=float(trans.get("duration_seconds") or 0.4),
        )


async def _pick_music(
    ctx, tmp: Path, artifact: dict, selections: dict, cfg: GenConfig
) -> str | None:
    tracks = (artifact.get("resources") or {}).get("audio") or []
    pinned = selections.get("music_key")
    chosen = (
        next((t for t in tracks if t.get("key") == pinned), None)
        or next((t for t in tracks if t.get("source") == cfg.music and t.get("key")), None)
        or next((t for t in tracks if t.get("key")), None)
    )
    if not chosen:
        return None
    return await _safe("music fetch", _key_to_tmp(ctx, tmp, chosen["key"], "music.mp3"))


async def _render_plan(
    ctx: "WorkerContext", plan_id: str, video_id: str, artifact: dict,
    voice_id: str, face_key: str, selections: dict, cfg: GenConfig,
) -> None:
    """Phase-1 plan render: build a clip per scene (parallel, best-effort timing),
    xfade-concat them on their planned transitions, then mix the chosen music
    under the voiceover with ducking. Outputs an MP4 → S3 → `fast_ready` SSE."""
    settings = get_settings()
    scenes = (artifact.get("script") or {}).get("scenes") or []
    res = artifact.get("resources") or {}
    media_by_scene = {m["scene_id"]: m for m in (res.get("media") or []) if m.get("scene_id")}
    overlays_by_id = {e["id"]: e for e in (res.get("design_elements") or []) if e.get("id")}
    ducking = bool((artifact.get("audio") or {}).get("ducking", True)) and cfg.duck
    fast_key = f"videos/{video_id}/fast.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        face_bytes = await ctx.storage.get(face_key)
        face_path = str(tmp / "face.png")
        await anyio.to_thread.run_sync(lambda: Path(face_path).write_bytes(face_bytes))

        total = len(scenes)
        sem = asyncio.Semaphore(settings.pipeline_concurrency)
        tts_sem = asyncio.Semaphore(2)  # stay under the ElevenLabs concurrency cap
        await publish(ctx.redis, video_id, "progress", {"step": "narration"})
        segments = await asyncio.gather(*[
            _build_scene(ctx, tmp, sc, i, total, video_id, voice_id, face_path, face_bytes,
                         media_by_scene, overlays_by_id, cfg, sem, tts_sem)
            for i, sc in enumerate(scenes)
        ])
        if not segments:
            raise RuntimeError("plan has no scenes to render")

        await publish(ctx.redis, video_id, "progress", {"step": "compositing"})
        composite = str(tmp / "composite.mp4")
        await compose.concat_transitions(list(segments), composite)

        out = composite
        music_path = await _pick_music(ctx, tmp, artifact, selections, cfg)
        if music_path:
            await publish(ctx.redis, video_id, "progress", {"step": "mixing_audio"})
            mixed = str(tmp / "final.mp4")
            ok = await _safe("music mix", compose.mix_music(
                composite, music_path, mixed, gain=cfg.music_gain, duck=ducking))
            if ok:
                out = mixed

        final_bytes = Path(out).read_bytes()  # noqa: ASYNC240
        cache.save_render(video_id, "mp4", final_bytes)
        await ctx.storage.put(fast_key, final_bytes, "video/mp4")

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        v.status_fast = "ready"
        v.assets = {**v.assets, "fast": fast_key}
        await s.commit()
    await publish(ctx.redis, video_id, "fast_ready", {
        "fast_url": await ctx.storage.presign_get(fast_key),
    })


async def handle_plan_generate(ctx: "WorkerContext", payload: dict) -> None:
    plan_id = payload["plan_id"]
    video_id = payload["video_id"]
    selections = payload.get("selections") or {}
    cfg = _gen_config(payload.get("model_overrides"))
    async with ctx.session_factory() as s:
        p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one()
        artifact = dict(p.plan or {})
        avatar_id = p.avatar_id
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        voice_id = avatar.assets["voice_id"]
        face_key = avatar.assets["face_image"]
        # A picker voice (a reusable Voice object) overrides the avatar's own voice.
        brief_voice = (p.brief or {}).get("voice_id")
        if brief_voice and brief_voice != voice_id:
            v = (await s.execute(
                select(Voice).where(Voice.id == brief_voice, Voice.device_id == avatar.device_id)
            )).scalar_one_or_none()
            if v and v.status == "ready" and v.external_id:
                voice_id = v.external_id
                print(f"plan {plan_id}: using selected voice {v.id} ({v.label})")
        # A picked look swaps the first frame: the avatar is rendered wearing that
        # look instead of the raw recording frame.
        look_index = (p.brief or {}).get("look_index")
        if look_index is not None:
            looks = avatar.assets.get("looks") or []
            if 0 <= look_index < len(looks) and looks[look_index].get("key"):
                face_key = looks[look_index]["key"]
                print(f"plan {plan_id}: using look #{look_index} ({face_key}) as first frame")

    try:
        await _render_plan(ctx, plan_id, video_id, artifact, voice_id, face_key, selections, cfg)
    except Exception:
        async with ctx.session_factory() as s:
            p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one()
            p.status = "ready"  # generation failed; the plan itself is still good
            await s.commit()
        raise

    async with ctx.session_factory() as s:
        p = (await s.execute(select(Plan).where(Plan.id == plan_id))).scalar_one()
        p.status = "generated"
        await s.commit()


async def _avatar_voice_keep_ids(ctx: "WorkerContext") -> set[str]:
    """External voice ids still referenced by any avatar/voice — never prune these."""
    keep: set[str] = set()
    async with ctx.session_factory() as s:
        for a in (await s.execute(select(Avatar))).scalars():
            vid = (a.assets or {}).get("voice_id")
            if vid:
                keep.add(vid)
        for v in (await s.execute(select(Voice))).scalars():
            if v.external_id:
                keep.add(v.external_id)
            for c in v.candidates or []:
                if c.get("external_id"):
                    keep.add(c["external_id"])
    return keep


async def _clone_with_capacity(ctx: "WorkerContext", sample_path: str) -> str:
    """Instant-clone the sample; if the EL voice cap is hit, prune our orphaned
    voices (those not referenced in the DB) and retry once."""
    try:
        return await voice.clone(sample_path, name="doppel-voice")
    except Exception as exc:
        print(f"voice clone failed ({exc!r}); pruning orphaned EL voices and retrying")
        try:
            deleted = await voice.prune_orphans(await _avatar_voice_keep_ids(ctx))
            print(f"pruned {deleted} orphaned EL voices")
        except Exception as prune_exc:
            print(f"prune failed: {prune_exc!r}")
        return await voice.clone(sample_path, name="doppel-voice")


async def handle_voice_clone(ctx: "WorkerContext", payload: dict) -> None:
    """Clone the voice sample into provider/model candidates for the A/B review.
    Stores each preview MP3 in S3 and on `voice.candidates`, then goes `ready`.
    """
    voice_id = payload["voice_id"]
    async with ctx.session_factory() as s:
        v = (await s.execute(select(Voice).where(Voice.id == voice_id))).scalar_one()
        sample_key = v.assets["sample"]

    await publish(ctx.redis, voice_id, "progress", {"step": "cloning_voice"})
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        raw = tmp / "sample.in"
        sample_bytes = await ctx.storage.get(sample_key)
        await anyio.to_thread.run_sync(lambda: raw.write_bytes(sample_bytes))
        # Normalize any container (webm/opus, mp4, wav) to a clean mono wav the
        # clone APIs reliably accept.
        wav = await media.extract_audio(str(raw), str(tmp / "sample.wav"))
        external_id = await _clone_with_capacity(ctx, wav)
        candidates = await voice_clone.elevenlabs_previews(external_id)
        fish = await voice_clone.fish_candidate(wav)
        if fish:
            candidates.append(fish)

        stored: list[dict] = []
        for i, c in enumerate(candidates):
            preview_key = f"voices/{voice_id}/preview-{i}.mp3"
            await _store(ctx, preview_key, c["preview_bytes"], "audio/mpeg",
                         f"voice-{voice_id}-{i}", "mp3")
            stored.append({
                "provider": c["provider"], "label": c["label"], "model": c["model"],
                "external_id": c["external_id"], "preview_key": preview_key,
            })

    if not stored:
        async with ctx.session_factory() as s:
            v = (await s.execute(select(Voice).where(Voice.id == voice_id))).scalar_one()
            v.status = "failed"
            await s.commit()
        await publish(ctx.redis, voice_id, "failed", {"kind": "voice_clone"})
        raise RuntimeError("no voice candidates produced")

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Voice).where(Voice.id == voice_id))).scalar_one()
        v.candidates = stored
        v.status = "ready"
        await s.commit()

    views = [{
        "provider": c["provider"], "label": c["label"], "model": c["model"],
        "external_id": c["external_id"],
        "preview_url": await ctx.storage.presign_get(c["preview_key"]),
    } for c in stored]
    await publish(ctx.redis, voice_id, "ready", {"candidates": views})


HANDLERS = {
    "avatar_prep": handle_avatar_prep,
    "fast_generate": handle_fast_generate,
    "plan_build": handle_plan_build,
    "plan_generate": handle_plan_generate,
    "voice_clone": handle_voice_clone,
}


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
        print(f"job {msg['job_id']} ({kind}) failed: {_fmt_exc(exc)}")
        status = "failed"
        entity_id = (
            payload.get("avatar_id") or payload.get("video_id") or payload.get("voice_id") or ""
        )
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
            elif "voice_id" in payload:
                vc = (
                    await s.execute(select(Voice).where(Voice.id == payload["voice_id"]))
                ).scalar_one_or_none()
                if vc is not None:
                    vc.status = "failed"
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
