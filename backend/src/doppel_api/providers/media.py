"""Local media ops: ffmpeg frame/audio extraction, SRT captions, timeline compose, downloads."""
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import anyio
import httpx


@dataclass
class CaptionCue:
    text: str
    start: float
    end: float


@dataclass
class BrollClip:
    path: str
    start: float
    end: float


def ffmpeg_missing() -> bool:
    return shutil.which("ffmpeg") is None


def _srt_ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(cues: list[CaptionCue]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(f"{i}\n{_srt_ts(cue.start)} --> {_srt_ts(cue.end)}\n{cue.text}\n")
    return "\n".join(blocks)


def _run_ffmpeg(args: list[str]) -> None:
    try:
        subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"")[-2000:]
        raise RuntimeError(f"ffmpeg failed ({e.returncode}): {tail!r}") from e


async def extract_frame(src_path: str, out_path: str) -> str:
    args = ["-ss", "1", "-i", src_path, "-frames:v", "1", "-q:v", "2", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def extract_audio(src_path: str, out_path: str) -> str:
    args = ["-i", src_path, "-vn", "-ac", "1", "-ar", "44100", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


def _compose_args(
    avatar_path: str, brolls: list[BrollClip], srt_path: str, out_path: str, font: str
) -> list[str]:
    args: list[str] = ["-i", avatar_path]
    for clip in brolls:
        args += ["-i", clip.path]
    chains = ["[0:v]scale=540:960,setsar=1[base]"]
    label = "base"
    for idx, clip in enumerate(brolls, start=1):
        chains.append(f"[{idx}:v]scale=540:960,setsar=1[bv{idx}]")
        nxt = f"ov{idx}"
        chains.append(
            f"[{label}][bv{idx}]overlay=enable='between(t,{clip.start},{clip.end})'[{nxt}]"
        )
        label = nxt
    safe_srt = srt_path.replace(":", r"\:")
    chains.append(f"[{label}]subtitles={safe_srt}:force_style='FontName={font}'[v]")
    filter_complex = ";".join(chains)
    args += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        out_path,
    ]
    return args


async def compose_timeline(
    avatar_path: str,
    brolls: list[BrollClip],
    cues: list[CaptionCue],
    out_path: str,
    font: str,
) -> str:
    srt_path = str(Path(out_path).with_suffix(".srt"))
    args = _compose_args(avatar_path, brolls, srt_path, out_path, font)

    def _compose() -> None:
        Path(srt_path).write_text(build_srt(cues), encoding="utf-8")
        _run_ffmpeg(args)

    await anyio.to_thread.run_sync(_compose)
    return out_path


async def fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def download(url: str, out_path: str) -> str:
    data = await fetch(url)
    await anyio.to_thread.run_sync(lambda: Path(out_path).write_bytes(data))
    return out_path
