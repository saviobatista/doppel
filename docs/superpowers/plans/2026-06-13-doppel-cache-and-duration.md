# Doppel Artifact Cache + Configurable Duration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a content-addressed local cache so paid provider calls (ElevenLabs, Claude, fal) are reused across runs, and a `VIDEO_TARGET_SECONDS` knob so validation runs are short and cheap.

**Architecture:** A new `cache.py` (pure, content-addressed over a host bind-mounted dir) is wired into the worker handlers around each expensive step; providers stay pure. `VIDEO_TARGET_SECONDS` flows into `script.build_script` and into the `script` cache key. No pipeline logic, route, SSE, or frontend change.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, fal-client/elevenlabs/anthropic, ffmpeg, pytest.

**Spec:** `docs/superpowers/specs/2026-06-13-doppel-cache-and-duration-design.md`

**Commit rule:** plain ASCII messages, no emojis, and **NO `Co-Authored-By` trailer** (supreme rule in the user's global CLAUDE.md). Branch: `feature/m0-walking-skeleton`. Run python from `/Users/savio/Project/backend`.

**Key facts about the existing code (do not change these contracts):**
- `cache.value`/`cache.blob` keys are hashes of LOGICAL inputs; composition is automatic (cached TTS bytes -> same Fabric key).
- The worker (`backend/workers/worker.py`) has `handle_avatar_prep` and `handle_fast_generate`; both use a `tempfile.TemporaryDirectory`, call `media`/`voice`/`script`/`video`, upload results to `ctx.storage`, and `publish` events. `_gen_broll` already drops a failed scene gracefully. `process_one` marks the entity `failed` on an uncaught exception.
- Providers: `voice.clone(sample_path, name)->str`, `voice.tts(voice_id, text)->bytes`, `voice.tts_with_timestamps(voice_id, text)->(bytes, list[CaptionCue])`, `voice.stt(audio_path)->str`; `script.build_script(transcript)->dict`; `video.upload(path)->str`, `video.talking(image_url, audio_url, resolution="480p")->str`, `video.image(prompt, image_size="portrait_16_9")->str`, `video.broll(image_url, prompt, duration="5")->str`; `media.download(url, out)->str`, `media.CaptionCue(text,start,end)`, `media.BrollClip(path,start,end)`, `media.compose_timeline(...)`.
- `Settings` (env_prefix `DOPPEL_`) reads raw provider env names via `validation_alias=AliasChoices(...)`; `elevenlabs_model` is a field.

---

## File Structure

```
backend/
  src/doppel_api/
    config.py        # + cache_dir, video_target_seconds (raw env via AliasChoices)
    cache.py         # NEW: content-addressed cache (blob / value / blob_with_meta / put_blob)
    providers/
      media.py       # + public fetch(url) -> bytes (download already exists; reuse _fetch)
      script.py      # build_script(transcript, target_seconds) - prompt parameterized
  workers/
    worker.py        # handlers route expensive steps through cache; pass target_seconds
  tests/
    test_cache.py            # NEW
    test_config_providers.py # + cache_dir / video_target_seconds assertions
    test_provider_media.py   # + fetch test
    test_provider_script.py  # build_script target_seconds
    test_worker.py           # + cache reuse assertions (2nd run = no provider call)
docker-compose.yml   # ./cache:/app/cache volume on api + stub-worker; CACHE_DIR env
.env.example         # CACHE_DIR, VIDEO_TARGET_SECONDS
.gitignore           # cache/
```

---

### Task 1: Config fields + compose volume + gitignore

**Files:**
- Modify: `backend/src/doppel_api/config.py`
- Modify: `backend/tests/test_config_providers.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Add failing assertions** to `backend/tests/test_config_providers.py`. Append to `test_provider_settings_defaults`:

```python
    assert s.cache_dir == "cache"
    assert s.video_target_seconds == 10
```

And add a new test:

```python
def test_cache_and_duration_env(monkeypatch):
    monkeypatch.setenv("CACHE_DIR", "/app/cache")
    monkeypatch.setenv("VIDEO_TARGET_SECONDS", "30")
    s = Settings()
    assert s.cache_dir == "/app/cache"
    assert s.video_target_seconds == 30
```

Run: `uv run pytest tests/test_config_providers.py -q` -> FAIL (fields missing).

- [ ] **Step 2: Add the fields** to `Settings` in `backend/src/doppel_api/config.py`, right after `pipeline_concurrency`:

```python
    cache_dir: str = Field(default="cache", validation_alias=AliasChoices("CACHE_DIR"))
    video_target_seconds: int = Field(
        default=10, validation_alias=AliasChoices("VIDEO_TARGET_SECONDS")
    )
```

Run: `uv run pytest tests/test_config_providers.py -q` -> PASS.

- [ ] **Step 3: Compose volume + env.** In `docker-compose.yml`, add `CACHE_DIR: /app/cache` to the `&doppel_env` anchor (after `PYTHONUNBUFFERED`), and add a `volumes:` mapping to BOTH `api` and `stub-worker` services:

```yaml
    volumes:
      - ./cache:/app/cache
```

(For `api`, add the `volumes:` block alongside its existing keys; for `stub-worker` likewise. Keep everything else unchanged.)

- [ ] **Step 4: .env.example + .gitignore.** Append to `.env.example` (in the providers block):

```bash
CACHE_DIR=/app/cache
VIDEO_TARGET_SECONDS=10
```

Add to `.gitignore` (under the media section):

```
# Provider artifact cache (generated media, never commit)
cache/
```

- [ ] **Step 5: Full suite + commit.**

Run: `uv run pytest -q && uv run ruff check src tests` -> all green.

```bash
cd /Users/savio/Project
git add backend/src/doppel_api/config.py backend/tests/test_config_providers.py docker-compose.yml .env.example .gitignore
git commit -m "feat(cache): config fields, compose cache volume, gitignore"
```

---

### Task 2: cache.py module

**Files:**
- Create: `backend/src/doppel_api/cache.py`
- Test: `backend/tests/test_cache.py`

- [ ] **Step 1: Failing tests** - `backend/tests/test_cache.py`:

```python
import json

import pytest

from doppel_api import cache, config


@pytest.fixture(autouse=True)
def _cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    # get_settings() is lru_cached; patch the cached instance's attribute
    yield


async def test_blob_miss_then_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    calls = []

    async def producer():
        calls.append(1)
        return b"DATA"

    p1 = await cache.blob("ns", ["a", "b"], "bin", producer)
    p2 = await cache.blob("ns", ["a", "b"], "bin", producer)
    assert p1 == p2
    assert open(p1, "rb").read() == b"DATA"
    assert len(calls) == 1  # second call was a cache hit


async def test_blob_key_depends_on_parts(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)

    async def make(tag):
        return tag.encode()

    pa = await cache.blob("ns", ["x"], "bin", lambda: make("A"))
    pb = await cache.blob("ns", ["y"], "bin", lambda: make("B"))
    assert pa != pb
    assert open(pa, "rb").read() == b"A"
    assert open(pb, "rb").read() == b"B"


async def test_value_roundtrip_and_hit(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    calls = []

    async def producer():
        calls.append(1)
        return {"voice_id": "v1"}

    v1 = await cache.value("clone", [b"audio"], producer)
    v2 = await cache.value("clone", [b"audio"], producer)
    assert v1 == v2 == {"voice_id": "v1"}
    assert len(calls) == 1


async def test_value_corrupt_reproduces(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    # prime, then corrupt the cache file
    await cache.value("ns", ["k"], lambda: _ret({"a": 1}))
    import pathlib
    f = next(pathlib.Path(tmp_path, "ns").glob("*.json"))
    f.write_text("not json{")
    out = await cache.value("ns", ["k"], lambda: _ret({"a": 2}))
    assert out == {"a": 2}


async def test_blob_with_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    calls = []

    async def producer():
        calls.append(1)
        return b"AUDIO", [{"text": "oi", "start": 0.0, "end": 0.5}]

    p1, m1 = await cache.blob_with_meta("tts_ts", ["v", "t"], "mp3", producer)
    p2, m2 = await cache.blob_with_meta("tts_ts", ["v", "t"], "mp3", producer)
    assert open(p1, "rb").read() == b"AUDIO"
    assert m1 == m2 == [{"text": "oi", "start": 0.0, "end": 0.5}]
    assert len(calls) == 1


def test_put_blob_writes_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path), raising=False)
    p = cache.put_blob("source", ["av1"], "webm", b"REC")
    assert open(p, "rb").read() == b"REC"
    p2 = cache.put_blob("source", ["av1"], "webm", b"DIFFERENT")
    assert p2 == p
    assert open(p2, "rb").read() == b"REC"  # not overwritten on hit


async def _ret(obj):
    return obj
```

Run: `uv run pytest tests/test_cache.py -q` -> FAIL (ImportError).

- [ ] **Step 2: Implement** `backend/src/doppel_api/cache.py`:

```python
"""Content-addressed local cache for paid provider artifacts.

Keyed by a sha256 of each call's logical inputs and stored under CACHE_DIR on a
host bind-mounted directory, so re-runs reuse already-generated artifacts (and
the files are inspectable locally). A cache-write failure never fails the job -
the artifact was still produced this run.
"""
import hashlib
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from doppel_api.config import get_settings


def _key(parts: list[str | bytes]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else str(part).encode("utf-8"))
        h.update(b"\x00")  # separator so ["a","b"] != ["ab"]
    return h.hexdigest()


def _path(namespace: str, key: str, ext: str) -> Path:
    return Path(get_settings().cache_dir) / namespace / f"{key}.{ext}"


def _safe_write(path: Path, data: bytes, ext: str) -> str:
    """Atomically write data to the cache; on failure fall back to a temp file.

    Returns the path that actually holds the bytes (cache path or fallback), so
    the current run always has a usable file.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return str(path)
    except OSError as exc:
        print(f"cache write failed for {path}: {exc!r}")
        fd, fallback = tempfile.mkstemp(suffix=f".{ext}")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return fallback


async def blob(
    namespace: str, parts: list, ext: str, producer: Callable[[], Awaitable[bytes]]
) -> str:
    path = _path(namespace, _key(parts), ext)
    if path.exists():
        return str(path)
    data = await producer()
    return _safe_write(path, data, ext)


async def value(namespace: str, parts: list, producer: Callable[[], Awaitable[Any]]) -> Any:
    path = _path(namespace, _key(parts), "json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass  # corrupt/unreadable -> re-produce
    obj = await producer()
    _safe_write(path, json.dumps(obj).encode("utf-8"), "json")
    return obj


async def blob_with_meta(
    namespace: str, parts: list, ext: str,
    producer: Callable[[], Awaitable[tuple[bytes, Any]]],
) -> tuple[str, Any]:
    key = _key(parts)
    blob_path = _path(namespace, key, ext)
    meta_path = _path(namespace, key, "json")
    if blob_path.exists() and meta_path.exists():
        try:
            return str(blob_path), json.loads(meta_path.read_text())
        except (ValueError, OSError):
            pass
    data, meta = await producer()
    actual = _safe_write(blob_path, data, ext)
    _safe_write(meta_path, json.dumps(meta).encode("utf-8"), "json")
    return actual, meta


def put_blob(namespace: str, parts: list, ext: str, data: bytes) -> str:
    path = _path(namespace, _key(parts), ext)
    if path.exists():
        return str(path)
    return _safe_write(path, data, ext)
```

Run: `uv run pytest tests/test_cache.py -q` -> PASS (7 tests). Then `uv run ruff check src tests`.

Note: the `_cache_dir` autouse fixture in the test is redundant with the per-test monkeypatch; if ruff/pytest flags the unused fixture, delete the autouse fixture and keep the per-test `monkeypatch.setattr` lines.

- [ ] **Step 3: Commit.**

```bash
git add backend/src/doppel_api/cache.py backend/tests/test_cache.py
git commit -m "feat(cache): content-addressed local cache module"
```

---

### Task 3: media.fetch (bytes from URL)

The worker needs fal output as bytes (to cache). `media` already has a private `_fetch(url)->bytes` used by `download`. Expose it as `fetch`.

**Files:**
- Modify: `backend/src/doppel_api/providers/media.py`
- Modify: `backend/tests/test_provider_media.py`

- [ ] **Step 1: Rename `_fetch` -> `fetch` and have `download` use it.** In `media.py`, change:

```python
async def fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def download(url: str, out_path: str) -> str:
    data = await fetch(url)
    await anyio.to_thread.run_sync(lambda: Path(out_path).write_bytes(data))
    return out_path
```

- [ ] **Step 2: Update the existing download test** in `backend/tests/test_provider_media.py` to monkeypatch `fetch` (it currently patches `_fetch`):

```python
async def test_download_writes_fetched_bytes(tmp_path, monkeypatch):
    async def fake_fetch(url: str) -> bytes:
        assert url == "https://fal.media/x.mp4"
        return b"VIDEO"

    monkeypatch.setattr(media, "fetch", fake_fetch)
    out = str(tmp_path / "x.mp4")
    result = await media.download("https://fal.media/x.mp4", out)
    assert result == out
    with open(out, "rb") as f:  # noqa: ASYNC230
        assert f.read() == b"VIDEO"
```

- [ ] **Step 3: Run + commit.**

Run: `uv run pytest tests/test_provider_media.py -q && uv run ruff check src tests` -> green.

```bash
git add backend/src/doppel_api/providers/media.py backend/tests/test_provider_media.py
git commit -m "feat(media): expose fetch(url) -> bytes for the cache layer"
```

---

### Task 4: build_script(transcript, target_seconds)

**Files:**
- Modify: `backend/src/doppel_api/providers/script.py`
- Modify: `backend/tests/test_provider_script.py`

- [ ] **Step 1: Update the test** `backend/tests/test_provider_script.py` so `build_script` takes `target_seconds` and the prompt reflects it. Replace the call + add an assertion:

```python
    monkeypatch.setattr(script, "_client", lambda: FakeClient())
    result = await script.build_script("quero um video sobre seguranca digital", 10)
    assert result == expected
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["tool_choice"] == {"type": "tool", "name": "emit_script"}
    assert "seguranca digital" in captured["messages"][0]["content"]
    assert "10" in captured["system"]  # target duration is in the system prompt
```

Run: `uv run pytest tests/test_provider_script.py -q` -> FAIL (build_script takes 1 arg).

- [ ] **Step 2: Parameterize the prompt.** In `backend/src/doppel_api/providers/script.py`, replace the module-level `_SYSTEM` string with a builder, and thread `target_seconds` through:

```python
def _system(target_seconds: int) -> str:
    words = round(target_seconds * 2.5)
    return (
        "Você é um roteirista de vídeos verticais curtos em PT-BR. A partir do briefing "
        f"falado do usuário, gere um roteiro de ~{target_seconds} segundos. A narração deve ser "
        f"primeira pessoa, natural, com cerca de {words} palavras. Crie de 2 a 4 cenas cobrindo "
        f"a linha do tempo de 0 a {target_seconds}s sem buracos, alternando 'avatar' (o usuário "
        "falando) e 'broll', com cortes curtos (janelas de 2 a 4s). Cada cena 'broll' precisa de "
        "um 'prompt' visual concreto (para gerar uma imagem) e um 'motion' (movimento de câmera "
        "para animar). Responda SOMENTE pela ferramenta emit_script."
    )


def _call(transcript: str, target_seconds: int) -> dict:
    settings = get_settings()
    resp = _client().messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        system=_system(target_seconds),
        messages=[{"role": "user", "content": transcript}],
        tools=[{
            "name": "emit_script",
            "description": "Emite o roteiro estruturado do vídeo.",
            "input_schema": _SCHEMA,
        }],
        tool_choice={"type": "tool", "name": "emit_script"},
    )
    return next(b.input for b in resp.content if b.type == "tool_use")


async def build_script(transcript: str, target_seconds: int) -> dict:
    return await anyio.to_thread.run_sync(_call, transcript, target_seconds)
```

(Delete the old `_SYSTEM` constant. Keep `_SCHEMA` unchanged.)

Run: `uv run pytest tests/test_provider_script.py -q` -> PASS. Then `uv run ruff check src tests`.

- [ ] **Step 3: Commit.**

```bash
git add backend/src/doppel_api/providers/script.py backend/tests/test_provider_script.py
git commit -m "feat(script): parameterize narration by target_seconds"
```

---

### Task 5: Wire the cache into the worker handlers + tests

Route every paid step in both handlers through `cache`. Providers stay pure. `_gen_broll` keeps graceful degrade. This is one atomic change (both handlers + helpers + tests).

**Files:**
- Modify: `backend/workers/worker.py`
- Modify: `backend/tests/test_worker.py`

- [ ] **Step 1: Rewrite the handlers in `backend/workers/worker.py`.** Update imports (add `from doppel_api import cache`), add the producer helpers, and replace `handle_avatar_prep`, `_gen_broll`, and `handle_fast_generate` with the cached versions below. Keep `WorkerContext`, `_fmt_exc`, `HANDLERS`, `process_one`, `main` as they are. Add `from doppel_api.config import get_settings` (already imported) and ensure `from doppel_api import cache` is added.

Add these helpers (near `_store_fal_video`, which can be removed - it is no longer used):

```python
async def _fabric_bytes(face_path: str, audio_path: str) -> bytes:
    face_url = await video.upload(face_path)
    audio_url = await video.upload(audio_path)
    return await media.fetch(await video.talking(face_url, audio_url))


async def _flux_bytes(prompt: str) -> bytes:
    return await media.fetch(await video.image(prompt))


async def _kling_bytes(image_path: str, motion: str) -> bytes:
    image_url = await video.upload(image_path)
    return await media.fetch(await video.broll(image_url, motion))
```

Replace `handle_avatar_prep` with:

```python
async def handle_avatar_prep(ctx: "WorkerContext", payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    settings = get_settings()
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        source_key = avatar.assets["source"]

    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    face_key = f"avatars/{avatar_id}/face.png"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        source_bytes = await ctx.storage.get(source_key)
        ext = "mp4" if source_key.endswith(".mp4") else "webm"
        cache.put_blob("source", [avatar_id], ext, source_bytes)  # keep the recording locally

        src = tmp / "source"
        src.write_bytes(source_bytes)
        face_path = await media.extract_frame(str(src), str(tmp / "face.png"))
        ref_path = await media.extract_audio(str(src), str(tmp / "ref.wav"))
        face_bytes = Path(face_path).read_bytes()
        ref_bytes = Path(ref_path).read_bytes()
        await ctx.storage.put(face_key, face_bytes, "image/png")

        voice_id = await cache.value(
            "clone", [ref_bytes],
            lambda: voice.clone(ref_path, name=f"doppel-{avatar_id[:8]}"),
        )
        model = settings.elevenlabs_model
        for line, key in ((HELLO_LINE, hello_key), (FEEDBACK_LINE, feedback_key)):
            audio_path = await cache.blob(
                "tts", [voice_id, line, model], "mp3",
                lambda v=voice_id, ln=line: voice.tts(v, ln),
            )
            audio_bytes = Path(audio_path).read_bytes()
            talk_path = await cache.blob(
                "fabric", [face_bytes, audio_bytes, "480p"], "mp4",
                lambda fp=face_path, ap=audio_path: _fabric_bytes(fp, ap),
            )
            await ctx.storage.put(key, Path(talk_path).read_bytes(), "video/mp4")

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
```

Replace `_gen_broll` with (note: no more `tmp` param; the clip path is the cache path):

```python
async def _gen_broll(ctx, scene, idx, total, video_id, sem) -> media.BrollClip | None:
    async with sem:
        try:
            prompt = scene.get("prompt", "")
            motion = scene.get("motion") or prompt
            img_path = await cache.blob(
                "flux", [prompt, "portrait_16_9"], "jpg", lambda p=prompt: _flux_bytes(p)
            )
            img_bytes = Path(img_path).read_bytes()
            clip_path = await cache.blob(
                "kling", [img_bytes, motion, "5"], "mp4",
                lambda ip=img_path, m=motion: _kling_bytes(ip, m),
            )
            await publish(ctx.redis, video_id, "progress", {"step": f"component_{idx + 2}_of_{total}"})
            return media.BrollClip(
                path=clip_path, start=float(scene["start"]), end=float(scene["end"])
            )
        except Exception as exc:  # graceful degrade: drop this scene, keep the video
            print(f"broll scene {scene.get('id')} failed, dropping: {_fmt_exc(exc)}")
            return None
```

Replace `handle_fast_generate` with:

```python
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
    model = settings.elevenlabs_model
    target = settings.video_target_seconds

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        briefing_bytes = await ctx.storage.get(briefing_key)
        brief = tmp / "briefing"
        brief.write_bytes(briefing_bytes)

        transcript = await cache.value("stt", [briefing_bytes], lambda: voice.stt(str(brief)))
        script_json = await cache.value(
            "script", [transcript, str(target)],
            lambda: script.build_script(transcript, target),
        )
        narration_text = script_json["narration"]["text"]

        async def _tts_ts_producer():
            audio, cues = await voice.tts_with_timestamps(voice_id, narration_text)
            return audio, [{"text": c.text, "start": c.start, "end": c.end} for c in cues]

        narration_path, cue_dicts = await cache.blob_with_meta(
            "tts_ts", [voice_id, narration_text, model], "mp3", _tts_ts_producer
        )
        cues = [media.CaptionCue(**c) for c in cue_dicts]

        face_bytes = await ctx.storage.get(face_key)
        face_path = tmp / "face.png"
        face_path.write_bytes(face_bytes)
        narration_bytes = Path(narration_path).read_bytes()

        broll_scenes = [sc for sc in script_json["scenes"] if sc["type"] == "broll"]
        total = 1 + len(broll_scenes)
        sem = asyncio.Semaphore(settings.pipeline_concurrency)

        async def gen_avatar() -> str:
            await publish(ctx.redis, video_id, "progress", {"step": f"component_1_of_{total}"})
            return await cache.blob(
                "fabric", [face_bytes, narration_bytes, "480p"], "mp4",
                lambda: _fabric_bytes(str(face_path), narration_path),
            )

        results = await asyncio.gather(
            gen_avatar(),
            *[_gen_broll(ctx, sc, i, total, video_id, sem)
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
```

- [ ] **Step 2: Update `backend/tests/test_worker.py`.** Three changes:

(a) Add imports at top:

```python
from collections import Counter
from doppel_api import config
```

(b) Give the `ctx` fixture an isolated cache dir (so cache writes go to a tmp dir, not the repo). Change the fixture signature and add the monkeypatch:

```python
@pytest.fixture
async def ctx(tmp_path, monkeypatch):
    monkeypatch.setattr(config.get_settings(), "cache_dir", str(tmp_path / "cache"), raising=False)
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
```

(c) Make `_patch_providers` count paid-provider calls and return the counter; update the `_gen_broll`-related fake signatures if needed (they are unchanged - `fake_image`, `fake_broll`, `fake_talking`, `fake_upload`, etc. keep their signatures). At the top of `_patch_providers` add:

```python
    counts = Counter()
```

wrap each paid fake to increment (e.g. `fake_clone` does `counts["clone"] += 1`, `fake_tts` -> `counts["tts"]`, `fake_tts_ts` -> `counts["tts_ts"]`, `fake_stt` -> `counts["stt"]`, `fake_build_script` -> `counts["script"]`, `fake_upload` -> `counts["upload"]`, `fake_talking` -> `counts["talking"]`, `fake_image` -> `counts["image"]`, `fake_broll` -> `counts["broll"]`), and `return counts` at the end. Existing tests ignore the return value, so they keep working.

(d) Add two cache-reuse tests:

```python
async def test_avatar_prep_second_run_uses_cache(ctx, monkeypatch):
    avatar_id = await _seed_avatar(ctx)
    counts = _patch_providers(monkeypatch)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(worker, "publish", noop)
    await worker.handle_avatar_prep(ctx, {"avatar_id": avatar_id})
    assert counts["clone"] == 1 and counts["talking"] == 2  # hello + feedback
    counts.clear()
    await worker.handle_avatar_prep(ctx, {"avatar_id": avatar_id})
    assert sum(counts.values()) == 0  # everything served from the cache


async def test_fast_generate_second_run_uses_cache(ctx, monkeypatch):
    await _seed_ready_avatar_and_video(ctx)
    video_id = (await _latest_video_id(ctx))
    counts = _patch_providers(monkeypatch)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(worker, "publish", noop)
    await worker.handle_fast_generate(ctx, {"video_id": video_id})
    assert counts["talking"] >= 1 and counts["script"] == 1
    counts.clear()
    await worker.handle_fast_generate(ctx, {"video_id": video_id})
    assert sum(counts.values()) == 0
```

Add the small helper `_latest_video_id` near the seed helpers:

```python
async def _latest_video_id(ctx) -> str:
    async with ctx.session_factory() as s:
        return (await s.execute(select(Video))).scalars().first().id
```

(`_seed_ready_avatar_and_video` already enqueues a fast_generate job; calling the handler directly with its video_id is fine. The existing `test_fast_generate_composes_video` calls `process_one`; the new test calls the handler directly to run it twice.)

- [ ] **Step 3: Run + ruff.**

Run: `uv run pytest -q && uv run ruff check src tests workers`
Expected: all green (existing worker tests still pass through the cache; 2 new cache-reuse tests pass; zero real provider/network calls).

- [ ] **Step 4: Commit.**

```bash
git add backend/workers/worker.py backend/tests/test_worker.py
git commit -m "feat(worker): cache paid provider artifacts; thread target_seconds"
```

---

## Self-review (run by the plan author)

**Spec coverage:**
- `cache.py` (blob/value/blob_with_meta/put_blob, atomic write, fallback, corrupt-as-miss): Task 2. Covered.
- What's cached + keys (source/clone/tts/tts_ts/stt/script/fabric/flux/kling): Task 5 wiring. Covered.
- Cache in the worker, providers pure: Task 5 (providers untouched). Covered.
- Host bind-mount + CACHE_DIR + gitignore: Task 1. Covered.
- VIDEO_TARGET_SECONDS in config + flows into build_script + into the `script` cache key: Tasks 1, 4, 5. Covered.
- media.fetch for bytes: Task 3. Covered.
- Tests prove 2nd run = no provider call: Task 5 (d). Covered.

**Placeholder scan:** none; every step has full code.

**Type/name consistency:** `cache.blob(namespace, parts, ext, producer)->path`, `cache.value(...)->obj`, `cache.blob_with_meta(...)->(path, meta)`, `cache.put_blob(...)->path` consistent between Task 2 and Task 5. `media.fetch` defined in Task 3, used in Task 5 helpers. `build_script(transcript, target_seconds)` defined Task 4, called Task 5. `CaptionCue(text,start,end)` round-trips via dicts in `_tts_ts_producer`. `_gen_broll` signature changed (dropped `tmp`) and its only caller (the gather in `handle_fast_generate`) is updated to match. `_store_fal_video` removed and no longer referenced.

**Risk note:** the worker cache-reuse tests assert `sum(counts.values()) == 0` on the second run; `media.extract_frame`/`extract_audio`/`compose_timeline` are local (not counted) and still run on the second pass - that is expected and not a paid call.

