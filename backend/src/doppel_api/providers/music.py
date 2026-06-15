"""Background-music generation — two candidates to A/B compare.

  1. fal_music        — fal Stable Audio 3 (instrumental, licensed) text->music
  2. elevenlabs_music — ElevenLabs Music API (POST /v1/music)

All best-effort: each raises on failure and the worker just drops that candidate.
"""
import asyncio

import fal_client
import httpx

from doppel_api.config import get_settings

MUSIC_TIMEOUT = 240.0


async def fal_music(prompt: str, seconds: int = 30) -> bytes:
    result = await asyncio.wait_for(
        fal_client.subscribe_async(
            get_settings().fal_music_model,
            arguments={"prompt": prompt, "duration": seconds},
        ),
        timeout=MUSIC_TIMEOUT,
    )
    audio = result.get("audio_file") or result.get("audio") or {}
    url = audio.get("url") if isinstance(audio, dict) else None
    if not url:
        raise RuntimeError(f"fal music: no audio url in {result!r}")
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url)
        r.raise_for_status()
        return r.content


async def elevenlabs_music(prompt: str, ms: int = 30000) -> bytes:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=MUSIC_TIMEOUT) as c:
        r = await c.post(
            "https://api.elevenlabs.io/v1/music",
            params={"output_format": "mp3_44100_128"},
            headers={"xi-api-key": settings.elevenlabs_api_key,
                     "Content-Type": "application/json"},
            json={"prompt": prompt, "music_length_ms": ms, "force_instrumental": True},
        )
        r.raise_for_status()
        return r.content
