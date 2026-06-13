import asyncio
import json

from sqlalchemy import select
from starlette.testclient import TestClient

from doppel_api.events import publish
from doppel_api.models import Avatar, Job


def _ws_upload(app, token: str) -> str:
    """Sobe 3 chunks fake pelo WS e retorna avatar_id."""
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/avatars/stream?t={token}") as ws:
            ws.send_text(json.dumps({"mime": "video/webm"}))
            first = json.loads(ws.receive_text())
            for chunk in (b"aaa", b"bbb", b"ccc"):
                ws.send_bytes(chunk)
            ws.send_text(json.dumps({"done": True}))
            final = json.loads(ws.receive_text())
    assert first["avatar_id"] == final["avatar_id"]
    assert final["status"] == "processing"
    return final["avatar_id"]


async def test_ws_upload_stores_source_and_enqueues_job(app, client, device_token):
    avatar_id = await asyncio.to_thread(_ws_upload, app, device_token)

    storage = app.state.storage
    data = await storage.get(f"raw/{avatar_id}/source.webm")
    assert data == b"aaabbbccc"

    async with app.state.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
        assert avatar.id == avatar_id
        assert avatar.status == "processing"
        job = (await s.execute(select(Job))).scalar_one()
        assert job.kind == "avatar_prep"
        assert job.payload == {"avatar_id": avatar_id}
        assert job.lane == "interactive"


async def test_avatar_events_sse_streams_published_events(app, client, device_token):
    avatar_id = await asyncio.to_thread(_ws_upload, app, device_token)

    async def emit():
        await asyncio.sleep(0.2)
        await publish(app.state.redis, avatar_id, "hello_ready", {"hello_url": "memory://h"})

    task = asyncio.create_task(emit())

    async def consume() -> list[str]:
        lines: list[str] = []
        async with client.stream(
            "GET", f"/v1/avatars/{avatar_id}/events", headers={"X-Device-Token": device_token}
        ) as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                lines.append(line)
                if line == "event: hello_ready":
                    break
        return lines

    lines = await asyncio.wait_for(consume(), timeout=10)
    await task
    assert "event: status" in lines
    assert "event: hello_ready" in lines


async def test_avatar_events_ready_snapshot_short_circuits(app, client, device_token):
    avatar_id = await asyncio.to_thread(_ws_upload, app, device_token)
    async with app.state.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {
            **avatar.assets,
            "hello": f"avatars/{avatar_id}/hello.mp4",
            "feedback": f"avatars/{avatar_id}/feedback.mp4",
        }
        await s.commit()
    lines: list[str] = []
    async with client.stream(
        "GET", f"/v1/avatars/{avatar_id}/events", headers={"X-Device-Token": device_token}
    ) as resp:
        async for line in resp.aiter_lines():
            lines.append(line)
    assert "event: status" in lines
    data_line = next(line for line in lines if line.startswith("data: "))
    payload = json.loads(data_line[6:])
    assert payload["value"] == "ready"
    assert payload["hello_url"] == f"memory://avatars/{avatar_id}/hello.mp4"
    assert payload["feedback_url"] == f"memory://avatars/{avatar_id}/feedback.mp4"


async def test_avatar_events_404_for_foreign_avatar(app, client, device_token):
    avatar_id = await asyncio.to_thread(_ws_upload, app, device_token)
    other = await client.post("/v1/sessions")
    other_token = other.json()["token"]
    resp = await client.get(
        f"/v1/avatars/{avatar_id}/events", headers={"X-Device-Token": other_token}
    )
    assert resp.status_code == 404


async def test_ws_rejects_invalid_token(app):
    def attempt():
        with TestClient(app) as tc:
            with tc.websocket_connect("/v1/avatars/stream?t=wrong") as ws:
                return json.loads(ws.receive_text())

    result = await asyncio.to_thread(attempt)
    assert result == {"error": "invalid token"}
