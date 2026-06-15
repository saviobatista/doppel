"""Voices: a reusable, manageable voice object. Clone from an avatar's footage
or from a recorded/uploaded sample → A/B provider candidates → select one."""
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from doppel_api.config import get_settings
from doppel_api.constants import VOICE_PREVIEW_LINE
from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import HEARTBEAT, sse_comment, sse_format, subscription
from doppel_api.models import Avatar, Device, Voice
from doppel_api.providers import voice as voice_tts
from doppel_api.queue import enqueue

router = APIRouter()

MAX_SAMPLE_BYTES = 128 * 1024 * 1024

# Preserve the uploaded container so ElevenLabs decodes it correctly.
AUDIO_EXTS = {"wav", "mp3", "m4a", "aac", "ogg", "oga", "opus", "flac", "webm", "mp4", "wma"}


async def _candidate_views(voice: Voice, storage) -> list[dict]:
    """Candidate cards with freshly presigned preview URLs (the stored ones expire)."""
    out = []
    for c in voice.candidates or []:
        view = {k: c.get(k) for k in ("provider", "label", "model", "external_id")}
        if c.get("preview_key"):
            view["preview_url"] = await storage.presign_get(c["preview_key"])
        out.append(view)
    return out


async def _voice_detail(voice: Voice, storage) -> dict:
    return {
        "voice_id": voice.id,
        "label": voice.label,
        "status": voice.status,
        "source": voice.source,
        "provider": voice.provider,
        "external_id": voice.external_id,
        "avatar_id": voice.avatar_id,
        "candidates": await _candidate_views(voice, storage),
        "created_at": voice.created_at.isoformat(),
    }


@router.post("/v1/voices", status_code=201)
async def create_voice(
    label: str = Form("Minha voz"),
    source: Literal["footage", "recorded", "uploaded"] = Form("recorded"),
    avatar_id: str | None = Form(None),
    sample: UploadFile | None = None,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
    redis=Depends(get_redis),
) -> dict:
    avatar = None
    if avatar_id:
        avatar = (
            await session.execute(
                select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
            )
        ).scalar_one_or_none()
        if avatar is None:
            raise HTTPException(status_code=404, detail="avatar not found")

    # Footage voice is ALREADY cloned at avatar prep — reuse it instead of making a
    # new ElevenLabs voice (avoids the account voice cap and is instant). The clone
    # job is only for fresh recorded/uploaded samples.
    if source == "footage" and sample is None:
        if avatar is None or not avatar.assets.get("voice_id"):
            raise HTTPException(status_code=422, detail="avatar has no cloned voice")
        external_id = avatar.assets["voice_id"]
        voice = Voice(
            device_id=device.id, avatar_id=avatar_id, label=label or "Minha voz",
            source="footage", status="ready", provider="elevenlabs", external_id=external_id,
            candidates=[{
                "provider": "elevenlabs", "label": "Da gravação",
                "model": get_settings().elevenlabs_model, "external_id": external_id,
            }],
            assets={"reused_from": "avatar"},
        )
        session.add(voice)
        await session.commit()
        return {"voice_id": voice.id, "status": "ready"}

    voice = Voice(
        device_id=device.id, avatar_id=avatar_id, label=label or "Minha voz", source=source,
        status="cloning",
    )
    session.add(voice)
    await session.flush()

    # Resolve the sample: an uploaded/recorded file, or the avatar's footage audio.
    if sample is not None:
        data = await sample.read(MAX_SAMPLE_BYTES + 1)
        if len(data) > MAX_SAMPLE_BYTES:
            raise HTTPException(status_code=413, detail="sample too large")
        fname = sample.filename or ""
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext not in AUDIO_EXTS:
            ctype = sample.content_type or ""
            ext = "wav" if ctype.endswith("wav") else "webm"
        sample_key = f"voices/{voice.id}/sample.{ext}"
        await storage.put(sample_key, data, sample.content_type or "audio/webm")
    elif source == "footage" and avatar is not None:
        # No prep clone yet but we have footage: clone from the raw recording.
        sample_key = avatar.assets.get("audio") or avatar.assets.get("source")
        if not sample_key:
            raise HTTPException(status_code=422, detail="avatar has no footage audio")
    else:
        raise HTTPException(status_code=422, detail="no voice sample provided")

    voice.assets = {"sample": sample_key}
    # enqueue COMMITS (voice row + assets) before notifying the stream
    await enqueue(redis, session, kind="voice_clone", lane="interactive",
                  payload={"voice_id": voice.id})
    return {"voice_id": voice.id}


@router.get("/v1/voices")
async def list_voices(
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Voice).where(Voice.device_id == device.id).order_by(Voice.created_at.desc())
    )
    voices = [
        {
            "voice_id": v.id, "label": v.label, "status": v.status, "source": v.source,
            "provider": v.provider, "external_id": v.external_id, "avatar_id": v.avatar_id,
            "candidate_count": len(v.candidates or []), "created_at": v.created_at.isoformat(),
        }
        for v in result.scalars()
    ]
    return {"voices": voices}


@router.get("/v1/voices/{voice_id}")
async def get_voice(
    voice_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    voice = (
        await session.execute(
            select(Voice).where(Voice.id == voice_id, Voice.device_id == device.id)
        )
    ).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404)
    return await _voice_detail(voice, storage)


@router.get("/v1/voices/{voice_id}/preview")
async def voice_preview(
    voice_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    """A playable preview URL for any voice. Reuses a candidate preview stored at
    clone time; for footage voices (no stored sample) it synthesizes one short
    line on first request and caches it so later plays are instant."""
    voice = (
        await session.execute(
            select(Voice).where(Voice.id == voice_id, Voice.device_id == device.id)
        )
    ).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404)

    key = (voice.assets or {}).get("preview_key")
    if not key:
        # Prefer the candidate matching the selected provider; else any with audio.
        cands = voice.candidates or []
        chosen = next(
            (c for c in cands
             if c.get("external_id") == voice.external_id and c.get("preview_key")),
            None,
        ) or next((c for c in cands if c.get("preview_key")), None)
        if chosen:
            key = chosen["preview_key"]

    if not key:
        external_id = voice.external_id or next(
            (c.get("external_id") for c in (voice.candidates or []) if c.get("external_id")), None
        )
        if not external_id:
            raise HTTPException(status_code=422, detail="voice has no synthesizable id")
        try:
            audio = await voice_tts.tts(external_id, VOICE_PREVIEW_LINE)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"preview synthesis failed: {exc}") from exc
        key = f"voices/{voice_id}/preview.mp3"
        await storage.put(key, audio, "audio/mpeg")
        voice.assets = {**(voice.assets or {}), "preview_key": key}
        await session.commit()

    return {"preview_url": await storage.presign_get(key)}


class VoiceSelect(BaseModel):
    provider: str
    model: str | None = None
    external_id: str | None = None


@router.post("/v1/voices/{voice_id}/select")
async def select_voice(
    voice_id: str,
    body: VoiceSelect,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    voice = (
        await session.execute(
            select(Voice).where(Voice.id == voice_id, Voice.device_id == device.id)
        )
    ).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404)
    chosen = next(
        (c for c in (voice.candidates or [])
         if c.get("provider") == body.provider
         and (body.model is None or c.get("model") == body.model)),
        None,
    )
    if chosen is None:
        raise HTTPException(status_code=422, detail="candidate not found")
    voice.provider = chosen["provider"]
    voice.external_id = chosen["external_id"]
    voice.assets = {**voice.assets, "selected_model": chosen.get("model")}
    # Attach the chosen voice to its avatar so downstream generation uses it.
    if voice.avatar_id:
        avatar = (
            await session.execute(select(Avatar).where(Avatar.id == voice.avatar_id))
        ).scalar_one_or_none()
        if avatar is not None:
            avatar.assets = {**avatar.assets, "voice_id": chosen["external_id"]}
    await session.commit()
    return await _voice_detail(voice, storage)


@router.get("/v1/voices/{voice_id}/events")
async def voice_events(
    voice_id: str,
    request: Request,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
    storage=Depends(get_storage),
):
    voice = (
        await session.execute(
            select(Voice).where(Voice.id == voice_id, Voice.device_id == device.id)
        )
    ).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404)
    await session.rollback()

    async def stream():
        async with subscription(redis, voice_id) as events_iter:
            async with request.app.state.session_factory() as snap_session:
                snap = (
                    await snap_session.execute(select(Voice).where(Voice.id == voice_id))
                ).scalar_one()
            yield sse_format("status", {"value": snap.status})
            if snap.status == "ready":
                yield sse_format("ready", {"candidates": await _candidate_views(snap, storage)})
                return
            if snap.status == "failed":
                return
            async for event, payload in events_iter:
                if event == HEARTBEAT:
                    yield sse_comment()
                    continue
                yield sse_format(event, payload)
                if event in ("ready", "failed"):
                    return

    return StreamingResponse(stream(), media_type="text/event-stream")
