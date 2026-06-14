"""Video Agent plan artifact: create → research/script (worker) → review/edit → generate."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import HEARTBEAT, sse_comment, sse_format, subscription
from doppel_api.models import Avatar, Device, Plan, Video
from doppel_api.queue import enqueue

router = APIRouter()

TERMINAL_BUILD = ("ready", "failed")


async def _rehydrate(plan_dict: dict, storage) -> dict:
    """Replace stored (expiring) presigned URLs with freshly-signed ones from the
    durable S3 keys, so a revisited plan never shows broken assets. Mutates and
    returns plan_dict. Footage `video_url` (a YouTube link) is left as-is.
    """
    plan = plan_dict.get("plan")
    if isinstance(plan, dict):
        res = plan.get("resources") or {}
        for it in res.get("media") or []:
            if it.get("key"):
                it["preview_url"] = await storage.presign_get(it["key"])
        for el in res.get("design_elements") or []:
            if el.get("key"):
                el["preview_url"] = await storage.presign_get(el["key"])
        for tr in res.get("audio") or []:
            if tr.get("key"):
                tr["preview_url"] = await storage.presign_get(tr["key"])
        for fo in res.get("footage") or []:
            if fo.get("thumb_key"):
                fo["preview_url"] = await storage.presign_get(fo["thumb_key"])

    bundle = plan_dict.get("bundle")
    if isinstance(bundle, dict):
        for a in bundle.get("assets") or []:
            if a.get("key"):
                a["download_url"] = await storage.presign_get(a["key"])
        if bundle.get("plan_key"):
            bundle["plan_download_url"] = await storage.presign_get(bundle["plan_key"])
    return plan_dict


class PlanCreate(BaseModel):
    prompt: str
    avatar_id: str | None = None
    voice_id: str | None = None
    avatar_label: str | None = None
    voice_label: str | None = None
    duration_seconds: int = 40
    orientation: Literal["portrait", "landscape"] = "portrait"
    language: str = "pt-BR"


class PlanPatch(BaseModel):
    plan: dict


class PlanGenerate(BaseModel):
    # Attach/override the avatar at generation time (the plan may have been built
    # without one). `selections` pins choices (e.g. {"music_key": "..."}); the
    # `model_overrides` swap generation drivers per run (tts/lipsync/i2v/...).
    avatar_id: str | None = None
    selections: dict = {}
    model_overrides: dict = {}


def _plan_dict(p: Plan) -> dict:
    return {
        "plan_id": p.id,
        "status": p.status,
        "brief": p.brief,
        "plan": p.plan,
        "bundle": p.bundle,
        "video_id": p.video_id,
        "created_at": p.created_at.isoformat(),
    }


@router.post("/v1/plans", status_code=201)
async def create_plan(
    body: PlanCreate,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
) -> dict:
    if body.avatar_id is not None:
        owned = await session.execute(
            select(Avatar).where(Avatar.id == body.avatar_id, Avatar.device_id == device.id)
        )
        if owned.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="avatar not found")

    plan = Plan(
        device_id=device.id,
        avatar_id=body.avatar_id,
        status="researching",
        brief=body.model_dump(),
    )
    session.add(plan)
    await session.flush()
    # enqueue COMMITS the session (plan row included) before notifying the stream
    await enqueue(redis, session, kind="plan_build", lane="interactive",
                  payload={"plan_id": plan.id})
    return {"plan_id": plan.id}


@router.get("/v1/plans")
async def list_plans(
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    """List the device's plans (the revisitable sessions). Lightweight: the heavy
    `plan` blob is dropped; a `summary` carries what the projects grid needs."""
    result = await session.execute(
        select(Plan).where(Plan.device_id == device.id).order_by(Plan.created_at.desc())
    )
    plans = []
    for p in result.scalars():
        plan_json = p.plan or {}
        res = plan_json.get("resources") or {}
        cover_key = next((it.get("key") for it in (res.get("media") or []) if it.get("key")), None)
        plans.append({
            "plan_id": p.id,
            "status": p.status,
            "title": plan_json.get("title") or (p.brief or {}).get("prompt", "")[:80],
            "prompt": (p.brief or {}).get("prompt"),
            "video_id": p.video_id,
            "created_at": p.created_at.isoformat(),
            "counts": (p.bundle or {}).get("counts"),
            "cover_url": await storage.presign_get(cover_key) if cover_key else None,
        })
    return {"plans": plans}


@router.get("/v1/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    result = await session.execute(
        select(Plan).where(Plan.id == plan_id, Plan.device_id == device.id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404)
    return await _rehydrate(_plan_dict(plan), storage)


@router.patch("/v1/plans/{plan_id}")
async def patch_plan(
    plan_id: str,
    body: PlanPatch,
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> dict:
    result = await session.execute(
        select(Plan).where(Plan.id == plan_id, Plan.device_id == device.id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404)
    plan.plan = body.plan
    await session.commit()
    return _plan_dict(plan)


@router.get("/v1/plans/{plan_id}/events")
async def plan_events(
    plan_id: str,
    request: Request,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
    storage=Depends(get_storage),
):
    result = await session.execute(
        select(Plan).where(Plan.id == plan_id, Plan.device_id == device.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404)
    # release the request-scoped connection; the stream uses its own short session
    await session.rollback()

    async def stream():
        # subscribe BEFORE reading the snapshot: no lost-event window
        async with subscription(redis, plan_id) as events_iter:
            async with request.app.state.session_factory() as snap_session:
                snap = (
                    await snap_session.execute(select(Plan).where(Plan.id == plan_id))
                ).scalar_one()
            yield sse_format("status", {"value": snap.status})
            if snap.plan is not None:
                # rehydrate so a revisited (terminal) plan never serves expired URLs
                fresh = await _rehydrate(
                    {"plan": snap.plan, "bundle": snap.bundle}, storage)
                yield sse_format("plan", {"plan": fresh["plan"]})
                if fresh.get("bundle"):
                    yield sse_format("bundle", {"bundle": fresh["bundle"]})
            if snap.status == "failed" or (
                snap.status == "ready" and (snap.plan or {}).get("resources", {}).get("audio")
            ):
                return  # terminal AND music already present — nothing more to stream
            # Otherwise keep streaming: music is generated AFTER `ready` and arrives
            # as a late `audio` event; bound the post-ready wait so we never hang.
            ready_seen = snap.status == "ready"
            hb_after_ready = 0
            async for event, payload in events_iter:
                if event == HEARTBEAT:
                    yield sse_comment()
                    if ready_seen:
                        hb_after_ready += 1
                        if hb_after_ready > 40:  # ~160s cap after ready
                            return
                    continue
                yield sse_format(event, payload)  # incl. plan_partial (progressive fill)
                if event == "failed" or event == "audio":
                    return
                if event == "ready":
                    ready_seen = True

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/v1/plans/{plan_id}/generate", status_code=201)
async def generate_plan(
    plan_id: str,
    body: PlanGenerate | None = None,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
) -> dict:
    body = body or PlanGenerate()
    result = await session.execute(
        select(Plan).where(Plan.id == plan_id, Plan.device_id == device.id)
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404)
    if plan.plan is None:
        raise HTTPException(status_code=409, detail="plan not ready")
    # A plan can be built without an avatar; attach one now via the request body.
    if body.avatar_id:
        plan.avatar_id = body.avatar_id
    if not plan.avatar_id:
        raise HTTPException(status_code=422, detail="plan has no avatar selected")
    avatar = (
        await session.execute(
            select(Avatar).where(Avatar.id == plan.avatar_id, Avatar.device_id == device.id)
        )
    ).scalar_one_or_none()
    if avatar is None:
        raise HTTPException(status_code=404, detail="avatar not found")
    if avatar.status != "ready":
        raise HTTPException(status_code=409, detail="avatar not ready")

    video = Video(device_id=device.id, avatar_id=plan.avatar_id)
    session.add(video)
    await session.flush()
    plan.video_id = video.id
    plan.status = "generating"
    # enqueue COMMITS (video + plan mutations in one transaction) before xadd
    await enqueue(redis, session, kind="plan_generate", lane="interactive",
                  payload={
                      "plan_id": plan.id, "video_id": video.id,
                      "selections": body.selections, "model_overrides": body.model_overrides,
                  })
    return {"video_id": video.id}
