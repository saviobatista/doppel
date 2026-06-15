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


def _ass_ts(seconds: float) -> str:
    cs = round(max(0.0, seconds) * 100)
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(
    cues: list[CaptionCue],
    font: str = "DejaVu Sans",
    *,
    width: int = 1080,
    height: int = 1920,
    fontsize: int = 64,
    margin_v: int = 230,
) -> str:
    """An ASS subtitle script with an explicit PlayRes so positioning is in real
    target pixels (the bare `subtitles` filter defaults to a 384x288 PlayRes,
    which is what pushes MarginV-based captions up to the middle of the frame).
    Captions sit in the lower band (Alignment=2 = bottom-center)."""
    style = (
        f"Style: Default,{font},{fontsize},&H00FFFFFF,&H000000FF,&H00101010,&H64000000,"
        f"1,0,0,0,100,100,0,0,1,4,2,2,90,90,{margin_v},1"
    )
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
         "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
         "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
         "MarginR, MarginV, Encoding"),
        style,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cue in cues:
        text = cue.text.replace("\n", "\\N").replace("{", "(").replace("}", ")")
        lines.append(
            f"Dialogue: 0,{_ass_ts(cue.start)},{_ass_ts(cue.end)},Default,,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"


def _run_ffmpeg(args: list[str]) -> None:
    try:
        subprocess.run(["ffmpeg", "-y", *args], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"")[-2000:]
        raise RuntimeError(f"ffmpeg failed ({e.returncode}): {tail!r}") from e


# -fflags +bitexact and -map_metadata -1 strip ffmpeg version/metadata so the
# extracted bytes are identical across runs - that stability is what lets the
# content-addressed cache (keyed on these bytes) actually hit on a re-run.
async def extract_frame(src_path: str, out_path: str) -> str:
    args = ["-fflags", "+bitexact", "-ss", "1", "-i", src_path,
            "-frames:v", "1", "-q:v", "2", "-map_metadata", "-1", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


def _probe_duration_sync(path: str) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            check=True, capture_output=True,
        )
        return float(out.stdout.decode().strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


async def extract_candidate_frames(src_path: str, out_dir: str, count: int = 8) -> list[str]:
    """Grab `count` evenly-spaced frames across the clip (skipping the very start/
    end where the subject is settling) as JPEGs — candidates for best-frame
    selection. Falls back to a single t=1s frame when the duration is unknown."""

    def _do() -> list[str]:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        dur = _probe_duration_sync(src_path)
        if dur <= 0.5:
            p = str(Path(out_dir) / "cand_00.jpg")
            _run_ffmpeg(["-ss", "1", "-i", src_path, "-frames:v", "1", "-q:v", "3",
                         "-map_metadata", "-1", p])
            return [p]
        lo, hi = max(0.3, dur * 0.06), max(0.6, dur * 0.94)
        paths: list[str] = []
        for i in range(count):
            ts = lo + (hi - lo) * i / max(1, count - 1)
            p = str(Path(out_dir) / f"cand_{i:02d}.jpg")
            _run_ffmpeg(["-ss", f"{ts:.3f}", "-i", src_path, "-frames:v", "1",
                         "-q:v", "3", "-map_metadata", "-1", p])
            paths.append(p)
        return paths

    return await anyio.to_thread.run_sync(_do)


async def transcode_image(src_path: str, out_path: str) -> str:
    """Re-encode an image to the container/codec implied by `out_path` (e.g. jpg->png)."""
    args = ["-fflags", "+bitexact", "-i", src_path, "-map_metadata", "-1", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def extract_audio(src_path: str, out_path: str) -> str:
    args = ["-fflags", "+bitexact", "-i", src_path, "-vn", "-ac", "1", "-ar", "44100",
            "-map_metadata", "-1", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def compress_for_clone(src_path: str, out_path: str, max_seconds: float = 300.0) -> str:
    """Mono MP3, length-capped, for voice-clone upload. Providers cap the sample
    file size (ElevenLabs IVC rejects > 11MB); 128kbps mono ≈ 1MB/min, so a 5-min
    cap stays well under the limit while preserving plenty of timbre for cloning."""
    args = ["-fflags", "+bitexact", "-i", src_path, "-vn", "-ac", "1", "-ar", "44100",
            "-t", f"{max_seconds}", "-b:a", "128k", "-map_metadata", "-1", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def silent_wav(out_path: str, seconds: float = 4.0) -> str:
    """A short silent mono track — fed to the talking-avatar model it yields an
    idle clip (mouth closed, natural blinks) to loop while waiting for input."""
    args = ["-fflags", "+bitexact", "-f", "lavfi",
            "-i", "anullsrc=channel_layout=mono:sample_rate=44100",
            "-t", f"{seconds}", "-ac", "1", "-ar", "44100",
            "-map_metadata", "-1", out_path]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def boomerang(src_path: str, out_path: str) -> str:
    """Forward + reversed copy concatenated, so the clip loops with no visible
    seam (the idle 'standby' breathes/blinks back and forth naturally)."""
    args = ["-i", src_path, "-filter_complex",
            "[0:v]reverse[r];[0:v][r]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map", "[v]", "-an", "-movflags", "+faststart", out_path]
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
