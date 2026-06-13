import base64
import types

from doppel_api.providers import voice
from doppel_api.providers.media import CaptionCue


def test_group_alignment_to_words_groups_on_spaces():
    chars = list("Oi mundo")
    starts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    ends = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    cues = voice.group_alignment_to_words(chars, starts, ends)
    assert cues == [
        CaptionCue(text="Oi", start=0.0, end=0.2),
        CaptionCue(text="mundo", start=0.3, end=0.8),
    ]


async def test_clone_passes_readable_file_not_path(monkeypatch, tmp_path):
    # Regression: clone must hand the SDK a readable file object carrying the
    # audio bytes, NOT the path string (a path string uploads garbage and
    # ElevenLabs rejects it as "File is corrupted").
    sample = tmp_path / "sample.wav"
    sample.write_bytes(b"AUDIODATA")
    seen = {}

    class FakeIvc:
        def create(self, name, files):
            f = files[0]
            seen["has_read"] = hasattr(f, "read")
            seen["content"] = f.read()
            return types.SimpleNamespace(voice_id="voice-123")

    class FakeVoices:
        ivc = FakeIvc()

    class FakeClient:
        voices = FakeVoices()

    monkeypatch.setattr(voice, "_client", lambda: FakeClient())
    assert await voice.clone(str(sample), name="Doppel user") == "voice-123"
    assert seen["has_read"] is True
    assert seen["content"] == b"AUDIODATA"


async def test_tts_joins_byte_iterator(monkeypatch):
    class FakeTTS:
        def convert(self, voice_id, text, model_id, output_format):
            assert voice_id == "v1"
            return iter([b"AU", b"DIO"])

    class FakeClient:
        text_to_speech = FakeTTS()

    monkeypatch.setattr(voice, "_client", lambda: FakeClient())
    assert await voice.tts("v1", "olá") == b"AUDIO"


async def test_tts_with_timestamps_decodes_audio_and_builds_cues(monkeypatch):
    align = types.SimpleNamespace(
        characters=list("Oi mundo"),
        character_start_times_seconds=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
        character_end_times_seconds=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    )
    resp = types.SimpleNamespace(
        audio_base_64=base64.b64encode(b"MP3").decode(), alignment=align
    )

    class FakeTTS:
        def convert_with_timestamps(self, voice_id, text, model_id):
            return resp

    class FakeClient:
        text_to_speech = FakeTTS()

    monkeypatch.setattr(voice, "_client", lambda: FakeClient())
    audio, cues = await voice.tts_with_timestamps("v1", "Oi mundo")
    assert audio == b"MP3"
    assert cues[0] == CaptionCue(text="Oi", start=0.0, end=0.2)


async def test_stt_returns_text(monkeypatch, tmp_path):
    f = tmp_path / "a.wav"
    f.write_bytes(b"x")

    class FakeSTT:
        def convert(self, file, model_id):
            assert model_id == "scribe_v1"
            return types.SimpleNamespace(text="olá mundo", words=[])

    class FakeClient:
        speech_to_text = FakeSTT()

    monkeypatch.setattr(voice, "_client", lambda: FakeClient())
    assert await voice.stt(str(f)) == "olá mundo"
