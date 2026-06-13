"""End-to-end smoke against the live Doppel compose stack (real PG/Redis/floci/ffmpeg).

Drives the exact HTTP+WS contract the frontend uses and verifies the worker
rendered placeholder videos and uploaded them to floci.
"""
import asyncio
import json
import sys

import httpx
import websockets

API = "http://localhost:8200"
WS = "ws://localhost:8200"


def browserize(url: str) -> str:
    # presigns point at http://floci:4566 (compose-internal); from the host the
    # floci container is published on localhost:4566.
    return url.replace("http://floci:4566", "http://localhost:4566")


async def sse_wait(client, path, token, terminal, timeout=60):
    """Consume SSE until an event in `terminal` arrives; return (event, data)."""
    seen = []
    async with client.stream("GET", f"{API}{path}", headers={"X-Device-Token": token},
                             timeout=timeout) as resp:
        assert resp.status_code == 200, f"SSE {path} -> {resp.status_code}"
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                seen.append((event, data))
                if event in terminal:
                    return event, data
    raise AssertionError(f"SSE {path} closed without {terminal}; saw {[e for e, _ in seen]}")


async def main() -> int:
    async with httpx.AsyncClient() as client:
        # 1. session
        r = await client.post(f"{API}/v1/sessions")
        assert r.status_code == 201, r.text
        token = r.json()["token"]
        print(f"[ok] session minted (token {token[:8]}...)")

        # 2-5. avatar upload over WS (streaming chunks, like the reading scene)
        async with websockets.connect(f"{WS}/v1/avatars/stream?t={token}") as ws:
            await ws.send(json.dumps({"mime": "video/webm"}))
            first = json.loads(await ws.recv())
            avatar_id = first["avatar_id"]
            for chunk in (b"\x1a\x45\xdf\xa3fake", b"webm", b"chunks"):
                await ws.send(chunk)
            await ws.send(json.dumps({"done": True}))
            final = json.loads(await ws.recv())
            assert final["status"] == "processing", final
        print(f"[ok] avatar uploaded over WS (avatar_id {avatar_id[:8]}..., status processing)")

        # 6. avatar SSE until hello_ready (worker renders hello+feedback via ffmpeg)
        event, data = await sse_wait(client, f"/v1/avatars/{avatar_id}/events", token,
                                     {"hello_ready", "failed"})
        assert event == "hello_ready", f"avatar prep failed: {data}"
        assert "hello_url" in data and "feedback_url" in data, data
        print("[ok] worker produced hello + feedback (hello_ready received)")

        # 7. verify the rendered hello object actually exists in floci
        hello = await client.get(browserize(data["hello_url"]))
        assert hello.status_code == 200 and len(hello.content) > 1000, \
            f"hello object {hello.status_code} len={len(hello.content)}"
        assert hello.content[4:8] == b"ftyp", "not an mp4 (no ftyp box)"
        print(f"[ok] hello.mp4 fetchable from floci ({len(hello.content)} bytes, valid mp4)")

        # 8. create video with briefing (multipart, like the briefing scene)
        r = await client.post(f"{API}/v1/videos", headers={"X-Device-Token": token},
                              data={"avatar_id": avatar_id},
                              files={"briefing": ("b.webm", b"fake-audio-briefing", "audio/webm")})
        assert r.status_code == 201, r.text
        video_id = r.json()["video_id"]
        print(f"[ok] video created (video_id {video_id[:8]}...)")

        # 9. video SSE until fast_ready (progress steps + 30s placeholder render)
        steps = []
        async with client.stream("GET", f"{API}/v1/videos/{video_id}/events",
                                 headers={"X-Device-Token": token}, timeout=120) as resp:
            event = None
            done = None
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event = line[7:]
                elif line.startswith("data: "):
                    d = json.loads(line[6:])
                    if event == "progress":
                        steps.append(d["step"])
                    if event in ("fast_ready", "failed") or (event == "status" and d.get("fast_url")):
                        done = (event, d)
                        break
        assert done and done[0] != "failed", f"generation failed: {done}; steps={steps}"
        fast_url = done[1]["fast_url"]
        print(f"[ok] fast video ready (progress steps seen: {steps})")

        # 10. verify the 30s placeholder rendered and uploaded
        fast = await client.get(browserize(fast_url))
        assert fast.status_code == 200 and fast.content[4:8] == b"ftyp", \
            f"fast object {fast.status_code}"
        print(f"[ok] fast.mp4 fetchable from floci ({len(fast.content)} bytes, valid mp4)")

        # 11. thumbs up -> gallery
        r = await client.post(f"{API}/v1/videos/{video_id}/feedback",
                              headers={"X-Device-Token": token}, json={"rating": "up"})
        assert r.json()["action"] == "gallery", r.text
        print("[ok] thumbs up -> gallery")

        # 12. gallery lists the video
        r = await client.get(f"{API}/v1/gallery", headers={"X-Device-Token": token})
        vids = r.json()["videos"]
        assert len(vids) == 1 and vids[0]["video_id"] == video_id, vids
        print(f"[ok] gallery lists 1 video with presigned url")

        # 13-14. LGPD delete then gallery is 401
        r = await client.delete(f"{API}/v1/me", headers={"X-Device-Token": token})
        assert r.status_code == 204, r.status_code
        r = await client.get(f"{API}/v1/gallery", headers={"X-Device-Token": token})
        assert r.status_code == 401, r.status_code
        print("[ok] delete me -> token revoked (gallery 401)")

    print("\nALL GREEN: full pipeline works against live PG + Redis + floci + ffmpeg worker")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
