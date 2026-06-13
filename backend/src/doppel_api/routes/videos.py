from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import HEARTBEAT, sse_comment, sse_format, subscription
from doppel_api.log import get_logger, kv
from doppel_api.models import Avatar, Device, Video
from doppel_api.queue import enqueue

router = APIRouter()
log = get_logger("videos")

MAX_BRIEFING_BYTES = 16 * 1024 * 1024


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]


@router.post("/v1/videos", status_code=201)
async def create_video(
    avatar_id: str = Form(...),
    briefing: UploadFile | None = None,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
    redis=Depends(get_redis),
) -> dict:
    result = await session.execute(
        select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="avatar not found")

    video = Video(device_id=device.id, avatar_id=avatar_id)
    session.add(video)
    await session.flush()
    if briefing is not None:
        data = await briefing.read(MAX_BRIEFING_BYTES + 1)
        if len(data) > MAX_BRIEFING_BYTES:
            raise HTTPException(status_code=413, detail="briefing too large")
        key = f"videos/{video.id}/briefing.webm"
        await storage.put(key, data, briefing.content_type or "audio/webm")
        video.assets = {"briefing": key}
    # enqueue COMMITS the session (video row + assets included)
    job = await enqueue(redis, session, kind="fast_generate", lane="interactive",
                  payload={"video_id": video.id})
    log.info(
        "video created %s",
        kv(video_id=video.id, avatar_id=avatar_id, job_id=job.id, has_briefing=briefing is not None),
    )
    return {"video_id": video.id}


@router.get("/v1/videos/{video_id}/events")
async def video_events(
    video_id: str,
    request: Request,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
    storage=Depends(get_storage),
):
    result = await session.execute(
        select(Video).where(Video.id == video_id, Video.device_id == device.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404)
    device_id = device.id
    # release the request-scoped connection; the stream uses its own short session
    await session.rollback()

    async def stream():
        log.info("video sse opened %s", kv(video_id=video_id, device_id=device_id))
        terminal = None
        try:
            # subscribe BEFORE reading the snapshot: no lost-event window
            async with subscription(redis, video_id) as events_iter:
                async with request.app.state.session_factory() as snap_session:
                    snap = (
                        await snap_session.execute(select(Video).where(Video.id == video_id))
                    ).scalar_one()
                data: dict = {"value": snap.status_fast}
                if snap.status_fast == "ready" and "fast" in snap.assets:
                    data["fast_url"] = await storage.presign_get(snap.assets["fast"])
                yield sse_format("status", data)
                if snap.status_fast in ("ready", "failed"):
                    terminal = snap.status_fast
                    return
                async for event, payload in events_iter:
                    if event == HEARTBEAT:
                        yield sse_comment()
                        continue
                    log.info("video sse event %s", kv(video_id=video_id, event=event, **payload))
                    yield sse_format(event, payload)
                    if event in ("fast_ready", "failed"):
                        terminal = event
                        return
        finally:
            log.info("video sse closed %s", kv(video_id=video_id, terminal=terminal))

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/v1/videos/{video_id}/feedback")
async def feedback(
    video_id: str,
    body: FeedbackIn,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
) -> dict:
    result = await session.execute(
        select(Video).where(Video.id == video_id, Video.device_id == device.id)
    )
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404)
    video.rating = body.rating
    if body.rating == "up":
        await session.commit()
        return {"video_id": video_id, "action": "gallery"}
    regen = Video(device_id=device.id, avatar_id=video.avatar_id)
    session.add(regen)
    await session.flush()
    # enqueue COMMITS (rating + regen row in one transaction)
    job = await enqueue(redis, session, kind="fast_generate", lane="interactive",
                  payload={"video_id": regen.id})
    log.info(
        "video regenerate %s",
        kv(source_video_id=video_id, video_id=regen.id, job_id=job.id),
    )
    return {"video_id": regen.id, "action": "regenerate"}


@router.get("/v1/gallery")
async def gallery(
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    result = await session.execute(
        select(Video).where(
            Video.device_id == device.id, Video.status_fast == "ready", Video.rating == "up"
        ).order_by(Video.created_at.desc())
    )
    videos = []
    for v in result.scalars():
        key = v.assets.get("fast")
        if key is None:
            continue  # corrupted row must not brick the gallery
        videos.append({
            "video_id": v.id,
            "created_at": v.created_at.isoformat(),
            "fast_url": await storage.presign_get(key),
        })
    return {"videos": videos}


@router.delete("/v1/me", status_code=204)
async def delete_me(
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> None:
    await session.execute(sql_delete(Video).where(Video.device_id == device.id))
    await session.execute(sql_delete(Avatar).where(Avatar.device_id == device.id))
    # merge is defensive: device comes from the same cached request session today,
    # but a future get_device refactor must not silently detach it
    merged = await session.merge(device)
    merged.deleted_at = datetime.now(UTC)
    await session.commit()
