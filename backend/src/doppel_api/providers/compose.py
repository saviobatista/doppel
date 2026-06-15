"""Phase-1 plan-generation compositing — pure ffmpeg/ffprobe, no network.

The plan-generation worker builds one normalized vertical clip per scene
(talking-avatar lip-sync or Ken-Burns b-roll), burns the scene's overlay PNG
and word-timed captions, then xfade-concats the scenes per their planned
transitions and mixes the chosen music track under the voiceover with
sidechain ducking. Every clip is normalized to the same resolution / fps /
SAR / pixel format / audio layout so xfade and acrossfade can chain them.
"""
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import anyio

from doppel_api.providers.media import CaptionCue, _run_ffmpeg, build_ass

W, H = 1080, 1920  # vertical 9:16 target
FPS = 30
SAR = 44100  # audio sample rate for every clip

# Plan `transition_out.type` -> ffmpeg xfade transition. Unknown types fall back
# to a soft dissolve; "cut" is rendered as a near-instant fade so the xfade graph
# stays uniform (a true hard cut still looks like a cut at 0.06s).
_XFADE = {
    "whip": "slideleft",
    "swipe": "slideleft",
    "slide": "slideright",
    "cut": "fade",
    "hardcut": "fade",
    "zoom": "zoomin",
    "punch": "zoomin",
    "crossfade": "dissolve",
    "dissolve": "dissolve",
    "fade": "fadeblack",
    "fadeblack": "fadeblack",
    "fadewhite": "fadewhite",
}
_DEFAULT_TRANS_DUR = 0.4
_CUT_TRANS_DUR = 0.06


@dataclass
class SceneSpec:
    """Everything needed to render one normalized scene clip."""

    out_path: str
    duration: float
    # base visual — exactly one of:
    video_path: str | None = None  # talking-avatar (lip-sync) clip
    image_path: str | None = None  # still for Ken-Burns
    kb_index: int = 0  # scene index — alternates the Ken-Burns pan direction
    audio_path: str | None = None  # voiceover; None -> silent for `duration`
    overlay_png: str | None = None
    overlay_anchor: str = "lower"  # top | upper | center | lower | bottom
    overlay_anim: str = "fade"  # slide_up | slide_down | fade | pop
    cues: list[CaptionCue] = field(default_factory=list)
    font: str = "DejaVu Sans"


@dataclass
class Segment:
    """A rendered scene clip plus the transition OUT of it into the next scene."""

    path: str
    duration: float
    transition: str = "cut"
    trans_dur: float = _CUT_TRANS_DUR


def _ffprobe(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", *args], check=True, capture_output=True
        )
        return out.stdout.decode().strip()
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or b"")[-800:]
        raise RuntimeError(f"ffprobe failed ({e.returncode}): {tail!r}") from e


async def probe_duration(path: str) -> float:
    """Container duration in seconds (audio or video), 0.0 if unknown."""

    def _do() -> float:
        out = _ffprobe(
            ["-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", path]
        )
        try:
            return float(out)
        except ValueError:
            return 0.0

    return await anyio.to_thread.run_sync(_do)


def _ken_burns(dur: float, kb_index: int) -> str:
    """Ken-Burns video chain: cover-crop to vertical, upscale, then a slow zoom
    with a slight pan whose direction alternates per scene for visual variety."""
    frames = max(1, round(dur * FPS))
    inc = 0.16 / frames  # reach ~1.16x zoom by the end of the scene
    y = "ih/2-(ih/zoom/2)"
    if kb_index % 2 == 0:  # ease toward the right third
        x = f"(iw-iw/zoom)*on/{frames}"
    else:  # ease toward the left third
        x = f"(iw-iw/zoom)*(1-on/{frames})"
    return (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
        f"scale={2 * W}:{2 * H},"
        f"zoompan=z='min(zoom+{inc:.6f},1.16)':d={frames}:x='{x}':y='{y}'"
        f":s={W}x{H}:fps={FPS},setsar=1"
    )


# overlay top-left Y as an ffmpeg expression of frame height H and overlay height h.
_ANCHOR_Y = {
    "top": "48",
    "upper": f"({H}*0.12)",
    "center": "((H-h)/2)",
    "lower": f"({H}*0.64)",
    "bottom": f"({H}-h-72)",
}
_OVL_IN, _OVL_OUT, _OVL_SLIDE = 0.45, 0.35, 90


def _overlay_chains(overlay_idx: int, label: str, spec: SceneSpec) -> list[str]:
    """Scale the overlay, fade it in/out (alpha), and place it at the planned
    vertical anchor with an entrance animation (slide/pop/fade)."""
    base_y = _ANCHOR_Y.get(spec.overlay_anchor, _ANCHOR_Y["lower"])
    fout = max(0.0, spec.duration - _OVL_OUT)
    fade = (f"format=rgba,fade=t=in:st=0:d={_OVL_IN}:alpha=1,"
            f"fade=t=out:st={fout:.2f}:d={_OVL_OUT}:alpha=1")

    anim = spec.overlay_anim or "fade"
    if anim == "slide_up":
        y = f"{base_y} + {_OVL_SLIDE}*max(0\\,1-(t/{_OVL_IN}))"
    elif anim == "slide_down":
        y = f"{base_y} - {_OVL_SLIDE}*max(0\\,1-(t/{_OVL_IN}))"
    elif anim == "pop":  # snappy short rise — reads as a punchy entrance
        y = f"{base_y} + 36*max(0\\,1-(t/0.22))"
    else:  # fade / none — no positional motion
        y = base_y

    return [
        f"[{overlay_idx}:v]scale='min(iw,{W - 110})':-1,{fade}[ovl]",
        f"[{label}][ovl]overlay=x=(W-w)/2:y='{y}':eval=frame:format=auto[ov]",
    ]


async def render_scene(spec: SceneSpec) -> str:
    """Render one scene to a normalized WxH/FPS clip with audio, overlay, captions."""
    args: list[str] = []
    # --- base visual input (index 0) ---
    if spec.image_path:
        args += ["-loop", "1", "-t", f"{spec.duration:.3f}", "-i", spec.image_path]
        base_src = _ken_burns(spec.duration, spec.kb_index)
    elif spec.video_path:
        args += ["-i", spec.video_path]
        base_src = (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},fps={FPS},setsar=1"
        )
    else:
        raise ValueError("scene needs an image_path or video_path")

    # --- optional overlay PNG, then audio (each gets the next input index) ---
    idx = 1
    overlay_idx = None
    if spec.overlay_png:
        # Loop the still as a stream for the scene so the alpha fade / slide
        # animate over time (a single-frame input would freeze at fade-in t=0).
        args += ["-loop", "1", "-t", f"{spec.duration:.3f}", "-i", spec.overlay_png]
        overlay_idx = idx
        idx += 1
    if spec.audio_path:
        args += ["-i", spec.audio_path]
        audio_chain = f"[{idx}:a]aresample={SAR},aformat=channel_layouts=stereo[a]"
    else:
        args += ["-f", "lavfi", "-t", f"{spec.duration:.3f}",
                 "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAR}"]
        audio_chain = f"[{idx}:a]anull[a]"

    chains = [f"[0:v]{base_src}[base]"]
    label = "base"
    if overlay_idx is not None:
        chains += _overlay_chains(overlay_idx, label, spec)
        label = "ov"

    ass_path = str(Path(spec.out_path).with_suffix(".ass"))
    if spec.cues:
        safe = ass_path.replace(":", r"\:")
        chains.append(f"[{label}]ass={safe}[v]")
    else:
        chains.append(f"[{label}]null[v]")
    chains.append(audio_chain)

    args += [
        "-filter_complex", ";".join(chains),
        "-map", "[v]", "-map", "[a]",
        "-r", str(FPS), "-t", f"{spec.duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", str(SAR), "-ac", "2",
        spec.out_path,
    ]

    def _do() -> None:
        if spec.cues:
            Path(ass_path).write_text(build_ass(spec.cues, spec.font, width=W, height=H),
                                      encoding="utf-8")
        _run_ffmpeg(args)

    await anyio.to_thread.run_sync(_do)
    return spec.out_path


def _trans_for(seg: Segment, this_dur: float, next_dur: float) -> tuple[str, float]:
    name = _XFADE.get((seg.transition or "cut").lower(), "dissolve")
    tr = _CUT_TRANS_DUR if (seg.transition or "").lower() in ("cut", "hardcut") else seg.trans_dur
    # A transition cannot be longer than (most of) either neighbouring clip.
    tr = max(0.04, min(tr, 0.6 * min(this_dur, next_dur)))
    return name, tr


async def concat_transitions(segments: list[Segment], out_path: str) -> str:
    """xfade-concat normalized scene clips per their transitions; acrossfade the
    audio so it stays in lockstep with the shortened video timeline."""
    if not segments:
        raise ValueError("no segments to concat")
    if len(segments) == 1:
        # Single scene: still normalize through the encoder so downstream mixing
        # gets a clean container.
        args = ["-i", segments[0].path, "-c", "copy", out_path]
        await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
        return out_path

    args: list[str] = []
    for seg in segments:
        args += ["-i", seg.path]

    durs = [s.duration for s in segments]
    vchains: list[str] = []
    achains: list[str] = []
    vlabel = "0:v"
    alabel = "0:a"
    cum = durs[0]
    cum_tr = 0.0
    for i in range(len(segments) - 1):
        name, tr = _trans_for(segments[i], durs[i], durs[i + 1])
        offset = cum - cum_tr - tr
        vout = f"vx{i}" if i < len(segments) - 2 else "vout"
        aout = f"ax{i}" if i < len(segments) - 2 else "aout"
        vchains.append(
            f"[{vlabel}][{i + 1}:v]xfade=transition={name}:duration={tr:.3f}"
            f":offset={offset:.3f}[{vout}]"
        )
        achains.append(f"[{alabel}][{i + 1}:a]acrossfade=d={tr:.3f}[{aout}]")
        vlabel, alabel = vout, aout
        cum += durs[i + 1]
        cum_tr += tr

    args += [
        "-filter_complex", ";".join(vchains + achains),
        "-map", "[vout]", "-map", "[aout]",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", str(SAR), "-ac", "2",
        out_path,
    ]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def mix_music(
    video_path: str, music_path: str, out_path: str, *, gain: float = 0.10, duck: bool = True
) -> str:
    """Loop/trim the music bed under the video's voiceover. When `duck`, the music
    is aggressively sidechain-compressed by the voice so narration always sits on
    top; the bed is kept quiet (low `gain`) so it never overpowers the VO."""
    if duck:
        graph = (
            f"[1:a]aresample={SAR},volume={gain:.3f}[mraw];"
            f"[mraw][0:a]sidechaincompress=threshold=0.025:ratio=12:attack=5:release=320[mduck];"
            f"[0:a][mduck]amix=inputs=2:duration=first:normalize=0[a]"
        )
    else:
        graph = (
            f"[1:a]aresample={SAR},volume={gain:.3f}[mraw];"
            f"[0:a][mraw]amix=inputs=2:duration=first:normalize=0[a]"
        )
    args = [
        "-i", video_path, "-stream_loop", "-1", "-i", music_path,
        "-filter_complex", graph,
        "-map", "0:v", "-map", "[a]",
        "-c:v", "copy", "-c:a", "aac", "-ar", str(SAR), "-ac", "2",
        "-shortest", out_path,
    ]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def render_overlay_preview(
    overlay_png: str, out_path: str, *, anchor: str = "lower", anim: str = "fade",
    duration: float = 3.2,
) -> str:
    """A standalone preview clip: the overlay animated over a BLACK 9:16 frame at
    the exact target resolution — so the plan UI shows precisely how the element
    will animate and sit in the final video. Silent, loops cleanly."""
    spec = SceneSpec(out_path=out_path, duration=duration, overlay_anchor=anchor, overlay_anim=anim)
    args = [
        "-f", "lavfi", "-t", f"{duration:.3f}", "-i", f"color=c=black:s={W}x{H}:r={FPS}",
        "-loop", "1", "-t", f"{duration:.3f}", "-i", overlay_png,
    ]
    chains = ["[0:v]setsar=1[base]", *_overlay_chains(1, "base", spec)]
    args += [
        "-filter_complex", ";".join(chains),
        "-map", "[ov]", "-an", "-r", str(FPS), "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out_path,
    ]
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path
