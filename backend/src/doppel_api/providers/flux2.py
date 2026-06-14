"""Self-hosted FLUX.2 text-to-image (Starya inference cluster).

JSON POST /v1/images/generations → OpenAI-style envelope with a base64 PNG.
Worker pods are CPU-only HTTP clients; the GPU stays on the inference Deployment.
"""
import base64

import httpx

from doppel_api.config import get_settings

# A wedged inference pod must not pin the worker lane forever; T2I is a single
# fast (~4-step) image, so a generous-but-bounded budget is enough.
GENERATE_TIMEOUT = 300.0


async def generate(
    prompt: str,
    *,
    width: int = 832,
    height: int = 480,
    num_inference_steps: int = 4,
    guidance_scale: float = 1.0,
    seed: int = 0,
) -> bytes:
    base = get_settings().broll_flux_api_base.rstrip("/")
    if not base:
        raise RuntimeError("BROLL_FLUX_API_BASE not configured")
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "seed": seed,
    }
    async with httpx.AsyncClient(timeout=GENERATE_TIMEOUT) as client:
        resp = await client.post(f"{base}/v1/images/generations", json=payload)
        resp.raise_for_status()
        return base64.b64decode(resp.json()["data"][0]["b64_json"])
