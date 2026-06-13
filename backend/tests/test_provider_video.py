from doppel_api.providers import video


async def test_lipsync_posts_multipart_and_returns_bytes(monkeypatch, tmp_path):
    video_file = tmp_path / "v.mp4"
    audio_file = tmp_path / "a.mp3"
    video_file.write_bytes(b"VID")
    audio_file.write_bytes(b"AUD")
    seen: dict = {}

    class FakeResp:
        content = b"OUT"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, data, files, headers):
            seen["url"] = url
            seen["data"] = data
            seen["headers"] = headers
            return FakeResp()

    monkeypatch.setattr(video.httpx, "AsyncClient", lambda **kw: FakeClient())
    out = await video.lipsync(str(video_file), str(audio_file))
    assert out == b"OUT"
    assert seen["url"].endswith("/v1/lipsync")
    assert seen["data"]["guidance_scale"] == "1.5"


async def test_broll_i2v_posts_cosmos_form(monkeypatch):
    seen: dict = {}

    class FakeResp:
        content = b"BROLL"

        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, data, files, headers):
            seen["url"] = url
            seen["data"] = data
            seen["files"] = files
            return FakeResp()

    monkeypatch.setattr(video.httpx, "AsyncClient", lambda **kw: FakeClient())
    out = await video.broll_i2v(
        first_frame=b"PNG",
        prompt="beach sunrise",
        negative_prompt="text",
        duration_sec=5.0,
    )
    assert out == b"BROLL"
    assert seen["url"].endswith("/v1/videos/sync")
    assert seen["data"]["prompt"] == "beach sunrise"
    assert seen["data"]["num_frames"] == "120"  # 5s * 24fps
