import json

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import HEARTBEAT, publish, sse_comment, sse_format, subscription
from doppel_api.models import Avatar, Device
from doppel_api.queue import enqueue

router = APIRouter()

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


async def _look_views(avatar: Avatar, storage) -> list[dict]:
    """Presigned look thumbnails (first-frame edits) for the avatar card."""
    out = []
    for look in avatar.assets.get("looks") or []:
        if look.get("key"):
            out.append({
                "label": look.get("label"),
                "url": await storage.presign_get(look["key"]),
            })
    return out


@router.get("/v1/avatars")
async def list_avatars(
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    """The picker source for the Video Agent: device avatars + a preview frame."""
    result = await session.execute(
        select(Avatar)
        .where(Avatar.device_id == device.id, Avatar.status != "deleted")
        .order_by(Avatar.created_at.desc())
    )
    avatars = []
    for a in result.scalars():
        preview = None
        face_key = a.assets.get("face_image")
        if face_key:
            preview = await storage.presign_get(face_key)
        avatars.append({
            "avatar_id": a.id,
            "status": a.status,
            "label": a.assets.get("label"),
            "preview_url": preview,
            "voice_id": a.assets.get("voice_id"),
            "looks": await _look_views(a, storage),
        })
    return {"avatars": avatars}


@router.get("/v1/avatars/{avatar_id}")
async def get_avatar(
    avatar_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    a = (
        await session.execute(
            select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
        )
    ).scalar_one_or_none()
    if a is None or a.status == "deleted":
        raise HTTPException(status_code=404)
    out = {
        "avatar_id": a.id,
        "status": a.status,
        "label": a.assets.get("label"),
        "preview_url": await storage.presign_get(a.assets["face_image"])
        if a.assets.get("face_image") else None,
        "voice_id": a.assets.get("voice_id"),
        "looks": await _look_views(a, storage),
    }
    if a.assets.get("hello"):
        out["hello_url"] = await storage.presign_get(a.assets["hello"])
    if a.assets.get("feedback"):
        out["feedback_url"] = await storage.presign_get(a.assets["feedback"])
    if a.assets.get("idle"):
        out["idle_url"] = await storage.presign_get(a.assets["idle"])
    return out


@router.patch("/v1/avatars/{avatar_id}")
async def update_avatar(
    avatar_id: str,
    body: dict,
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> dict:
    a = (
        await session.execute(
            select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
        )
    ).scalar_one_or_none()
    if a is None or a.status == "deleted":
        raise HTTPException(status_code=404)
    label = (body.get("label") or "").strip()
    if label:
        a.assets = {**a.assets, "label": label[:120]}
        await session.commit()
    return {"avatar_id": a.id, "label": a.assets.get("label")}


@router.delete("/v1/avatars/{avatar_id}", status_code=204)
async def delete_avatar(
    avatar_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> None:
    a = (
        await session.execute(
            select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
        )
    ).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404)
    # Soft delete: keep the row (voices/plans reference it) but hide it everywhere.
    a.status = "deleted"
    await session.commit()


@router.websocket("/v1/avatars/stream")
async def avatar_stream(ws: WebSocket):
    await ws.accept()
    token = ws.query_params.get("t", "")
    app = ws.app
    async with app.state.session_factory() as session:
        result = await session.execute(
            select(Device).where(Device.token == token, Device.deleted_at.is_(None))
        )
        device = result.scalar_one_or_none()
        if device is None:
            await ws.send_text(json.dumps({"error": "invalid token"}))
            await ws.close()
            return

        header = json.loads(await ws.receive_text())
        ext = "mp4" if "mp4" in header.get("mime", "") else "webm"
        label = (header.get("label") or "").strip()
        avatar = Avatar(device_id=device.id)
        session.add(avatar)
        await session.commit()
        await ws.send_text(json.dumps({"avatar_id": avatar.id}))

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await ws.receive()
            if message.get("bytes") is not None:
                total += len(message["bytes"])
                if total > MAX_UPLOAD_BYTES:
                    await ws.close(code=1009)  # message too big
                    return  # avatar stays in recording, same as abandoned
                chunks.append(message["bytes"])
                continue
            if message.get("text"):
                control = json.loads(message["text"])
                if control.get("done"):
                    break
            if message.get("type") == "websocket.disconnect":
                return  # gravacao abandonada: avatar fica em recording

        key = f"raw/{avatar.id}/source.{ext}"
        await app.state.storage.put(key, b"".join(chunks), header.get("mime", "video/webm"))
        avatar.status = "processing"
        avatar.assets = {"source": key, "label": label} if label else {"source": key}
        # enqueue COMMITS the session (avatar mutations included) before xadd
        await enqueue(
            app.state.redis, session, kind="avatar_prep", lane="interactive",
            payload={"avatar_id": avatar.id},
        )
        await publish(app.state.redis, avatar.id, "status", {"value": "processing"})
        await ws.send_text(json.dumps({"avatar_id": avatar.id, "status": "processing"}))
        await ws.close()


@router.get("/v1/avatars/{avatar_id}/events")
async def avatar_events(
    avatar_id: str,
    request: Request,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
    storage=Depends(get_storage),
):
    result = await session.execute(
        select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404)
    # release the request-scoped connection; the stream uses its own short session
    await session.rollback()

    async def stream():
        # subscribe BEFORE reading the snapshot: no lost-event window
        async with subscription(redis, avatar_id) as events_iter:
            async with request.app.state.session_factory() as snap_session:
                snap = (
                    await snap_session.execute(select(Avatar).where(Avatar.id == avatar_id))
                ).scalar_one()
            data: dict = {"value": snap.status}
            if snap.status == "ready" and "hello" in snap.assets:
                data["hello_url"] = await storage.presign_get(snap.assets["hello"])
                data["feedback_url"] = await storage.presign_get(snap.assets["feedback"])
                if snap.assets.get("idle"):
                    data["idle_url"] = await storage.presign_get(snap.assets["idle"])
            yield sse_format("status", data)
            if snap.status in ("ready", "failed"):
                return
            async for event, payload in events_iter:
                if event == HEARTBEAT:
                    yield sse_comment()
                    continue
                yield sse_format(event, payload)
                if event in ("hello_ready", "failed"):
                    return

    return StreamingResponse(stream(), media_type="text/event-stream")
