"""Background-music generation/sourcing — three candidates to A/B compare.

  1. fal_music       — fal Stable Audio 3 (instrumental, licensed) text->music
  2. elevenlabs_music — ElevenLabs Music API (POST /v1/music)
  3. scraped_music    — royalty-free track pulled from YouTube via yt-dlp

All best-effort: each raises on failure and the worker just drops that candidate.
"""
import asyncio
from pathlib import Path

import fal_client
import httpx

from doppel_api.config import get_settings
from doppel_api.providers import sourcing

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


async def scraped_music(query: str) -> tuple[bytes, dict] | None:
    """Royalty-free track via yt-dlp. Returns (mp3_bytes, meta) or None."""
    item = await sourcing.youtube_audio(query)
    if not item:
        return None
    data = Path(item["path"]).read_bytes()  # noqa: ASYNC240
    return data, {"title": item.get("title"), "url": item.get("url")}
