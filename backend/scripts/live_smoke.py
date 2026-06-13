"""Opt-in live end-to-end smoke against the REAL providers (costs money).

Run with real keys in the environment:
    DOPPEL_LIVE_SMOKE=1 uv run python scripts/live_smoke.py

It synthesizes a 3s clip with ffmpeg, runs voice clone + TTS + Fabric for the
avatar, then a script + b-roll + compose. Prints output paths. Refuses to run
unless DOPPEL_LIVE_SMOKE=1 to avoid accidental spend.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from doppel_api.providers import media, script, video, voice


def _make_sample(path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=180:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path],
        check=True, capture_output=True,
    )


async def run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        sample = str(tmp / "sample.mp4")
        _make_sample(sample)

        face = await media.extract_frame(sample, str(tmp / "face.png"))
        ref = await media.extract_audio(sample, str(tmp / "ref.wav"))
        print("cloning voice...")
        voice_id = await voice.clone(ref, name="live-smoke")
        print("voice:", voice_id)

        hello_bytes = await voice.tts(voice_id, "Oi! Eu sou você aprimorado!")
        (tmp / "hello.mp3").write_bytes(hello_bytes)
        face_url = await video.upload(face)
        hello_audio_url = await video.upload(str(tmp / "hello.mp3"))
        print("generating talking avatar (Fabric)...")
        talk_url = await video.talking(face_url, hello_audio_url)
        await media.download(talk_url, str(tmp / "hello.mp4"))
        print("hello.mp4 ->", tmp / "hello.mp4", os.path.getsize(tmp / "hello.mp4"), "bytes")  # noqa: ASYNC240

        print("building script...")
        sjson = await script.build_script("Quero um vídeo curto sobre proteger suas senhas.")
        print("script scenes:", [(s["type"], s["start"], s["end"]) for s in sjson["scenes"]])

        narration, cues = await voice.tts_with_timestamps(voice_id, sjson["narration"]["text"])
        (tmp / "narration.mp3").write_bytes(narration)
        narration_url = await video.upload(str(tmp / "narration.mp3"))
        avatar_url = await video.talking(face_url, narration_url)
        await media.download(avatar_url, str(tmp / "avatar.mp4"))

        brolls = []
        for i, sc in enumerate(s for s in sjson["scenes"] if s["type"] == "broll"):
            img = await video.image(sc.get("prompt", "abstract background"))
            clip = await video.broll(img, sc.get("motion") or sc.get("prompt", ""))
            p = str(tmp / f"broll{i}.mp4")
            await media.download(clip, p)
            brolls.append(media.BrollClip(path=p, start=float(sc["start"]), end=float(sc["end"])))

        out = str(Path.cwd() / "live_smoke_out.mp4")
        await media.compose_timeline(str(tmp / "avatar.mp4"), brolls, cues, out, "DejaVu Sans")
        print("FINAL ->", out, os.path.getsize(out), "bytes")  # noqa: ASYNC240


if __name__ == "__main__":
    if os.environ.get("DOPPEL_LIVE_SMOKE") != "1":
        print("refusing to run: set DOPPEL_LIVE_SMOKE=1 (this spends real money)")
        sys.exit(1)
    asyncio.run(run())
