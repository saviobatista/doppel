from doppel_api.providers import video


async def test_upload_returns_url(monkeypatch):
    async def fake_upload(path):
        assert path == "f.png"
        return "https://fal.media/f.png"

    monkeypatch.setattr(video.fal_client, "upload_file_async", fake_upload)
    assert await video.upload("f.png") == "https://fal.media/f.png"


async def test_talking_calls_fabric_and_parses_url(monkeypatch):
    seen = {}

    async def fake_subscribe(model, arguments):
        seen["model"] = model
        seen["args"] = arguments
        return {"video": {"url": "https://fal.media/talk.mp4"}}

    monkeypatch.setattr(video.fal_client, "subscribe_async", fake_subscribe)
    url = await video.talking("img-url", "aud-url", resolution="480p")
    assert url == "https://fal.media/talk.mp4"
    assert seen["model"] == "veed/fabric-1.0"
    assert seen["args"] == {"image_url": "img-url", "audio_url": "aud-url", "resolution": "480p"}


async def test_image_calls_flux_and_parses_url(monkeypatch):
    async def fake_subscribe(model, arguments):
        assert model == "fal-ai/flux/schnell"
        assert arguments["prompt"] == "a vault"
        assert arguments["num_images"] == 1
        return {"images": [{"url": "https://fal.media/i.jpg"}]}

    monkeypatch.setattr(video.fal_client, "subscribe_async", fake_subscribe)
    assert await video.image("a vault") == "https://fal.media/i.jpg"


async def test_broll_calls_kling_with_string_duration(monkeypatch):
    seen = {}

    async def fake_subscribe(model, arguments):
        seen.update(arguments)
        seen["model"] = model
        return {"video": {"url": "https://fal.media/b.mp4"}}

    monkeypatch.setattr(video.fal_client, "subscribe_async", fake_subscribe)
    url = await video.broll("i.jpg", "camera zooms in")
    assert url == "https://fal.media/b.mp4"
    assert seen["model"] == "fal-ai/kling-video/v2.1/standard/image-to-video"
    assert seen["image_url"] == "i.jpg"
    assert seen["duration"] == "5"  # string, not int
