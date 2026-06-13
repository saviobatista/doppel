from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import sse_format, subscription
from doppel_api.models import Avatar, Device, Video
from doppel_api.queue import enqueue

router = APIRouter()


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
        key = f"videos/{video.id}/briefing.webm"
        await storage.put(key, await briefing.read(), briefing.content_type or "audio/webm")
        video.assets = {"briefing": key}
    # enqueue COMMITS the session (video row + assets included)
    await enqueue(redis, session, kind="fast_generate", lane="interactive",
                  payload={"video_id": video.id})
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
    # release the request-scoped connection; the stream uses its own short session
    await session.rollback()

    async def stream():
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
                return
            async for event, payload in events_iter:
                yield sse_format(event, payload)
                if event in ("fast_ready", "failed"):
                    return

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
    await enqueue(redis, session, kind="fast_generate", lane="interactive",
                  payload={"video_id": regen.id})
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
        videos.append({
            "video_id": v.id,
            "created_at": v.created_at.isoformat(),
            "fast_url": await storage.presign_get(v.assets["fast"]),
        })
    return {"videos": videos}


@router.delete("/v1/me", status_code=204)
async def delete_me(
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> None:
    await session.execute(sql_delete(Video).where(Video.device_id == device.id))
    await session.execute(sql_delete(Avatar).where(Avatar.device_id == device.id))
    merged = await session.merge(device)
    merged.deleted_at = datetime.now(UTC)
    await session.commit()
