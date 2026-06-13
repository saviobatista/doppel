"""Self-hosted inference: LatentSync lip-sync + Cosmos3 image-to-video."""
from __future__ import annotations

import json

import httpx

from doppel_api.config import get_settings

def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Accept": "video/mp4"}
    if settings.inference_api_key:
        headers["Authorization"] = f"Bearer {settings.inference_api_key}"
    return headers


async def lipsync(video_path: str, audio_path: str) -> bytes:
    """Lip-sync video to audio via LatentSync (multipart POST, returns MP4 bytes)."""
    settings = get_settings()
    base = settings.avatar_api_base.rstrip("/")
    data = {
        "guidance_scale": str(settings.avatar_guidance_scale),
        "inference_steps": str(settings.avatar_inference_steps),
    }
    async with httpx.AsyncClient(timeout=1800) as client:
        with open(video_path, "rb") as vf, open(audio_path, "rb") as af:
            r = await client.post(
                f"{base}/v1/lipsync",
                data=data,
                files={
                    "video": ("video.mp4", vf, "video/mp4"),
                    "audio": ("audio.mp3", af, "audio/mpeg"),
                },
                headers=_auth_headers(),
            )
        r.raise_for_status()
        return r.content


async def broll_i2v(
    *,
    first_frame: bytes,
    prompt: str,
    negative_prompt: str = "",
    duration_sec: float,
    size: str | None = None,
    fps: float | None = None,
    steps: int | None = None,
    seed: int | None = None,
) -> bytes:
    """Image-to-video b-roll via Cosmos3 (multipart POST, returns MP4 bytes)."""
    settings = get_settings()
    base = settings.broll_api_base.rstrip("/")
    fps_val = fps if fps is not None else settings.broll_fast_fps
    size_val = size if size is not None else settings.broll_fast_size
    steps_val = steps if steps is not None else settings.broll_fast_steps
    num_frames = max(5, min(400, int(duration_sec * fps_val)))
    data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": size_val,
        "num_frames": str(num_frames),
        "fps": str(fps_val),
        "num_inference_steps": str(steps_val),
        "guidance_scale": "6.0",
        "flow_shift": "5.0",
        "extra_params": json.dumps({
            "use_resolution_template": False,
            "use_duration_template": False,
            "guardrails": False,
        }),
    }
    if seed is not None:
        data["seed"] = str(seed)
    async with httpx.AsyncClient(timeout=1800) as client:
        r = await client.post(
            f"{base}/v1/videos/sync",
            data=data,
            files={"input_reference": ("frame.png", first_frame, "image/png")},
            headers=_auth_headers(),
        )
        r.raise_for_status()
        return r.content
