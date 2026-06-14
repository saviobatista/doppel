"""ElevenLabs: instant voice clone, TTS (+ timestamps), and Scribe STT."""
import base64
from pathlib import Path

import anyio
from elevenlabs import ElevenLabs

from doppel_api.config import get_settings
from doppel_api.providers.media import CaptionCue


def _client() -> ElevenLabs:
    return ElevenLabs(api_key=get_settings().elevenlabs_api_key)


def group_alignment_to_words(
    characters: list[str], starts: list[float], ends: list[float]
) -> list[CaptionCue]:
    cues: list[CaptionCue] = []
    word = ""
    word_start: float | None = None
    last_end = 0.0
    for ch, s, e in zip(characters, starts, ends, strict=False):
        if ch.isspace():
            if word:
                cues.append(CaptionCue(text=word, start=word_start or 0.0, end=last_end))
                word = ""
                word_start = None
            continue
        if not word:
            word_start = s
        word += ch
        last_end = e
    if word:
        cues.append(CaptionCue(text=word, start=word_start or 0.0, end=last_end))
    return cues


async def clone(sample_path: str, name: str) -> str:
    def _do() -> str:
        # ElevenLabs IVC needs a readable file object, not a path string;
        # passing the path makes it upload garbage ("File is corrupted").
        with Path(sample_path).open("rb") as f:
            created = _client().voices.ivc.create(name=name, files=[f])
        return created.voice_id

    return await anyio.to_thread.run_sync(_do)


async def list_voice_ids() -> list[tuple[str, str]]:
    """All voices on the account as (voice_id, name) — used to prune our orphans."""
    def _do() -> list[tuple[str, str]]:
        resp = _client().voices.get_all()
        return [(v.voice_id, v.name or "") for v in resp.voices]

    return await anyio.to_thread.run_sync(_do)


async def delete(voice_id: str) -> None:
    await anyio.to_thread.run_sync(lambda: _client().voices.delete(voice_id))


async def prune_orphans(keep_ids: set[str], prefix: str = "doppel") -> int:
    """Delete account voices we created (name starts with `prefix`) that are no
    longer referenced by any avatar/voice. Frees space against the EL voice cap."""
    deleted = 0
    for voice_id, name in await list_voice_ids():
        if name.startswith(prefix) and voice_id not in keep_ids:
            try:
                await delete(voice_id)
                deleted += 1
            except Exception as exc:  # best-effort cleanup
                print(f"prune: failed to delete {voice_id}: {exc!r}")
    return deleted


async def tts(voice_id: str, text: str, model: str | None = None) -> bytes:
    model_id = model or get_settings().elevenlabs_model

    def _do() -> bytes:
        stream = _client().text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=model_id,
            output_format="mp3_44100_128",
        )
        return b"".join(stream)

    return await anyio.to_thread.run_sync(_do)


async def tts_with_timestamps(voice_id: str, text: str) -> tuple[bytes, list[CaptionCue]]:
    def _do() -> tuple[bytes, list[CaptionCue]]:
        resp = _client().text_to_speech.convert_with_timestamps(
            voice_id=voice_id, text=text, model_id=get_settings().elevenlabs_model
        )
        audio = base64.b64decode(resp.audio_base_64)  # SDK field is audio_base_64, not audio_base64
        a = resp.alignment
        cues = group_alignment_to_words(
            a.characters, a.character_start_times_seconds, a.character_end_times_seconds
        )
        return audio, cues

    return await anyio.to_thread.run_sync(_do)


async def stt(audio_path: str) -> str:
    def _do() -> str:
        with Path(audio_path).open("rb") as f:
            result = _client().speech_to_text.convert(file=f, model_id="scribe_v1")
        return result.text

    return await anyio.to_thread.run_sync(_do)
