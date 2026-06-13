import pytest

from doppel_api.providers import media
from doppel_api.providers.media import BrollClip, CaptionCue, build_srt


def test_build_srt_formats_cues():
    srt = build_srt([
        CaptionCue(text="Olá", start=0.0, end=1.25),
        CaptionCue(text="mundo", start=1.25, end=2.5),
    ])
    assert "1\n00:00:00,000 --> 00:00:01,250\nOlá\n" in srt
    assert "2\n00:00:01,250 --> 00:00:02,500\nmundo\n" in srt


def test_compose_args_structure():
    args = media._compose_args(
        avatar_path="avatar.mp4",
        brolls=[BrollClip(path="b0.mp4", start=5.0, end=10.0)],
        srt_path="caps.srt",
        out_path="out.mp4",
        font="DejaVu Sans",
    )
    joined = " ".join(args)
    assert "-i avatar.mp4" in joined
    assert "-i b0.mp4" in joined
    assert "overlay=enable='between(t,5.0,10.0)'" in joined
    assert "subtitles=" in joined
    assert "DejaVu Sans" in joined
    assert args[-1] == "out.mp4"


async def test_download_writes_fetched_bytes(tmp_path, monkeypatch):
    async def fake_fetch(url: str) -> bytes:
        assert url == "https://fal.media/x.mp4"
        return b"VIDEO"

    monkeypatch.setattr(media, "fetch", fake_fetch)
    out = str(tmp_path / "x.mp4")
    result = await media.download("https://fal.media/x.mp4", out)
    assert result == out
    with open(out, "rb") as f:  # noqa: ASYNC230
        assert f.read() == b"VIDEO"


@pytest.mark.skipif(media.ffmpeg_missing(), reason="ffmpeg not installed")
async def test_extract_frame_integration(tmp_path):
    import subprocess
    src = str(tmp_path / "src.mp4")
    subprocess.run(  # noqa: ASYNC221
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", src],
        check=True, capture_output=True,
    )
    out = await media.extract_frame(src, str(tmp_path / "frame.png"))
    assert out.endswith("frame.png")
    import os
    assert os.path.getsize(out) > 0  # noqa: ASYNC240


@pytest.mark.skipif(media.ffmpeg_missing(), reason="ffmpeg not installed")
async def test_extract_is_deterministic(tmp_path):
    # bit-exact extraction: same source -> identical bytes, so cache keys are stable
    import subprocess
    src = str(tmp_path / "src.mp4")
    subprocess.run(  # noqa: ASYNC221
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=2",
         "-f", "lavfi", "-i", "sine=frequency=200:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
        check=True, capture_output=True,
    )
    f1 = await media.extract_frame(src, str(tmp_path / "f1.png"))
    f2 = await media.extract_frame(src, str(tmp_path / "f2.png"))
    a1 = await media.extract_audio(src, str(tmp_path / "a1.wav"))
    a2 = await media.extract_audio(src, str(tmp_path / "a2.wav"))
    assert open(f1, "rb").read() == open(f2, "rb").read()  # noqa: ASYNC230
    assert open(a1, "rb").read() == open(a2, "rb").read()  # noqa: ASYNC230
