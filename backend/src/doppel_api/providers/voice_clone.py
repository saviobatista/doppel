"""Multi-provider voice-clone candidates for the voice-setup A/B.

Clones the sample and renders a short preview line in a few provider/model
variants so the user can pick the best-sounding option (HeyGen-style). Real
ElevenLabs today (one instant clone, several model renderings); extra providers
(Fish, ...) light up only when their key is configured. Every candidate is
best-effort and degrades gracefully — a provider failing just drops its card.
"""
import httpx

from doppel_api.config import get_settings
from doppel_api.constants import VOICE_PREVIEW_LINE
from doppel_api.providers import voice

# (provider, human label, ElevenLabs model_id). One instant clone is reused for
# all ElevenLabs cards; only the synthesis model differs per preview.
_ELEVEN_CANDIDATES = [
    ("elevenlabs", "ElevenLabs Multilingual v2", "eleven_multilingual_v2"),
    ("elevenlabs", "ElevenLabs Turbo v2.5", "eleven_turbo_v2_5"),
    ("elevenlabs", "ElevenLabs v3", "eleven_v3"),
]


async def elevenlabs_previews(
    external_id: str, *, preview_text: str = VOICE_PREVIEW_LINE
) -> list[dict]:
    """Render the same instant clone in a few ElevenLabs models as A/B cards.
    No new voice is created here — only TTS against an existing `external_id`."""
    out: list[dict] = []
    for provider, label, model in _ELEVEN_CANDIDATES:
        try:
            audio = await voice.tts(external_id, preview_text, model=model)
        except Exception as exc:  # a single model card degrades
            print(f"elevenlabs preview {model} failed: {exc!r}")
            continue
        out.append({
            "provider": provider, "label": label, "model": model,
            "external_id": external_id, "preview_bytes": audio,
        })
    return out


async def fish_candidate(
    sample_path: str, *, preview_text: str = VOICE_PREVIEW_LINE
) -> dict | None:
    if not get_settings().fish_api_key:
        return None
    return await _fish_candidate(sample_path, preview_text)


async def _fish_candidate(sample_path: str, preview_text: str) -> dict | None:
    """Fish Audio clone + preview. Best-effort; only runs when FISH_API_KEY is set.
    (Untested without a key — verify the request shape against fish.audio docs.)"""
    key = get_settings().fish_api_key
    headers = {"Authorization": f"Bearer {key}"}
    try:
        with open(sample_path, "rb") as f:  # noqa: ASYNC230 (one-shot, key-gated path)
            sample = f.read()
        async with httpx.AsyncClient(timeout=120) as c:
            created = await c.post(
                "https://api.fish.audio/model", headers=headers,
                data={"title": "doppel-voice", "type": "tts", "train_mode": "fast"},
                files={"voices": ("sample.wav", sample, "audio/wav")},
            )
            created.raise_for_status()
            model_id = created.json().get("_id")
            if not model_id:
                return None
            tts = await c.post(
                "https://api.fish.audio/v1/tts", headers=headers,
                json={"text": preview_text, "reference_id": model_id, "format": "mp3"},
            )
            tts.raise_for_status()
            return {
                "provider": "fish", "label": "Fish Audio", "model": "fish-speech",
                "external_id": model_id, "preview_bytes": tts.content,
            }
    except Exception as exc:
        print(f"fish clone failed: {exc!r}")
        return None
