# Doppel fal.ai Generation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the M0 ffmpeg-stub generation with real managed providers - Anthropic Claude (script), ElevenLabs (voice clone/TTS/STT), fal.ai (Fabric talking avatar, FLUX+Kling b-roll), ffmpeg (captions/compose) - keeping Postgres, floci/S3 storage, and the Redis Streams + SSE skeleton untouched.

**Architecture:** A new `backend/src/doppel_api/providers/` package holds one thin async module per capability. The worker (`workers/worker.py`, renamed from `stub_worker.py`) keeps `process_one`, the lanes, and the failure path; only the two handlers (`handle_avatar_prep`, `handle_fast_generate`) are rewritten to orchestrate the providers. Sync SDK calls (Anthropic, ElevenLabs) run in `anyio.to_thread`; fal uses its native `*_async` methods. Provider modules are monkeypatched in handler tests (M0 pattern) and unit-tested with injected fake clients - zero paid calls in CI.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Redis Streams, boto3/floci, ffmpeg, `fal-client`, `elevenlabs`, `anthropic`, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-13-doppel-fal-pipeline-design.md`

**Verified SDK facts** (baked into the code below - do not "fix" these):
- `fal_client.subscribe_async(model, arguments={...})` returns the result dict directly: `result["video"]["url"]`, `result["images"][0]["url"]`. `fal_client.upload_file_async(path) -> str` (a URL). Reads `FAL_KEY` from env automatically.
- Fabric `veed/fabric-1.0` inputs: `image_url`, `audio_url`, `resolution` ("480p"|"720p"). Output: `result["video"]["url"]`.
- Kling `fal-ai/kling-video/v2.1/standard/image-to-video` inputs: `prompt`, `image_url`, `duration` (STRING "5"|"10"), `cfg_scale`. Output: `result["video"]["url"]`.
- FLUX `fal-ai/flux/schnell` inputs: `prompt`, `image_size` (enum, e.g. "portrait_16_9"), `num_images`. Output: `result["images"][0]["url"]`.
- ElevenLabs: `client.voices.ivc.create(name=, files=[paths]) -> .voice_id`; `client.text_to_speech.convert(voice_id=, text=, model_id=, output_format=)` returns an **iterator of bytes** (join with `b"".join(...)`); `client.text_to_speech.convert_with_timestamps(voice_id=, text=, model_id=)` returns `.audio_base64` (base64) + `.alignment.characters` / `.character_start_times_seconds` / `.character_end_times_seconds` (**per character**); `client.speech_to_text.convert(file=, model_id="scribe_v1")` returns `.text` + `.words[]` (`.text/.start/.end/.type`).
- Anthropic: model `claude-sonnet-4-6` direct; forced tool use - `tools=[{name, input_schema}]`, `tool_choice={"type":"tool","name":...}`, read `next(b.input for b in resp.content if b.type=="tool_use")`.

**Scope decisions** (from spec): no Supabase (ignore `SUPABASE_*` in `.env`); no schema migration (new fields go in the JSON `assets` of existing rows); no soundtrack; frontend stays on host (no `web` compose service); fast track only (no HQ track).

---

## File Structure

```
backend/
  pyproject.toml                         # + fal-client, elevenlabs, anthropic, httpx (already dev) as runtime
  src/doppel_api/
    config.py                            # + provider fields (raw env names via AliasChoices)
    constants.py                         # NEW: HELLO_LINE, FEEDBACK_LINE (PT-BR fixed lines)
    providers/
      __init__.py                        # NEW (empty)
      media.py                           # NEW: ffmpeg + srt + download; CaptionCue, BrollClip dataclasses
      script.py                          # NEW: Anthropic build_script(transcript) -> dict
      voice.py                           # NEW: ElevenLabs clone/tts/tts_with_timestamps/stt + word cues
      video.py                           # NEW: fal upload/talking/image/broll
  workers/
    worker.py                            # RENAMED from stub_worker.py; handlers rewritten
  tests/
    test_config_providers.py             # NEW
    test_provider_media.py               # NEW
    test_provider_script.py              # NEW
    test_provider_voice.py               # NEW
    test_provider_video.py               # NEW
    test_worker.py                       # RENAMED from test_stub_worker.py; rewritten handler tests
  scripts/
    live_smoke.py                        # NEW: opt-in real end-to-end (gated by DOPPEL_LIVE_SMOKE=1)
docker-compose.yml                       # api + stub-worker -> env_file: .env; worker command path
.env.example                             # documents all provider vars; marks SUPABASE_* unused
```

---

### Task 1: Provider dependencies, config fields, compose env wiring

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/src/doppel_api/config.py`
- Create: `backend/src/doppel_api/constants.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Test: `backend/tests/test_config_providers.py`

- [ ] **Step 1: Add runtime deps**

In `backend/pyproject.toml`, add to `[project] dependencies` (after `"anyio>=4.0",`):

```toml
    "fal-client>=0.5",
    "elevenlabs>=1.50",
    "anthropic>=0.69",
    "httpx>=0.28",
```

(`httpx` was a dev dep for tests; it is now also a runtime dep for downloading fal output files. Keep it in dev too - duplicate is harmless, or remove from dev. Leave dev as-is.)

Run: `cd /Users/savio/Project/backend && uv sync`
Expected: resolves and installs the three SDKs.

- [ ] **Step 2: Write the failing config test**

`backend/tests/test_config_providers.py`:

```python
from doppel_api.config import Settings


def test_provider_settings_read_raw_env_names(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fal-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-secret")
    monkeypatch.setenv("FAL_T2I_MODEL", "fal-ai/flux/schnell")
    monkeypatch.setenv("PIPELINE_CONCURRENCY", "3")
    s = Settings()
    assert s.fal_key == "fal-secret"
    assert s.anthropic_api_key == "anthropic-secret"
    assert s.anthropic_model == "claude-sonnet-4-6"
    assert s.elevenlabs_api_key == "el-secret"
    assert s.fal_t2i_model == "fal-ai/flux/schnell"
    assert s.pipeline_concurrency == 3


def test_provider_settings_defaults():
    s = Settings()
    assert s.elevenlabs_model == "eleven_multilingual_v2"
    assert s.fal_lipsync_model == "veed/fabric-1.0"
    assert s.fal_broll_model == "fal-ai/kling-video/v2.1/standard/image-to-video"
    assert s.fal_t2i_model == "fal-ai/flux/schnell"
    assert s.caption_font == "DejaVu Sans"
    assert s.pipeline_concurrency == 4
```

Run: `uv run pytest tests/test_config_providers.py -q`
Expected: FAIL (fields do not exist).

- [ ] **Step 3: Add the fields to Settings**

The M0 `Settings` uses `env_prefix="DOPPEL_"`. The provider vars use RAW names (`FAL_KEY`, not `DOPPEL_FAL_KEY`), so each needs an explicit `validation_alias` that bypasses the prefix. Edit `backend/src/doppel_api/config.py`:

```python
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPEL_", extra="ignore")

    database_url: str = "postgresql+asyncpg://doppel:doppel@localhost:5432/doppel"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:4566"
    s3_bucket: str = "doppel-media"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"

    # Managed providers - raw env names (no DOPPEL_ prefix), so use validation_alias.
    anthropic_api_key: str = Field(default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY"))
    anthropic_model: str = Field(
        default="claude-sonnet-4-6", validation_alias=AliasChoices("ANTHROPIC_MODEL")
    )
    elevenlabs_api_key: str = Field(default="", validation_alias=AliasChoices("ELEVENLABS_API_KEY"))
    elevenlabs_model: str = Field(
        default="eleven_multilingual_v2", validation_alias=AliasChoices("ELEVENLABS_MODEL")
    )
    fal_key: str = Field(default="", validation_alias=AliasChoices("FAL_KEY"))
    fal_lipsync_model: str = Field(
        default="veed/fabric-1.0", validation_alias=AliasChoices("FAL_LIPSYNC_MODEL")
    )
    fal_broll_model: str = Field(
        default="fal-ai/kling-video/v2.1/standard/image-to-video",
        validation_alias=AliasChoices("FAL_BROLL_MODEL"),
    )
    fal_t2i_model: str = Field(
        default="fal-ai/flux/schnell", validation_alias=AliasChoices("FAL_T2I_MODEL")
    )
    caption_font: str = Field(default="DejaVu Sans", validation_alias=AliasChoices("CAPTION_FONT"))
    pipeline_concurrency: int = Field(
        default=4, validation_alias=AliasChoices("PIPELINE_CONCURRENCY")
    )

    @field_validator("s3_endpoint", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Keep the existing `field_validator` import. Add to the top imports: `from pydantic import AliasChoices, Field, field_validator` (merge with the existing `field_validator` import line). The `extra="ignore"` lets the `SUPABASE_*` env vars coexist without error.

Run: `uv run pytest tests/test_config_providers.py -q`
Expected: `2 passed`.

- [ ] **Step 4: Fixed PT-BR lines constant**

`backend/src/doppel_api/constants.py`:

```python
"""Fixed PT-BR product lines spoken by the avatar (mirror of frontend strings)."""

HELLO_LINE = "Oi! Eu sou você aprimorado! O que vamos fazer hoje?"
FEEDBACK_LINE = "Não gostou? O que quer mudar?"
```

- [ ] **Step 5: Wire secrets into compose via env_file**

In `docker-compose.yml`, add `env_file: .env` to BOTH `api` and `stub-worker` so the provider keys flow from the host `.env` (the existing inline `environment:` block stays for the DOPPEL_/AWS values). For `api`:

```yaml
  api:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    environment: &doppel_env
      PYTHONUNBUFFERED: "1"
      DOPPEL_DATABASE_URL: postgresql+asyncpg://doppel:doppel@postgres:5432/doppel
      DOPPEL_REDIS_URL: redis://redis:6379/0
      DOPPEL_S3_ENDPOINT: http://floci:4566
      DOPPEL_S3_BUCKET: doppel-media
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
      AWS_DEFAULT_REGION: us-east-1
    ports: ["8200:8000"]
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
      floci: {condition: service_started}
```

For `stub-worker`, add `env_file: .env` above `environment: *doppel_env`:

```yaml
  stub-worker:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    command: ["python", "-m", "workers.worker"]
    environment: *doppel_env
    depends_on:
      api: {condition: service_started}
```

Note the `command` now points at `workers.worker` (renamed in Task 2). env_file values do not override the explicit `environment:` block (compose precedence: `environment` wins), so the DOPPEL_ overrides stay correct while the raw provider keys come from `.env`.

- [ ] **Step 6: Update .env.example**

Replace `.env.example` with:

```bash
# --- Frontend (vite) ---
VITE_API_URL=http://localhost:8200

# --- Backend (uvicorn local, outside compose) ---
DOPPEL_DATABASE_URL=postgresql+asyncpg://doppel:doppel@localhost:5432/doppel
DOPPEL_REDIS_URL=redis://localhost:6379/0
DOPPEL_S3_ENDPOINT=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1

# --- Managed providers (real keys; never commit the real .env) ---
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6
ELEVENLABS_API_KEY=...
ELEVENLABS_MODEL=eleven_multilingual_v2
FAL_KEY=...
FAL_LIPSYNC_MODEL=veed/fabric-1.0
FAL_BROLL_MODEL=fal-ai/kling-video/v2.1/standard/image-to-video
FAL_T2I_MODEL=fal-ai/flux/schnell
CAPTION_FONT=DejaVu Sans
PIPELINE_CONCURRENCY=4

# SUPABASE_* are intentionally unused in this iteration (Postgres + floci stay).

# Browser access to presigned URLs (dev): presigns point at http://floci:4566.
# Add to /etc/hosts once:  127.0.0.1 floci
```

- [ ] **Step 7: Full suite + commit**

Run: `uv run pytest -q && uv run ruff check src tests`
Expected: all green (config tests pass, nothing else regressed).

```bash
cd /Users/savio/Project
git add backend/pyproject.toml backend/uv.lock backend/src/doppel_api/config.py backend/src/doppel_api/constants.py backend/tests/test_config_providers.py docker-compose.yml .env.example
git commit -m "feat(providers): add provider deps, config fields, compose env_file wiring"
```

---

### Task 2: Rename stub_worker -> worker (behavior-preserving)

The worker is no longer a stub. Rename it now so all later tasks reference the final path; this step changes NO behavior (M0 tests still pass, just under new names).

**Files:**
- Rename: `backend/workers/stub_worker.py` -> `backend/workers/worker.py`
- Rename: `backend/tests/test_stub_worker.py` -> `backend/tests/test_worker.py`

- [ ] **Step 1: git mv both files**

```bash
cd /Users/savio/Project/backend
git mv workers/stub_worker.py workers/worker.py
git mv tests/test_stub_worker.py tests/test_worker.py
```

- [ ] **Step 2: Update the test's imports**

In `backend/tests/test_worker.py`, replace every `workers.stub_worker` / `stub_worker` reference with `workers.worker` / `worker`. Concretely the import block becomes:

```python
from workers import worker
from workers.worker import WorkerContext, process_one
```

and any `monkeypatch.setattr(stub_worker, ...)` / `monkeypatch.setattr(worker, ...)` calls use `worker` (the imported module alias). Update the module docstring reference if present.

- [ ] **Step 3: Update the module docstring**

In `backend/workers/worker.py`, change the top docstring from the M0 stub wording to:

```python
"""Doppel generation worker: consumes jobs and drives the managed providers."""
```

(The body is rewritten in Tasks 7-8; leave it functional for now so the rename stays green.)

- [ ] **Step 4: Run the suite**

Run: `uv run pytest -q && uv run ruff check src tests workers`
Expected: all green (same tests, new names).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(worker): rename stub_worker to worker (no behavior change)"
```

---

### Task 3: providers/media.py (ffmpeg, SRT, download)

**Files:**
- Create: `backend/src/doppel_api/providers/__init__.py` (empty)
- Create: `backend/src/doppel_api/providers/media.py`
- Test: `backend/tests/test_provider_media.py`

- [ ] **Step 1: Write failing tests**

`backend/tests/test_provider_media.py`:

```python
import pytest

from doppel_api.providers import media
from doppel_api.providers.media import BrollClip, CaptionCue, build_srt


def test_build_srt_formats_cues():
    srt = build_srt([
        CaptionCue(text="Olá", start=0.0, end=1.25),
        CaptionCue(text="mundo", start=1.25, end=2.5),
    ])
    assert "1\n00:00:00,000 --> 00:00:01,250\nOlá\n" in srt
    assert "2\n00:00:01,250 --> 00:00:02,500\nmundo\n" in srt


def test_compose_args_structure():
    args = media._compose_args(
        avatar_path="avatar.mp4",
        brolls=[BrollClip(path="b0.mp4", start=5.0, end=10.0)],
        srt_path="caps.srt",
        out_path="out.mp4",
        font="DejaVu Sans",
    )
    joined = " ".join(args)
    assert "-i avatar.mp4" in joined
    assert "-i b0.mp4" in joined
    assert "overlay=enable='between(t,5.0,10.0)'" in joined
    assert "subtitles=" in joined
    assert "DejaVu Sans" in joined
    assert args[-1] == "out.mp4"


async def test_download_writes_fetched_bytes(tmp_path, monkeypatch):
    async def fake_fetch(url: str) -> bytes:
        assert url == "https://fal.media/x.mp4"
        return b"VIDEO"

    monkeypatch.setattr(media, "_fetch", fake_fetch)
    out = str(tmp_path / "x.mp4")
    result = await media.download("https://fal.media/x.mp4", out)
    assert result == out
    with open(out, "rb") as f:
        assert f.read() == b"VIDEO"


@pytest.mark.skipif(media.ffmpeg_missing(), reason="ffmpeg not installed")
async def test_extract_frame_integration(tmp_path):
    # make a 2s test video, extract a frame
    import subprocess
    src = str(tmp_path / "src.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", src],
        check=True, capture_output=True,
    )
    out = await media.extract_frame(src, str(tmp_path / "frame.png"))
    assert out.endswith("frame.png")
    import os
    assert os.path.getsize(out) > 0
```

Run: `uv run pytest tests/test_provider_media.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 2: Implement media.py**

`backend/src/doppel_api/providers/__init__.py`: empty file.

`backend/src/doppel_api/providers/media.py`:

```python
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
    ms = int(round(seconds * 1000))
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
    # seek ~1s in to skip a black/blurred intro frame, grab one high-quality frame
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
    # build filter_complex: scale avatar to base, overlay each broll within its window, burn subs
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
    Path(srt_path).write_text(build_srt(cues), encoding="utf-8")
    args = _compose_args(avatar_path, brolls, srt_path, out_path, font)
    await anyio.to_thread.run_sync(lambda: _run_ffmpeg(args))
    return out_path


async def _fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def download(url: str, out_path: str) -> str:
    data = await _fetch(url)
    Path(out_path).write_bytes(data)
    return out_path
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_provider_media.py -q`
Expected: `3 passed` (+1 ffmpeg integration passes if ffmpeg present, else skipped). Then `uv run ruff check src tests`.

- [ ] **Step 4: Commit**

```bash
git add backend/src/doppel_api/providers/__init__.py backend/src/doppel_api/providers/media.py backend/tests/test_provider_media.py
git commit -m "feat(providers): media module - ffmpeg frame/audio, srt captions, compose, download"
```

---

### Task 4: providers/script.py (Anthropic Claude)

**Files:**
- Create: `backend/src/doppel_api/providers/script.py`
- Test: `backend/tests/test_provider_script.py`

- [ ] **Step 1: Failing tests**

`backend/tests/test_provider_script.py`:

```python
import types

from doppel_api.providers import script


def _fake_response(input_dict: dict):
    block = types.SimpleNamespace(type="tool_use", input=input_dict)
    return types.SimpleNamespace(content=[block])


async def test_build_script_returns_tool_input(monkeypatch):
    captured = {}
    expected = {
        "narration": {"text": "Olá, hoje falamos de seguranca.", "tone": "confiante"},
        "scenes": [
            {"id": "s1", "start": 0.0, "end": 10.0, "type": "avatar"},
            {"id": "s2", "start": 10.0, "end": 20.0, "type": "broll",
             "prompt": "cofre digital", "motion": "camera lenta aproximando"},
            {"id": "s3", "start": 20.0, "end": 30.0, "type": "avatar"},
        ],
        "captions": {"style": "tiktok"},
    }

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _fake_response(expected)

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(script, "_client", lambda: FakeClient())
    result = await script.build_script("quero um video sobre seguranca digital")
    assert result == expected
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["tool_choice"] == {"type": "tool", "name": "emit_script"}
    assert "seguranca digital" in captured["messages"][0]["content"]
```

Run: `uv run pytest tests/test_provider_script.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 2: Implement script.py**

`backend/src/doppel_api/providers/script.py`:

```python
"""Anthropic Claude: turn a briefing transcript into the structured video script JSON."""
import anyio
import anthropic

from doppel_api.config import get_settings

_SCHEMA = {
    "type": "object",
    "properties": {
        "narration": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "tone": {"type": "string"}},
            "required": ["text"],
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "type": {"type": "string", "enum": ["avatar", "broll"]},
                    "prompt": {"type": "string"},
                    "motion": {"type": "string"},
                },
                "required": ["id", "start", "end", "type"],
            },
        },
        "captions": {
            "type": "object",
            "properties": {"style": {"type": "string"}},
        },
    },
    "required": ["narration", "scenes"],
}

_SYSTEM = (
    "Você é um roteirista de vídeos verticais curtos em PT-BR. A partir do briefing falado "
    "do usuário, gere um roteiro de ~30 segundos. A narração deve ser primeira pessoa, natural, "
    "com cerca de 75 a 85 palavras. Crie de 3 a 5 cenas cobrindo a linha do tempo de 0 a 30s sem "
    "buracos, alternando 'avatar' (o usuário falando) e 'broll'. Cada cena 'broll' precisa de um "
    "'prompt' visual concreto (para gerar uma imagem) e um 'motion' (movimento de câmera para "
    "animar). Responda SOMENTE pela ferramenta emit_script."
)


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key)


def _call(transcript: str) -> dict:
    settings = get_settings()
    resp = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": transcript}],
        tools=[{
            "name": "emit_script",
            "description": "Emite o roteiro estruturado do vídeo.",
            "input_schema": _SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "emit_script"},
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


async def build_script(transcript: str) -> dict:
    return await anyio.to_thread.run_sync(_call, transcript)
```

- [ ] **Step 3: Run tests + ruff**

Run: `uv run pytest tests/test_provider_script.py -q && uv run ruff check src tests`
Expected: `1 passed`, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add backend/src/doppel_api/providers/script.py backend/tests/test_provider_script.py
git commit -m "feat(providers): anthropic script generation via forced tool use"
```

---

### Task 5: providers/voice.py (ElevenLabs)

**Files:**
- Create: `backend/src/doppel_api/providers/voice.py`
- Test: `backend/tests/test_provider_voice.py`

- [ ] **Step 1: Failing tests**

`backend/tests/test_provider_voice.py`:

```python
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


async def test_clone_returns_voice_id(monkeypatch):
    class FakeIvc:
        def create(self, name, files):
            assert files == ["sample.wav"]
            return types.SimpleNamespace(voice_id="voice-123")

    class FakeVoices:
        ivc = FakeIvc()

    class FakeClient:
        voices = FakeVoices()

    monkeypatch.setattr(voice, "_client", lambda: FakeClient())
    assert await voice.clone("sample.wav", name="Doppel user") == "voice-123"


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
        audio_base64=base64.b64encode(b"MP3").decode(), alignment=align
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
```

Run: `uv run pytest tests/test_provider_voice.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 2: Implement voice.py**

`backend/src/doppel_api/providers/voice.py`:

```python
"""ElevenLabs: instant voice clone, TTS (+ timestamps), and Scribe STT."""
import base64

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
        voice = _client().voices.ivc.create(name=name, files=[sample_path])
        return voice.voice_id

    return await anyio.to_thread.run_sync(_do)


async def tts(voice_id: str, text: str) -> bytes:
    def _do() -> bytes:
        stream = _client().text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id=get_settings().elevenlabs_model,
            output_format="mp3_44100_128",
        )
        return b"".join(stream)

    return await anyio.to_thread.run_sync(_do)


async def tts_with_timestamps(voice_id: str, text: str) -> tuple[bytes, list[CaptionCue]]:
    def _do() -> tuple[bytes, list[CaptionCue]]:
        resp = _client().text_to_speech.convert_with_timestamps(
            voice_id=voice_id, text=text, model_id=get_settings().elevenlabs_model
        )
        audio = base64.b64decode(resp.audio_base64)
        a = resp.alignment
        cues = group_alignment_to_words(
            a.characters, a.character_start_times_seconds, a.character_end_times_seconds
        )
        return audio, cues

    return await anyio.to_thread.run_sync(_do)


async def stt(audio_path: str) -> str:
    def _do() -> str:
        with open(audio_path, "rb") as f:
            result = _client().speech_to_text.convert(file=f, model_id="scribe_v1")
        return result.text

    return await anyio.to_thread.run_sync(_do)
```

- [ ] **Step 3: Run tests + ruff**

Run: `uv run pytest tests/test_provider_voice.py -q && uv run ruff check src tests`
Expected: `5 passed`, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add backend/src/doppel_api/providers/voice.py backend/tests/test_provider_voice.py
git commit -m "feat(providers): elevenlabs voice clone, tts, timestamps, scribe stt"
```

---

### Task 6: providers/video.py (fal: Fabric, FLUX, Kling)

**Files:**
- Create: `backend/src/doppel_api/providers/video.py`
- Test: `backend/tests/test_provider_video.py`

- [ ] **Step 1: Failing tests**

`backend/tests/test_provider_video.py`:

```python
from doppel_api.providers import video


async def test_upload_returns_url(monkeypatch):
    async def fake_upload(path):
        assert path == "f.png"
        return "https://fal.media/f.png"

    monkeypatch.setattr(video.fal_client, "upload_file_async", fake_upload)
    assert await video.upload("f.png") == "https://fal.media/f.png"


async def test_talking_calls_fabric_and_parses_url(monkeypatch):
    seen = {}

    async def fake_subscribe(model, arguments):
        seen["model"] = model
        seen["args"] = arguments
        return {"video": {"url": "https://fal.media/talk.mp4"}}

    monkeypatch.setattr(video.fal_client, "subscribe_async", fake_subscribe)
    url = await video.talking("img-url", "aud-url", resolution="480p")
    assert url == "https://fal.media/talk.mp4"
    assert seen["model"] == "veed/fabric-1.0"
    assert seen["args"] == {"image_url": "img-url", "audio_url": "aud-url", "resolution": "480p"}


async def test_image_calls_flux_and_parses_url(monkeypatch):
    async def fake_subscribe(model, arguments):
        assert model == "fal-ai/flux/schnell"
        assert arguments["prompt"] == "a vault"
        assert arguments["num_images"] == 1
        return {"images": [{"url": "https://fal.media/i.jpg"}]}

    monkeypatch.setattr(video.fal_client, "subscribe_async", fake_subscribe)
    assert await video.image("a vault") == "https://fal.media/i.jpg"


async def test_broll_calls_kling_with_string_duration(monkeypatch):
    seen = {}

    async def fake_subscribe(model, arguments):
        seen.update(arguments)
        seen["model"] = model
        return {"video": {"url": "https://fal.media/b.mp4"}}

    monkeypatch.setattr(video.fal_client, "subscribe_async", fake_subscribe)
    url = await video.broll("i.jpg", "camera zooms in")
    assert url == "https://fal.media/b.mp4"
    assert seen["model"] == "fal-ai/kling-video/v2.1/standard/image-to-video"
    assert seen["image_url"] == "i.jpg"
    assert seen["duration"] == "5"  # string, not int
```

Run: `uv run pytest tests/test_provider_video.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 2: Implement video.py**

`backend/src/doppel_api/providers/video.py`:

```python
"""fal.ai video generation: Fabric talking avatar, FLUX text-to-image, Kling image-to-video."""
import fal_client

from doppel_api.config import get_settings


async def upload(path: str) -> str:
    return await fal_client.upload_file_async(path)


async def talking(image_url: str, audio_url: str, resolution: str = "480p") -> str:
    result = await fal_client.subscribe_async(
        get_settings().fal_lipsync_model,
        arguments={"image_url": image_url, "audio_url": audio_url, "resolution": resolution},
    )
    return result["video"]["url"]


async def image(prompt: str, image_size: str = "portrait_16_9") -> str:
    result = await fal_client.subscribe_async(
        get_settings().fal_t2i_model,
        arguments={"prompt": prompt, "image_size": image_size, "num_images": 1},
    )
    return result["images"][0]["url"]


async def broll(image_url: str, prompt: str, duration: str = "5") -> str:
    result = await fal_client.subscribe_async(
        get_settings().fal_broll_model,
        arguments={"prompt": prompt, "image_url": image_url, "duration": duration},
    )
    return result["video"]["url"]
```

- [ ] **Step 3: Run tests + ruff**

Run: `uv run pytest tests/test_provider_video.py -q && uv run ruff check src tests`
Expected: `4 passed`, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add backend/src/doppel_api/providers/video.py backend/tests/test_provider_video.py
git commit -m "feat(providers): fal fabric, flux and kling video drivers"
```

---

### Task 7: Rewrite the worker handlers (both) + tests

This replaces `make_stub_video`/`_render_and_upload` and both handlers with real provider orchestration, in one atomic change (so there is no broken intermediate state). `WorkerContext`, `HANDLERS`, `process_one`, and `main` are unchanged except imports.

**Files:**
- Modify: `backend/workers/worker.py` (full rewrite below)
- Modify: `backend/tests/test_worker.py` (full rewrite below)

- [ ] **Step 1: Rewrite worker.py**

Replace the ENTIRE contents of `backend/workers/worker.py` with:

```python
"""Doppel generation worker: consumes jobs and drives the managed providers."""
import asyncio
import os
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.constants import FEEDBACK_LINE, HELLO_LINE
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.events import publish  # tests rebind providers, not this
from doppel_api.models import Avatar, Job, Video
from doppel_api.providers import media, script, video, voice
from doppel_api.queue import ack, ensure_groups, read_next
from doppel_api.storage import S3Storage, Storage


@dataclass
class WorkerContext:
    session_factory: async_sessionmaker[AsyncSession]
    storage: Storage
    redis: object
    consumer: str


async def _store_fal_video(ctx: "WorkerContext", url: str, key: str, tmp: Path, name: str) -> None:
    local = str(tmp / name)
    await media.download(url, local)
    await ctx.storage.put(key, Path(local).read_bytes(), "video/mp4")


async def handle_avatar_prep(ctx: "WorkerContext", payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        source_key = avatar.assets["source"]

    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    face_key = f"avatars/{avatar_id}/face.png"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        src = tmp / "source"
        src.write_bytes(await ctx.storage.get(source_key))

        face = await media.extract_frame(str(src), str(tmp / "face.png"))
        ref_audio = await media.extract_audio(str(src), str(tmp / "ref.wav"))
        await ctx.storage.put(face_key, Path(face).read_bytes(), "image/png")

        voice_id = await voice.clone(ref_audio, name=f"doppel-{avatar_id[:8]}")
        face_url = await video.upload(face)

        for line, key, name in (
            (HELLO_LINE, hello_key, "hello"),
            (FEEDBACK_LINE, feedback_key, "feedback"),
        ):
            audio_bytes = await voice.tts(voice_id, line)
            audio_path = tmp / f"{name}.mp3"
            audio_path.write_bytes(audio_bytes)
            audio_url = await video.upload(str(audio_path))
            talk_url = await video.talking(face_url, audio_url)
            await _store_fal_video(ctx, talk_url, key, tmp, f"{name}.mp4")

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {
            **avatar.assets,
            "face_image": face_key,
            "voice_id": voice_id,
            "hello": hello_key,
            "feedback": feedback_key,
        }
        await s.commit()

    await publish(ctx.redis, avatar_id, "hello_ready", {
        "hello_url": await ctx.storage.presign_get(hello_key),
        "feedback_url": await ctx.storage.presign_get(feedback_key),
    })


async def _gen_broll(ctx, scene, idx, total, tmp, video_id, sem) -> media.BrollClip | None:
    async with sem:
        try:
            img_url = await video.image(scene.get("prompt", ""))
            clip_url = await video.broll(img_url, scene.get("motion") or scene.get("prompt", ""))
            path = str(tmp / f"broll{idx}.mp4")
            await media.download(clip_url, path)
            await publish(ctx.redis, video_id, "progress", {"step": f"component_{idx + 2}_of_{total}"})
            return media.BrollClip(path=path, start=float(scene["start"]), end=float(scene["end"]))
        except Exception as exc:  # graceful degrade: drop this scene, keep the video
            print(f"broll scene {scene.get('id')} failed, dropping: {exc!r}")
            return None


async def handle_fast_generate(ctx: "WorkerContext", payload: dict) -> None:
    video_id = payload["video_id"]
    settings = get_settings()

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        briefing_key = v.assets["briefing"]
        avatar = (await s.execute(select(Avatar).where(Avatar.id == v.avatar_id))).scalar_one()
        voice_id = avatar.assets["voice_id"]
        face_key = avatar.assets["face_image"]

    await publish(ctx.redis, video_id, "progress", {"step": "scripting"})
    fast_key = f"videos/{video_id}/fast.mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        brief = tmp / "briefing"
        brief.write_bytes(await ctx.storage.get(briefing_key))
        transcript = await voice.stt(str(brief))
        script_json = await script.build_script(transcript)

        narration_audio, cues = await voice.tts_with_timestamps(
            voice_id, script_json["narration"]["text"]
        )
        (tmp / "narration.mp3").write_bytes(narration_audio)

        face_local = tmp / "face.png"
        face_local.write_bytes(await ctx.storage.get(face_key))
        face_url = await video.upload(str(face_local))
        narration_url = await video.upload(str(tmp / "narration.mp3"))

        broll_scenes = [sc for sc in script_json["scenes"] if sc["type"] == "broll"]
        total = 1 + len(broll_scenes)
        sem = asyncio.Semaphore(settings.pipeline_concurrency)

        async def gen_avatar() -> str:
            await publish(ctx.redis, video_id, "progress", {"step": f"component_1_of_{total}"})
            url = await video.talking(face_url, narration_url)
            path = str(tmp / "avatar.mp4")
            await media.download(url, path)
            return path

        results = await asyncio.gather(
            gen_avatar(),
            *[_gen_broll(ctx, sc, i, total, tmp, video_id, sem)
              for i, sc in enumerate(broll_scenes)],
        )
        avatar_path = results[0]
        brolls = [b for b in results[1:] if b is not None]

        out = str(tmp / "fast.mp4")
        await media.compose_timeline(avatar_path, brolls, cues, out, settings.caption_font)
        await ctx.storage.put(fast_key, Path(out).read_bytes(), "video/mp4")

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        v.status_fast = "ready"
        v.assets = {**v.assets, "fast": fast_key}
        v.script = script_json
        await s.commit()

    await publish(ctx.redis, video_id, "fast_ready", {
        "fast_url": await ctx.storage.presign_get(fast_key),
    })


HANDLERS = {"avatar_prep": handle_avatar_prep, "fast_generate": handle_fast_generate}


async def process_one(ctx: WorkerContext) -> bool:
    msg = await read_next(ctx.redis, consumer=ctx.consumer)
    if msg is None:
        return False
    async with ctx.session_factory() as s:
        job = (
            await s.execute(select(Job).where(Job.id == msg["job_id"]))
        ).scalar_one_or_none()
        if job is None:
            print(f"orphan stream entry, skipping job_id={msg['job_id']}")
            await ack(ctx.redis, msg["lane"], msg["msg_id"])
            return True
        job.status = "running"
        await s.commit()
        kind, payload = job.kind, dict(job.payload)
    try:
        await HANDLERS[kind](ctx, payload)
        status = "done"
    except Exception as exc:  # worker must survive any job failure
        print(f"job {msg['job_id']} ({kind}) failed: {exc!r}")
        status = "failed"
        entity_id = payload.get("avatar_id") or payload.get("video_id") or ""
        async with ctx.session_factory() as s:
            if "avatar_id" in payload:
                avatar = (
                    await s.execute(select(Avatar).where(Avatar.id == payload["avatar_id"]))
                ).scalar_one_or_none()
                if avatar is not None:
                    avatar.status = "failed"
            elif "video_id" in payload:
                vid = (
                    await s.execute(select(Video).where(Video.id == payload["video_id"]))
                ).scalar_one_or_none()
                if vid is not None:
                    vid.status_fast = "failed"
            await s.commit()
        if entity_id:
            await publish(ctx.redis, entity_id, "failed", {"kind": kind})
    async with ctx.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.id == msg["job_id"]))).scalar_one()
        job.status = status
        await s.commit()
    await ack(ctx.redis, msg["lane"], msg["msg_id"])
    return True


async def main() -> None:
    settings = get_settings()
    engine = make_engine()
    await init_db(engine)
    storage = S3Storage(settings)
    await storage.ensure_bucket()
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await ensure_groups(redis)
    ctx = WorkerContext(
        session_factory=make_session_factory(engine), storage=storage,
        redis=redis, consumer=f"worker-{socket.gethostname()}-{os.getpid()}",
    )
    print(f"worker started as {ctx.consumer}")
    while True:
        try:
            worked = await process_one(ctx)
        except Exception as exc:
            print(f"worker loop error: {exc!r}")
            await asyncio.sleep(1.0)
            continue
        if not worked:
            await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Rewrite test_worker.py**

Replace the ENTIRE contents of `backend/tests/test_worker.py` with:

```python
import fakeredis.aioredis
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api.constants import HELLO_LINE
from doppel_api.db import init_db, make_session_factory
from doppel_api.models import Avatar, Device, Job, Video
from doppel_api.providers import media
from doppel_api.providers.media import CaptionCue
from doppel_api.queue import ensure_groups, enqueue
from doppel_api.storage import MemoryStorage
from workers import worker
from workers.worker import WorkerContext, process_one


@pytest.fixture
async def ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_groups(redis)
    yield WorkerContext(
        session_factory=make_session_factory(engine),
        storage=MemoryStorage(),
        redis=redis,
        consumer="test-worker",
    )
    await engine.dispose()


def _patch_providers(monkeypatch, *, broll_ok=True, fail=None):
    """Stub every provider call with in-memory fakes. `fail` = name of a call to raise in."""
    async def maybe(name):
        if fail == name:
            raise RuntimeError(f"{name} boom")

    async def fake_extract_frame(src, out):
        await maybe("extract_frame")
        from pathlib import Path
        Path(out).write_bytes(b"IMG")
        return out

    async def fake_extract_audio(src, out):
        from pathlib import Path
        Path(out).write_bytes(b"WAV")
        return out

    async def fake_download(url, out):
        from pathlib import Path
        Path(out).write_bytes(b"MP4")
        return out

    async def fake_compose(avatar_path, brolls, cues, out, font):
        from pathlib import Path
        Path(out).write_bytes(b"FINAL")
        return out

    monkeypatch.setattr(media, "extract_frame", fake_extract_frame)
    monkeypatch.setattr(media, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(media, "download", fake_download)
    monkeypatch.setattr(media, "compose_timeline", fake_compose)

    async def fake_clone(sample, name):
        await maybe("clone")
        return "voice-xyz"

    async def fake_tts(voice_id, text):
        return b"AUDIO"

    async def fake_tts_ts(voice_id, text):
        return b"AUDIO", [CaptionCue(text="oi", start=0.0, end=0.5)]

    async def fake_stt(path):
        return "briefing transcrito"

    monkeypatch.setattr(worker.voice, "clone", fake_clone)
    monkeypatch.setattr(worker.voice, "tts", fake_tts)
    monkeypatch.setattr(worker.voice, "tts_with_timestamps", fake_tts_ts)
    monkeypatch.setattr(worker.voice, "stt", fake_stt)

    async def fake_build_script(transcript):
        return {
            "narration": {"text": "Olá, sou eu aprimorado.", "tone": "confiante"},
            "scenes": [
                {"id": "s1", "start": 0.0, "end": 10.0, "type": "avatar"},
                {"id": "s2", "start": 10.0, "end": 20.0, "type": "broll",
                 "prompt": "cofre", "motion": "zoom"},
                {"id": "s3", "start": 20.0, "end": 30.0, "type": "avatar"},
            ],
            "captions": {"style": "tiktok"},
        }

    monkeypatch.setattr(worker.script, "build_script", fake_build_script)

    async def fake_upload(path):
        return f"https://fal.media/{path.split('/')[-1]}"

    async def fake_talking(image_url, audio_url, resolution="480p"):
        return "https://fal.media/talk.mp4"

    async def fake_image(prompt, image_size="portrait_16_9"):
        if not broll_ok:
            raise RuntimeError("flux boom")
        return "https://fal.media/i.jpg"

    async def fake_broll(image_url, prompt, duration="5"):
        return "https://fal.media/b.mp4"

    monkeypatch.setattr(worker.video, "upload", fake_upload)
    monkeypatch.setattr(worker.video, "talking", fake_talking)
    monkeypatch.setattr(worker.video, "image", fake_image)
    monkeypatch.setattr(worker.video, "broll", fake_broll)


async def _seed_avatar(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="t" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="processing", assets={"source": "raw/x/source.webm"})
        s.add(a)
        await s.flush()
        avatar_id = a.id
        await ctx.storage.put("raw/x/source.webm", b"SRC", "video/webm")
        await enqueue(ctx.redis, s, kind="avatar_prep", lane="interactive",
                      payload={"avatar_id": avatar_id})
        return avatar_id


async def _seed_ready_avatar_and_video(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="u" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="ready",
                   assets={"face_image": "avatars/a/face.png", "voice_id": "voice-xyz"})
        s.add(a)
        await s.flush()
        v = Video(device_id=d.id, avatar_id=a.id, assets={"briefing": "videos/v/briefing.webm"})
        s.add(v)
        await s.flush()
        video_id = v.id
        await ctx.storage.put("avatars/a/face.png", b"IMG", "image/png")
        await ctx.storage.put("videos/v/briefing.webm", b"AUD", "audio/webm")
        await enqueue(ctx.redis, s, kind="fast_generate", lane="interactive",
                      payload={"video_id": video_id})
        return video_id


async def test_process_one_returns_false_on_empty_queue(ctx):
    assert await process_one(ctx) is False


async def test_orphan_job_id_is_skipped_not_fatal(ctx):
    await ctx.redis.xadd("jobs:interactive", {"job_id": "nope"})
    assert await process_one(ctx) is True
    assert await process_one(ctx) is False


async def test_avatar_prep_produces_hello_and_feedback(ctx, monkeypatch):
    avatar_id = await _seed_avatar(ctx)
    events = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    _patch_providers(monkeypatch)
    monkeypatch.setattr(worker, "publish", capture)
    assert HELLO_LINE  # the worker speaks the fixed PT-BR line
    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
    assert avatar.status == "ready"
    assert avatar.assets["voice_id"] == "voice-xyz"
    assert avatar.assets["face_image"] == f"avatars/{avatar_id}/face.png"
    assert avatar.assets["hello"] == f"avatars/{avatar_id}/hello.mp4"
    assert await ctx.storage.get(avatar.assets["hello"]) == b"MP4"
    assert events[-1][0] == "hello_ready"
    assert "hello_url" in events[-1][1] and "feedback_url" in events[-1][1]


async def test_fast_generate_composes_video(ctx, monkeypatch):
    video_id = await _seed_ready_avatar_and_video(ctx)
    events = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    _patch_providers(monkeypatch)
    monkeypatch.setattr(worker, "publish", capture)
    assert await process_one(ctx) is True

    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video))).scalar_one()
    assert v.status_fast == "ready"
    assert v.assets["fast"] == f"videos/{video_id}/fast.mp4"
    assert await ctx.storage.get(v.assets["fast"]) == b"FINAL"
    assert v.script["narration"]["text"]
    assert events[-1][0] == "fast_ready"
    assert "fast_url" in events[-1][1]


async def test_fast_generate_degrades_when_broll_fails(ctx, monkeypatch):
    await _seed_ready_avatar_and_video(ctx)
    _patch_providers(monkeypatch, broll_ok=False)
    monkeypatch.setattr(worker, "publish", lambda *a, **k: _noop())
    assert await process_one(ctx) is True
    async with ctx.session_factory() as s:
        v = (await s.execute(select(Video))).scalar_one()
    assert v.status_fast == "ready"  # broll failure dropped the scene, video still made


async def test_avatar_prep_failure_marks_failed(ctx, monkeypatch):
    await _seed_avatar(ctx)
    events = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    _patch_providers(monkeypatch, fail="clone")
    monkeypatch.setattr(worker, "publish", capture)
    assert await process_one(ctx) is True
    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
        job = (await s.execute(select(Job).where(Job.kind == "avatar_prep"))).scalar_one()
    assert avatar.status == "failed"
    assert job.status == "failed"
    assert events[-1] == ("failed", {"kind": "avatar_prep"})


async def _noop():
    return None
```

- [ ] **Step 3: Run the full suite + ruff**

Run: `uv run pytest -q && uv run ruff check src tests workers`
Expected: all green. The worker handler tests, provider tests, and all M0 backend tests pass with zero network calls.

- [ ] **Step 4: Commit**

```bash
git add backend/workers/worker.py backend/tests/test_worker.py
git commit -m "feat(worker): real provider-driven avatar_prep and fast_generate pipelines"
```

---

### Task 8: Opt-in live smoke script + final verification

**Files:**
- Create: `backend/scripts/live_smoke.py`

This is a manual, paid, end-to-end check gated behind `DOPPEL_LIVE_SMOKE=1` so it never runs in CI. It exercises the real providers against a tiny synthetic recording.

- [ ] **Step 1: Write the script**

`backend/scripts/live_smoke.py`:

```python
"""Opt-in live end-to-end smoke against the REAL providers (costs money).

Run with real keys in the environment:
    DOPPEL_LIVE_SMOKE=1 uv run python scripts/live_smoke.py

It synthesizes a 3s talking-ish clip with ffmpeg, runs voice clone + TTS + Fabric
for the avatar, then a one-scene script + b-roll + compose. Prints output paths.
Refuses to run unless DOPPEL_LIVE_SMOKE=1 to avoid accidental spend.
"""
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from doppel_api.providers import media, script, video, voice


def _make_sample(path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=540x960:rate=30:duration=3",
         "-f", "lavfi", "-i", "sine=frequency=180:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path],
        check=True, capture_output=True,
    )


async def run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        sample = str(tmp / "sample.mp4")
        _make_sample(sample)

        face = await media.extract_frame(sample, str(tmp / "face.png"))
        ref = await media.extract_audio(sample, str(tmp / "ref.wav"))
        print("cloning voice...")
        voice_id = await voice.clone(ref, name="live-smoke")
        print("voice:", voice_id)

        hello_bytes = await voice.tts(voice_id, "Oi! Eu sou você aprimorado!")
        (tmp / "hello.mp3").write_bytes(hello_bytes)
        face_url = await video.upload(face)
        hello_audio_url = await video.upload(str(tmp / "hello.mp3"))
        print("generating talking avatar (Fabric)...")
        talk_url = await video.talking(face_url, hello_audio_url)
        await media.download(talk_url, str(tmp / "hello.mp4"))
        print("hello.mp4 ->", tmp / "hello.mp4", os.path.getsize(tmp / "hello.mp4"), "bytes")

        print("building script...")
        sjson = await script.build_script("Quero um vídeo curto sobre proteger suas senhas.")
        print("script scenes:", [(s["type"], s["start"], s["end"]) for s in sjson["scenes"]])

        narration, cues = await voice.tts_with_timestamps(voice_id, sjson["narration"]["text"])
        (tmp / "narration.mp3").write_bytes(narration)
        narration_url = await video.upload(str(tmp / "narration.mp3"))
        avatar_url = await video.talking(face_url, narration_url)
        await media.download(avatar_url, str(tmp / "avatar.mp4"))

        brolls = []
        for i, sc in enumerate(s for s in sjson["scenes"] if s["type"] == "broll"):
            img = await video.image(sc.get("prompt", "abstract background"))
            clip = await video.broll(img, sc.get("motion") or sc.get("prompt", ""))
            p = str(tmp / f"broll{i}.mp4")
            await media.download(clip, p)
            brolls.append(media.BrollClip(path=p, start=float(sc["start"]), end=float(sc["end"])))

        out = str(Path.cwd() / "live_smoke_out.mp4")
        await media.compose_timeline(str(tmp / "avatar.mp4"), brolls, cues, out, "DejaVu Sans")
        print("FINAL ->", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    if os.environ.get("DOPPEL_LIVE_SMOKE") != "1":
        print("refusing to run: set DOPPEL_LIVE_SMOKE=1 (this spends real money)")
        sys.exit(1)
    asyncio.run(run())
```

- [ ] **Step 2: Verify it refuses to run without the flag**

Run: `cd /Users/savio/Project/backend && uv run python scripts/live_smoke.py`
Expected: prints "refusing to run..." and exits non-zero. (Do NOT run with the flag here - that spends money; the user runs it manually when ready.)

- [ ] **Step 3: Final full suite + ruff**

Run: `uv run pytest -q && uv run ruff check src tests workers`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/live_smoke.py
git commit -m "feat(smoke): opt-in live end-to-end smoke against real providers"
```

---

## Self-review (run by the plan author)

**Spec coverage:**
- Provider stack (spec section 3): script.py (Anthropic), voice.py (ElevenLabs clone/tts/timestamps/stt), video.py (fal Fabric/FLUX/Kling), media.py (ffmpeg/captions/compose) - Tasks 3-6. Covered.
- avatar_prep pipeline (spec 5): Task 7 handle_avatar_prep - frame+audio extract, clone, hello+feedback TTS, Fabric, store, hello_ready with both urls, voice_id+face in assets. Covered.
- fast_generate pipeline (spec 6): Task 7 handle_fast_generate - Scribe STT, Claude script, narration TTS-with-timestamps, parallel avatar+b-roll (FLUX->Kling) under PIPELINE_CONCURRENCY, compose with burned captions, fast_ready. Covered.
- Config additions + env_file + .env.example (spec 7): Task 1. Covered.
- Error handling/degrade (spec 8): broll failure drops scene (Task 7 `_gen_broll`); critical failure marks entity failed via process_one (unchanged). Covered. NOTE: per-call fal timeout/retry from spec 8 is NOT separately implemented - fal_client has its own polling/timeout; explicit retry wrapper is deferred. Flagged below.
- Testing (spec 9): driver unit tests with injected fakes (Tasks 3-6); handler tests with providers monkeypatched (Task 7); media integration skip-if-no-ffmpeg; live smoke opt-in (Task 8). Covered.
- No Supabase / no schema migration / no music / frontend on host: respected throughout.

**Gaps / deliberate deferrals (acceptable for this iteration, called out):**
1. Explicit per-call fal timeout+retry wrapper (spec 8) is not added; relying on fal_client defaults. If flakiness appears, add a retry decorator in video.py. Low risk for first cut.
2. compose_timeline's ffmpeg filtergraph (overlay windows + burned subtitles) is validated by the pure `_compose_args` test and the live smoke, not by an automated render-and-inspect test (ffmpeg may be absent in CI). The subtitles path escaping is minimal (`:` escaped); the live smoke is where real composition is proven.
3. Budget kill-switch is documentation-only (spec), not code.

**Placeholder scan:** No TBD/TODO; every step has complete code.

**Type consistency:** `CaptionCue`/`BrollClip` defined in media.py, imported by voice.py and worker.py and tests. Provider function names (`clone`, `tts`, `tts_with_timestamps`, `stt`, `build_script`, `upload`, `talking`, `image`, `broll`, `extract_frame`, `extract_audio`, `download`, `compose_timeline`) are consistent across drivers, the worker, and tests. Event names (`hello_ready`, `fast_ready`, `progress`, `failed`) match the M0 SSE routes. assets keys (`source`, `face_image`, `voice_id`, `hello`, `feedback`, `briefing`, `fast`) consistent between handlers and tests.



