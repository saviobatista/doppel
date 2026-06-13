import asyncio

from sqlalchemy import select

from doppel_api.events import publish
from doppel_api.models import Avatar, Device, Job, Video


async def _seed_ready_avatar(app, device_token: str) -> str:
    async with app.state.session_factory() as s:
        device = (await s.execute(select(Device))).scalar_one()
        avatar = Avatar(device_id=device.id, status="ready", assets={"source": "raw/k"})
        s.add(avatar)
        await s.commit()
        return avatar.id


async def test_create_video_enqueues_fast_generate(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos",
        headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id},
        files={"briefing": ("briefing.webm", b"audio-bytes", "audio/webm")},
    )
    assert resp.status_code == 201
    video_id = resp.json()["video_id"]
    async with app.state.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.kind == "fast_generate"))).scalar_one()
        assert job.payload == {"video_id": video_id}
        assert job.lane == "interactive"
    data = await app.state.storage.get(f"videos/{video_id}/briefing.webm")
    assert data == b"audio-bytes"


async def test_create_video_404_for_foreign_avatar(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    other = (await client.post("/v1/sessions")).json()["token"]
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": other},
        data={"avatar_id": avatar_id},
    )
    assert resp.status_code == 404


async def test_video_events_sse(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id},
        files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    video_id = resp.json()["video_id"]

    async def emit():
        await asyncio.sleep(0.2)
        await publish(app.state.redis, video_id, "fast_ready", {"fast_url": "memory://f"})

    task = asyncio.create_task(emit())

    async def consume() -> list[str]:
        lines: list[str] = []
        async with client.stream(
            "GET", f"/v1/videos/{video_id}/events", headers={"X-Device-Token": device_token}
        ) as r:
            async for line in r.aiter_lines():
                lines.append(line)
                if line == "event: fast_ready":
                    break
        return lines

    lines = await asyncio.wait_for(consume(), timeout=10)
    await task
    assert "event: status" in lines
    assert "event: fast_ready" in lines


async def test_feedback_up_sets_rating(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id}, files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    video_id = resp.json()["video_id"]
    resp = await client.post(
        f"/v1/videos/{video_id}/feedback",
        headers={"X-Device-Token": device_token}, json={"rating": "up"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"video_id": video_id, "action": "gallery"}
    async with app.state.session_factory() as s:
        video = (await s.execute(select(Video))).scalar_one()
        assert video.rating == "up"


async def test_feedback_down_creates_regen_video(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id}, files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    first_id = resp.json()["video_id"]
    resp = await client.post(
        f"/v1/videos/{first_id}/feedback",
        headers={"X-Device-Token": device_token}, json={"rating": "down"},
    )
    assert resp.status_code == 200
    new_id = resp.json()["video_id"]
    assert new_id != first_id
    assert resp.json()["action"] == "regenerate"
    async with app.state.session_factory() as s:
        jobs = (await s.execute(select(Job).where(Job.kind == "fast_generate"))).scalars().all()
        assert {j.payload["video_id"] for j in jobs} == {first_id, new_id}


async def test_feedback_rejects_invalid_rating(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id}, files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    video_id = resp.json()["video_id"]
    resp = await client.post(
        f"/v1/videos/{video_id}/feedback",
        headers={"X-Device-Token": device_token}, json={"rating": "sideways"},
    )
    assert resp.status_code == 422


async def test_gallery_lists_ready_videos_with_urls(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    async with app.state.session_factory() as s:
        device = (await s.execute(select(Device))).scalar_one()
        v = Video(device_id=device.id, avatar_id=avatar_id, status_fast="ready",
                  assets={"fast": "videos/v1/fast.mp4"}, rating="up")
        s.add(v)
        await s.commit()
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": device_token})
    assert resp.status_code == 200
    videos = resp.json()["videos"]
    assert len(videos) == 1
    assert videos[0]["fast_url"] == "memory://videos/v1/fast.mp4"
    assert videos[0]["video_id"] == v.id


async def test_create_video_without_briefing(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id},
    )
    assert resp.status_code == 201


async def test_delete_me_removes_rows_and_keeps_jobs(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id}, files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    assert resp.status_code == 201
    resp = await client.delete("/v1/me", headers={"X-Device-Token": device_token})
    assert resp.status_code == 204
    async with app.state.session_factory() as s:
        assert (await s.execute(select(Video))).scalars().all() == []
        assert (await s.execute(select(Avatar))).scalars().all() == []
        jobs = (await s.execute(select(Job))).scalars().all()
        assert len(jobs) == 1  # fast_generate job kept for audit


async def test_delete_me_revokes_token_and_rows(app, client, device_token):
    resp = await client.delete("/v1/me", headers={"X-Device-Token": device_token})
    assert resp.status_code == 204
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": device_token})
    assert resp.status_code == 401


async def test_download_video_returns_bytes_as_attachment(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    async with app.state.session_factory() as s:
        device = (await s.execute(select(Device))).scalar_one()
        v = Video(device_id=device.id, avatar_id=avatar_id, status_fast="ready",
                  assets={"fast": "videos/v/fast.mp4"}, rating="up")
        s.add(v)
        await s.commit()
        vid = v.id
    await app.state.storage.put("videos/v/fast.mp4", b"FINALVIDEO", "video/mp4")
    resp = await client.get(f"/v1/videos/{vid}/download", headers={"X-Device-Token": device_token})
    assert resp.status_code == 200
    assert resp.content == b"FINALVIDEO"
    assert "attachment" in resp.headers["content-disposition"]


async def test_download_video_404_for_unknown(app, client, device_token):
    resp = await client.get("/v1/videos/nope/download", headers={"X-Device-Token": device_token})
    assert resp.status_code == 404
