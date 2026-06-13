import json

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import HEARTBEAT, publish, sse_comment, sse_format, subscription
from doppel_api.log import get_logger, kv
from doppel_api.models import Avatar, Device
from doppel_api.queue import enqueue

router = APIRouter()
log = get_logger("avatars")

MAX_UPLOAD_BYTES = 64 * 1024 * 1024


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
            log.warning("avatar upload rejected %s", kv(reason="invalid_token"))
            await ws.send_text(json.dumps({"error": "invalid token"}))
            await ws.close()
            return

        header = json.loads(await ws.receive_text())
        ext = "mp4" if "mp4" in header.get("mime", "") else "webm"
        avatar = Avatar(device_id=device.id)
        session.add(avatar)
        await session.commit()
        await ws.send_text(json.dumps({"avatar_id": avatar.id}))
        log.info("avatar upload started %s", kv(avatar_id=avatar.id, device_id=device.id, mime=header.get("mime")))

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await ws.receive()
            if message.get("bytes") is not None:
                total += len(message["bytes"])
                if total > MAX_UPLOAD_BYTES:
                    log.warning(
                        "avatar upload rejected %s",
                        kv(avatar_id=avatar.id, reason="too_large", bytes=total),
                    )
                    await ws.close(code=1009)  # message too big
                    return  # avatar stays in recording, same as abandoned
                chunks.append(message["bytes"])
                continue
            if message.get("text"):
                control = json.loads(message["text"])
                if control.get("done"):
                    break
            if message.get("type") == "websocket.disconnect":
                log.warning(
                    "avatar upload abandoned %s",
                    kv(avatar_id=avatar.id, bytes_received=total),
                )
                return  # gravacao abandonada: avatar fica em recording

        key = f"raw/{avatar.id}/source.{ext}"
        await app.state.storage.put(key, b"".join(chunks), header.get("mime", "video/webm"))
        avatar.status = "processing"
        avatar.assets = {"source": key}
        # enqueue COMMITS the session (avatar mutations included) before xadd
        job = await enqueue(
            app.state.redis, session, kind="avatar_prep", lane="interactive",
            payload={"avatar_id": avatar.id},
        )
        log.info(
            "avatar upload complete %s",
            kv(avatar_id=avatar.id, job_id=job.id, bytes=total, source_key=key),
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
    device_id = device.id
    # release the request-scoped connection; the stream uses its own short session
    await session.rollback()

    async def stream():
        log.info("avatar sse opened %s", kv(avatar_id=avatar_id, device_id=device_id))
        terminal = None
        try:
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
                yield sse_format("status", data)
                if snap.status in ("ready", "failed"):
                    terminal = snap.status
                    return
                async for event, payload in events_iter:
                    if event == HEARTBEAT:
                        yield sse_comment()
                        continue
                    log.info("avatar sse event %s", kv(avatar_id=avatar_id, event=event, **payload))
                    yield sse_format(event, payload)
                    if event in ("hello_ready", "failed"):
                        terminal = event
                        return
        finally:
            log.info("avatar sse closed %s", kv(avatar_id=avatar_id, terminal=terminal))

    return StreamingResponse(stream(), media_type="text/event-stream")
