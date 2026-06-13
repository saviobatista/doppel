# Doppel M0 Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Walking skeleton da experiência Doppel completa no Mac: frontend cinematográfico navegável de ponta a ponta, backend com fila e workers stub que produzem vídeos placeholder via ffmpeg, infraestrutura em docker compose com floci emulando S3.

**Architecture:** Monolito modular (PDR seção 4): FastAPI async + Postgres + Redis Streams (lanes interactive/background) + storage S3 via AWS SDK (floci no dev). Workers stub provam o pipeline fila-worker-storage-SSE sem nenhum modelo de IA. Frontend Vite + TypeScript vanilla com state machine explícita e efeitos em canvas.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 async, redis-py async, boto3, ffmpeg (stub videos), pytest + pytest-asyncio + fakeredis; Vite, TypeScript vanilla, vitest; docker compose, floci (hectorvent/floci), Postgres 17, Redis 7.

**Spec:** `docs/superpowers/specs/2026-06-12-doppel-design.md` (fase M0 da seção 13)

**Decisões de escopo M0** (anotadas para M1+):
- Sem Alembic: `create_all` no startup (migrations entram no M1).
- Sem tabela `components`: cache por componente só faz sentido com geração real (M1+).
- Upload WS bufferiza chunks em memória (~12 MB); multipart S3 streaming entra no M1.
- `DELETE /v1/me` apaga rows e marca o device; purge de objetos S3 listado no M1.
- Frontend roda com `npm run dev` no host (proxy para a api do compose); container web/Caddy entra no M1.
- Validação de rosto/áudio na gravação (MediaPipe) entra no M1; M0 grava sem validar.

---

## File Structure

```
/Users/savio/Project/
  docker-compose.yml          # postgres, redis, floci, api, stub-worker
  .env.example
  backend/
    pyproject.toml            # uv project: fastapi, sqlalchemy, redis, boto3
    Dockerfile
    src/doppel_api/
      __init__.py
      config.py               # Settings (pydantic-settings, prefixo DOPPEL_)
      db.py                   # engine async, session factory, init_db
      models.py               # Device, Avatar, Video, Job
      storage.py              # Storage protocol, S3Storage (boto3), MemoryStorage
      queue.py                # Redis Streams: enqueue, read_next, ack, ensure_groups
      events.py               # pub/sub de progresso + formato SSE
      deps.py                 # get_session, get_device (auth por X-Device-Token)
      main.py                 # app factory, CORS, startup, routers
      routes/
        __init__.py
        sessions.py           # POST /v1/sessions
        avatars.py            # WS /v1/avatars/stream, GET /v1/avatars/{id}/events
        videos.py             # POST /v1/videos, SSE, feedback, gallery, DELETE /v1/me
    workers/
      __init__.py
      stub_worker.py          # loop + handlers avatar_prep / fast_generate + ffmpeg stub
    tests/
      conftest.py             # app + MemoryStorage + fakeredis + sqlite em memória
      test_storage.py
      test_models.py
      test_sessions.py
      test_queue.py
      test_events.py
      test_avatars.py
      test_videos.py
      test_stub_worker.py
  frontend/
    package.json              # vite, typescript, vitest
    tsconfig.json
    vite.config.ts            # proxy /v1 -> localhost:8000
    index.html
    src/
      main.ts                 # loop da máquina: estado -> cena
      machine.ts              # state machine explícita
      strings.ts              # todo o copy PT-BR
      api.ts                  # session, WS upload, SSE clients, gallery
      style.css               # tela escura, stage, fades
      fx/
        typewriter.ts
        gears.ts              # canvas: engrenagens girando
        tvstatic.ts           # canvas: ruído + estabilização
      scenes/
        permission.ts
        reading.ts            # typewriter + gravação + upload streaming
        processing.ts         # gears + SSE até hello_ready
        hello.ts              # player do hello
        briefing.ts           # gravação de áudio + POST /v1/videos
        generating.ts         # gears + SSE até fast_ready
        reveal.ts             # tv static -> player
        feedback.ts           # thumbs up/down
        gallery.ts
      machine.test.ts         # vitest
```

Cada arquivo tem uma responsabilidade. Workers importam `doppel_api` (mesmo pacote instalado) para reusar config/models/storage/queue/events.

---

### Task 1: Scaffold do backend

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/doppel_api/__init__.py`
- Create: `backend/tests/conftest.py` (mínimo nesta task)
- Create: `backend/tests/test_scaffold.py`

- [ ] **Step 1: Criar projeto uv**

```bash
cd /Users/savio/Project && mkdir -p backend/src/doppel_api backend/tests backend/workers
```

Criar `backend/pyproject.toml`:

```toml
[project]
name = "doppel-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "aiosqlite>=0.20",
    "redis>=5.2",
    "boto3>=1.35",
    "anyio>=4.0",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.12",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "fakeredis>=2.26",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "UP", "ASYNC", "RUF"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/doppel_api", "workers"]
```

Criar `backend/src/doppel_api/__init__.py` e `backend/workers/__init__.py` vazios.

- [ ] **Step 2: Teste de fumaça do scaffold**

`backend/tests/test_scaffold.py`:

```python
def test_package_imports():
    import doppel_api  # noqa: F401
```

- [ ] **Step 3: Instalar e rodar**

Run: `cd /Users/savio/Project/backend && uv sync && uv run pytest -q`
Expected: `1 passed`

- [ ] **Step 4: Commit**

```bash
git add backend/ && git commit -m "feat(backend): scaffold uv project with fastapi deps"
```

---

### Task 2: Config e Storage

**Files:**
- Create: `backend/src/doppel_api/config.py`
- Create: `backend/src/doppel_api/storage.py`
- Test: `backend/tests/test_storage.py`

- [ ] **Step 1: Escrever testes falhando**

`backend/tests/test_storage.py`:

```python
import pytest

from doppel_api.config import Settings
from doppel_api.storage import MemoryStorage


def test_settings_defaults_and_env(monkeypatch):
    monkeypatch.setenv("DOPPEL_S3_BUCKET", "test-bucket")
    s = Settings()
    assert s.s3_bucket == "test-bucket"
    assert s.redis_url.startswith("redis://")


async def test_memory_storage_roundtrip():
    st = MemoryStorage()
    await st.ensure_bucket()
    await st.put("raw/a/source.webm", b"bytes", "video/webm")
    url = await st.presign_get("raw/a/source.webm")
    assert "raw/a/source.webm" in url
    assert await st.get("raw/a/source.webm") == b"bytes"


async def test_memory_storage_missing_key():
    st = MemoryStorage()
    with pytest.raises(KeyError):
        await st.get("nope")
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_storage.py -q`
Expected: FAIL (ModuleNotFoundError / ImportError)

- [ ] **Step 3: Implementar**

`backend/src/doppel_api/config.py`:

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOPPEL_")

    database_url: str = "postgresql+asyncpg://doppel:doppel@localhost:5432/doppel"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint: str | None = "http://localhost:4566"
    s3_bucket: str = "doppel-media"
    s3_region: str = "us-east-1"
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

`backend/src/doppel_api/storage.py`:

```python
from typing import Protocol

import anyio
import boto3

from doppel_api.config import Settings


class Storage(Protocol):
    async def ensure_bucket(self) -> None: ...
    async def put(self, key: str, data: bytes, content_type: str) -> None: ...
    async def get(self, key: str) -> bytes: ...
    async def presign_get(self, key: str) -> str: ...


class MemoryStorage:
    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def ensure_bucket(self) -> None:
        return None

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = data

    async def get(self, key: str) -> bytes:
        return self._objects[key]

    async def presign_get(self, key: str) -> str:
        return f"memory://{key}"


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region
        )

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except Exception:
                self._client.create_bucket(Bucket=self._bucket)

        await anyio.to_thread.run_sync(_ensure)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            return self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()

        return await anyio.to_thread.run_sync(_get)

    async def presign_get(self, key: str) -> str:
        return await anyio.to_thread.run_sync(
            lambda: self._client.generate_presigned_url(
                "get_object", Params={"Bucket": self._bucket, "Key": key}, ExpiresIn=3600
            )
        )
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_storage.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/doppel_api/config.py backend/src/doppel_api/storage.py backend/tests/test_storage.py
git commit -m "feat(backend): settings and storage layer (S3 via boto3, memory fake)"
```

---

### Task 3: Modelos e banco

**Files:**
- Create: `backend/src/doppel_api/models.py`
- Create: `backend/src/doppel_api/db.py`
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Teste falhando**

`backend/tests/test_models.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from doppel_api.db import init_db
from doppel_api.models import Avatar, Device, Job, Video


async def test_create_all_and_insert_graph():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as s:
        d = Device(token="tok123")
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id)
        s.add(a)
        await s.flush()
        v = Video(device_id=d.id, avatar_id=a.id)
        j = Job(kind="avatar_prep", lane="interactive", payload={"avatar_id": a.id})
        s.add_all([v, j])
        await s.commit()

    async with sessions() as s:
        av = (await s.execute(select(Avatar))).scalar_one()
        assert av.status == "recording"
        assert av.assets == {}
        vid = (await s.execute(select(Video))).scalar_one()
        assert vid.status_fast == "queued"
        job = (await s.execute(select(Job))).scalar_one()
        assert job.status == "queued"
        assert job.payload["avatar_id"] == av.id
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_models.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implementar**

`backend/src/doppel_api/models.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON}


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Avatar(Base):
    __tablename__ = "avatars"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="recording")
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    avatar_id: Mapped[str] = mapped_column(ForeignKey("avatars.id"), index=True)
    status_fast: Mapped[str] = mapped_column(String(16), default="queued")
    script: Mapped[dict | None] = mapped_column(JSON, default=None)
    assets: Mapped[dict] = mapped_column(JSON, default=dict)
    rating: Mapped[str | None] = mapped_column(String(8), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    lane: Mapped[str] = mapped_column(String(16), default="interactive")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    timings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

`backend/src/doppel_api/db.py`:

```python
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from doppel_api.config import get_settings
from doppel_api.models import Base


def make_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(url or get_settings().database_url)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_models.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/doppel_api/models.py backend/src/doppel_api/db.py backend/tests/test_models.py
git commit -m "feat(backend): device/avatar/video/job models and async db helpers"
```

---

### Task 4: App factory, conftest e POST /v1/sessions

**Files:**
- Create: `backend/src/doppel_api/deps.py`
- Create: `backend/src/doppel_api/main.py`
- Create: `backend/src/doppel_api/routes/__init__.py`
- Create: `backend/src/doppel_api/routes/sessions.py`
- Modify: `backend/tests/conftest.py`
- Test: `backend/tests/test_sessions.py`

- [ ] **Step 1: conftest com app de teste**

`backend/tests/conftest.py`:

```python
import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api.db import init_db, make_session_factory
from doppel_api.main import create_app
from doppel_api.storage import MemoryStorage


@pytest.fixture
async def app():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    application = create_app(
        session_factory=make_session_factory(engine),
        storage=MemoryStorage(),
        redis=fakeredis.aioredis.FakeRedis(decode_responses=True),
        run_startup=False,
    )
    yield application
    await engine.dispose()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def device_token(client) -> str:
    resp = await client.post("/v1/sessions")
    return resp.json()["token"]
```

- [ ] **Step 2: Teste falhando**

`backend/tests/test_sessions.py`:

```python
async def test_create_session_returns_device_and_token(client):
    resp = await client.post("/v1/sessions")
    assert resp.status_code == 201
    body = resp.json()
    assert body["device_id"]
    assert len(body["token"]) >= 32


async def test_auth_required_for_protected_route(client):
    resp = await client.get("/v1/gallery")
    assert resp.status_code == 401


async def test_auth_accepts_valid_token(client, device_token):
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": device_token})
    assert resp.status_code == 200
    assert resp.json() == {"videos": []}
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `uv run pytest tests/test_sessions.py -q`
Expected: FAIL (ImportError em doppel_api.main)

- [ ] **Step 4: Implementar**

`backend/src/doppel_api/deps.py`:

```python
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from doppel_api.models import Device


async def get_session(request: Request):
    async with request.app.state.session_factory() as session:
        yield session


def get_storage(request: Request):
    return request.app.state.storage


def get_redis(request: Request):
    return request.app.state.redis


async def get_device(
    x_device_token: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> Device:
    if not x_device_token:
        raise HTTPException(status_code=401, detail="missing token")
    result = await session.execute(
        select(Device).where(Device.token == x_device_token, Device.deleted_at.is_(None))
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=401, detail="invalid token")
    return device
```

`backend/src/doppel_api/routes/sessions.py`:

```python
import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from doppel_api.deps import get_session
from doppel_api.models import Device

router = APIRouter()


@router.post("/v1/sessions", status_code=201)
async def create_session(session: AsyncSession = Depends(get_session)) -> dict:
    device = Device(token=secrets.token_urlsafe(32))
    session.add(device)
    await session.commit()
    return {"device_id": device.id, "token": device.token}
```

`backend/src/doppel_api/main.py` (a rota /v1/gallery placeholder vem na Task 9; para este teste passar, registre já um stub mínimo aqui que será substituído):

```python
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.deps import get_device
from doppel_api.models import Device
from doppel_api.routes import sessions
from doppel_api.storage import S3Storage, Storage


def create_app(
    session_factory: async_sessionmaker | None = None,
    storage: Storage | None = None,
    redis=None,
    run_startup: bool = True,
) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_startup:
            engine = make_engine()
            app.state.session_factory = make_session_factory(engine)
            app.state.storage = S3Storage(settings)
            app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await init_db(engine)
            await app.state.storage.ensure_bucket()
        yield

    app = FastAPI(title="doppel-api", lifespan=lifespan)
    if session_factory is not None:
        app.state.session_factory = session_factory
    if storage is not None:
        app.state.storage = storage
    if redis is not None:
        app.state.redis = redis

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sessions.router)

    @app.get("/v1/gallery")
    async def gallery_stub(device: Device = Depends(get_device)) -> dict:
        return {"videos": []}

    return app
```

Criar `backend/src/doppel_api/routes/__init__.py` vazio.

- [ ] **Step 5: Rodar e ver passar**

Run: `uv run pytest tests/test_sessions.py -q`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/src/doppel_api backend/tests
git commit -m "feat(backend): app factory, device auth and POST /v1/sessions"
```

---

### Task 5: Fila (Redis Streams) e eventos de progresso

**Files:**
- Create: `backend/src/doppel_api/queue.py`
- Create: `backend/src/doppel_api/events.py`
- Test: `backend/tests/test_queue.py`
- Test: `backend/tests/test_events.py`

- [ ] **Step 1: Testes falhando**

`backend/tests/test_queue.py`:

```python
import fakeredis.aioredis
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api.db import init_db, make_session_factory
from doppel_api.queue import ack, ensure_groups, enqueue, read_next


@pytest.fixture
async def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    return make_session_factory(engine)


async def test_enqueue_creates_job_row_and_stream_entry(redis, session_factory):
    await ensure_groups(redis)
    async with session_factory() as s:
        job = await enqueue(redis, s, kind="avatar_prep", lane="interactive", payload={"x": 1})
        await s.commit()
    assert job.id
    msg = await read_next(redis, consumer="w1")
    assert msg is not None
    assert msg["job_id"] == job.id
    assert msg["lane"] == "interactive"


async def test_interactive_lane_drains_first(redis, session_factory):
    await ensure_groups(redis)
    async with session_factory() as s:
        bg = await enqueue(redis, s, kind="hq", lane="background", payload={})
        it = await enqueue(redis, s, kind="fast", lane="interactive", payload={})
        await s.commit()
    first = await read_next(redis, consumer="w1")
    assert first["job_id"] == it.id
    second = await read_next(redis, consumer="w1")
    assert second["job_id"] == bg.id
    await ack(redis, first["lane"], first["msg_id"])
    await ack(redis, second["lane"], second["msg_id"])


async def test_read_next_returns_none_when_empty(redis):
    await ensure_groups(redis)
    assert await read_next(redis, consumer="w1") is None
```

`backend/tests/test_events.py`:

```python
import asyncio

import fakeredis.aioredis

from doppel_api.events import publish, sse_format, subscribe


async def test_publish_subscribe_roundtrip():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    received = []

    async def listen():
        async for event, data in subscribe(redis, "av1"):
            received.append((event, data))
            break

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    await publish(redis, "av1", "hello_ready", {"url": "memory://hello"})
    await asyncio.wait_for(task, timeout=2)
    assert received == [("hello_ready", {"url": "memory://hello"})]


def test_sse_format():
    out = sse_format("status", {"value": "processing"})
    assert out == 'event: status\ndata: {"value": "processing"}\n\n'
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_queue.py tests/test_events.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implementar**

`backend/src/doppel_api/queue.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from doppel_api.models import Job

STREAMS = {"interactive": "jobs:interactive", "background": "jobs:background"}
GROUP = "workers"


async def ensure_groups(redis) -> None:
    for stream in STREAMS.values():
        try:
            await redis.xgroup_create(stream, GROUP, id="0", mkstream=True)
        except Exception:
            pass  # BUSYGROUP: grupo ja existe


async def enqueue(redis, session: AsyncSession, kind: str, lane: str, payload: dict) -> Job:
    job = Job(kind=kind, lane=lane, payload=payload)
    session.add(job)
    await session.flush()
    await redis.xadd(STREAMS[lane], {"job_id": job.id})
    return job


async def read_next(redis, consumer: str) -> dict | None:
    for lane in ("interactive", "background"):
        resp = await redis.xreadgroup(
            GROUP, consumer, {STREAMS[lane]: ">"}, count=1, block=100
        )
        if resp:
            _stream, messages = resp[0]
            msg_id, fields = messages[0]
            return {"msg_id": msg_id, "lane": lane, "job_id": fields["job_id"]}
    return None


async def ack(redis, lane: str, msg_id: str) -> None:
    await redis.xack(STREAMS[lane], GROUP, msg_id)
```

`backend/src/doppel_api/events.py`:

```python
import json
from collections.abc import AsyncIterator


def _channel(entity_id: str) -> str:
    return f"events:{entity_id}"


async def publish(redis, entity_id: str, event: str, data: dict) -> None:
    await redis.publish(_channel(entity_id), json.dumps({"event": event, "data": data}))


async def subscribe(redis, entity_id: str) -> AsyncIterator[tuple[str, dict]]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(_channel(entity_id))
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            payload = json.loads(message["data"])
            yield payload["event"], payload["data"]
    finally:
        await pubsub.unsubscribe(_channel(entity_id))


def sse_format(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_queue.py tests/test_events.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/doppel_api/queue.py backend/src/doppel_api/events.py backend/tests/test_queue.py backend/tests/test_events.py
git commit -m "feat(backend): redis streams queue with priority lanes and progress events"
```

---

### Task 6: Upload de avatar por WebSocket e SSE de progresso

**Files:**
- Create: `backend/src/doppel_api/routes/avatars.py`
- Modify: `backend/src/doppel_api/main.py` (registrar router, remover nada)
- Test: `backend/tests/test_avatars.py`

- [ ] **Step 1: Testes falhando**

`backend/tests/test_avatars.py`:

```python
import asyncio
import json

from sqlalchemy import select
from starlette.testclient import TestClient

from doppel_api.events import publish
from doppel_api.models import Avatar, Job


def _ws_upload(app, token: str) -> str:
    """Sobe 3 chunks fake pelo WS e retorna avatar_id."""
    with TestClient(app) as tc:
        with tc.websocket_connect(f"/v1/avatars/stream?t={token}") as ws:
            ws.send_text(json.dumps({"mime": "video/webm"}))
            first = json.loads(ws.receive_text())
            for chunk in (b"aaa", b"bbb", b"ccc"):
                ws.send_bytes(chunk)
            ws.send_text(json.dumps({"done": True}))
            final = json.loads(ws.receive_text())
    assert first["avatar_id"] == final["avatar_id"]
    assert final["status"] == "processing"
    return final["avatar_id"]


async def test_ws_upload_stores_source_and_enqueues_job(app, client, device_token):
    avatar_id = await asyncio.to_thread(_ws_upload, app, device_token)

    storage = app.state.storage
    data = await storage.get(f"raw/{avatar_id}/source.webm")
    assert data == b"aaabbbccc"

    async with app.state.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
        assert avatar.id == avatar_id
        assert avatar.status == "processing"
        job = (await s.execute(select(Job))).scalar_one()
        assert job.kind == "avatar_prep"
        assert job.payload == {"avatar_id": avatar_id}
        assert job.lane == "interactive"


async def test_avatar_events_sse_streams_published_events(app, client, device_token):
    avatar_id = await asyncio.to_thread(_ws_upload, app, device_token)

    async def emit():
        await asyncio.sleep(0.2)
        await publish(app.state.redis, avatar_id, "hello_ready", {"hello_url": "memory://h"})

    task = asyncio.create_task(emit())
    lines: list[str] = []
    async with client.stream(
        "GET", f"/v1/avatars/{avatar_id}/events", headers={"X-Device-Token": device_token}
    ) as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            lines.append(line)
            if line == "event: hello_ready":
                break
    await task
    assert "event: status" in lines  # estado atual enviado na conexao
    assert "event: hello_ready" in lines


async def test_ws_rejects_invalid_token(app):
    def attempt():
        with TestClient(app) as tc:
            with tc.websocket_connect("/v1/avatars/stream?t=wrong") as ws:
                return json.loads(ws.receive_text())

    result = await asyncio.to_thread(attempt)
    assert result == {"error": "invalid token"}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_avatars.py -q`
Expected: FAIL (404 / ImportError)

- [ ] **Step 3: Implementar**

`backend/src/doppel_api/routes/avatars.py`:

```python
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import publish, sse_format, subscribe
from doppel_api.models import Avatar, Device
from doppel_api.queue import enqueue

router = APIRouter()


@router.websocket("/v1/avatars/stream")
async def avatar_stream(ws: WebSocket):
    await ws.accept()
    token = ws.query_params.get("t", "")
    app = ws.app
    async with app.state.session_factory() as session:
        result = await session.execute(
            select(Device).where(Device.token == token, Device.deleted_at.is_(None))
        )
        device = result.scalar_one_or_none()
        if device is None:
            await ws.send_text(json.dumps({"error": "invalid token"}))
            await ws.close()
            return

        header = json.loads(await ws.receive_text())
        ext = "mp4" if "mp4" in header.get("mime", "") else "webm"
        avatar = Avatar(device_id=device.id)
        session.add(avatar)
        await session.commit()
        await ws.send_text(json.dumps({"avatar_id": avatar.id}))

        chunks: list[bytes] = []
        while True:
            message = await ws.receive()
            if "bytes" in message and message["bytes"] is not None:
                chunks.append(message["bytes"])
                continue
            if "text" in message and message["text"]:
                control = json.loads(message["text"])
                if control.get("done"):
                    break
            if message.get("type") == "websocket.disconnect":
                return  # gravacao abandonada: avatar fica em recording

        key = f"raw/{avatar.id}/source.{ext}"
        await app.state.storage.put(key, b"".join(chunks), header.get("mime", "video/webm"))
        avatar.status = "processing"
        avatar.assets = {"source": key}
        await enqueue(
            app.state.redis, session, kind="avatar_prep", lane="interactive",
            payload={"avatar_id": avatar.id},
        )
        await session.commit()
        await publish(app.state.redis, avatar.id, "status", {"value": "processing"})
        await ws.send_text(json.dumps({"avatar_id": avatar.id, "status": "processing"}))
        await ws.close()


@router.get("/v1/avatars/{avatar_id}/events")
async def avatar_events(
    avatar_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
):
    result = await session.execute(
        select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
    )
    avatar = result.scalar_one_or_none()
    if avatar is None:
        raise HTTPException(status_code=404)

    async def stream():
        yield sse_format("status", {"value": avatar.status, "assets": avatar.assets})
        if avatar.status == "ready":
            return
        async for event, data in subscribe(redis, avatar_id):
            yield sse_format(event, data)
            if event in ("hello_ready", "failed"):
                return

    return StreamingResponse(stream(), media_type="text/event-stream")
```

Em `backend/src/doppel_api/main.py`, adicionar import e registro:

```python
from doppel_api.routes import avatars, sessions
# ...
    app.include_router(sessions.router)
    app.include_router(avatars.router)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_avatars.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/doppel_api backend/tests/test_avatars.py
git commit -m "feat(backend): websocket avatar upload and SSE progress endpoint"
```

---

### Task 7: Stub worker (framework + avatar_prep)

**Files:**
- Create: `backend/workers/stub_worker.py`
- Test: `backend/tests/test_stub_worker.py`

O worker gera vídeos placeholder com ffmpeg (`testsrc2` + `drawtext` + tom `sine`). Nos testes, `make_stub_video` é substituído por monkeypatch (sem exigir ffmpeg no ambiente de teste).

- [ ] **Step 1: Testes falhando**

`backend/tests/test_stub_worker.py`:

```python
import fakeredis.aioredis
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from doppel_api.db import init_db, make_session_factory
from doppel_api.models import Avatar, Device, Video
from doppel_api.queue import ensure_groups, enqueue
from doppel_api.storage import MemoryStorage
from workers import stub_worker
from workers.stub_worker import WorkerContext, process_one


@pytest.fixture
async def ctx(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await ensure_groups(redis)
    monkeypatch.setattr(stub_worker, "make_stub_video", lambda path, seconds, label: path.write_bytes(b"MP4" + label.encode()))
    return WorkerContext(
        session_factory=make_session_factory(engine),
        storage=MemoryStorage(),
        redis=redis,
        consumer="test-worker",
    )


async def _seed_avatar(ctx) -> str:
    async with ctx.session_factory() as s:
        d = Device(token="t" * 32)
        s.add(d)
        await s.flush()
        a = Avatar(device_id=d.id, status="processing", assets={"source": "raw/x/source.webm"})
        s.add(a)
        await enqueue(ctx.redis, s, kind="avatar_prep", lane="interactive", payload={"avatar_id": a.id})
        await s.commit()
        return a.id


async def test_process_one_returns_false_on_empty_queue(ctx):
    assert await process_one(ctx) is False


async def test_avatar_prep_produces_hello_and_feedback(ctx):
    avatar_id = await _seed_avatar(ctx)

    events: list[tuple[str, dict]] = []

    async def capture(redis, entity_id, event, data):
        events.append((event, data))

    import workers.stub_worker as sw
    original_publish = sw.publish
    sw.publish = capture
    try:
        assert await process_one(ctx) is True
    finally:
        sw.publish = original_publish

    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar))).scalar_one()
    assert avatar.status == "ready"
    assert avatar.assets["hello"] == f"avatars/{avatar_id}/hello.mp4"
    assert avatar.assets["feedback"] == f"avatars/{avatar_id}/feedback.mp4"
    assert await ctx.storage.get(avatar.assets["hello"]) == b"MP4HELLO"

    names = [e for e, _ in events]
    assert names[-1] == "hello_ready"
    assert "hello_url" in events[-1][1]
    assert "feedback_url" in events[-1][1]
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_stub_worker.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implementar**

`backend/workers/stub_worker.py`:

```python
"""Stub worker do M0: consome jobs e produz videos placeholder via ffmpeg."""
import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import anyio
import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.events import publish
from doppel_api.models import Avatar, Job, Video
from doppel_api.queue import ack, ensure_groups, read_next
from doppel_api.storage import S3Storage, Storage


@dataclass
class WorkerContext:
    session_factory: async_sessionmaker
    storage: Storage
    redis: object
    consumer: str


def make_stub_video(path: Path, seconds: int, label: str) -> None:
    """Gera um mp4 9:16 com texto central e tom de audio. Requer ffmpeg no PATH."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size=540x960:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
        "-vf", f"drawtext=text='{label}':fontcolor=white:fontsize=64:"
               "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


async def _render_and_upload(ctx: WorkerContext, key: str, seconds: int, label: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.mp4"
        await anyio.to_thread.run_sync(lambda: make_stub_video(out, seconds, label))
        await ctx.storage.put(key, out.read_bytes(), "video/mp4")


async def handle_avatar_prep(ctx: WorkerContext, payload: dict) -> None:
    avatar_id = payload["avatar_id"]
    await publish(ctx.redis, avatar_id, "progress", {"step": "preparing_avatar"})
    hello_key = f"avatars/{avatar_id}/hello.mp4"
    feedback_key = f"avatars/{avatar_id}/feedback.mp4"
    await _render_and_upload(ctx, hello_key, 6, "HELLO")
    await _render_and_upload(ctx, feedback_key, 4, "FEEDBACK")
    async with ctx.session_factory() as s:
        avatar = (await s.execute(select(Avatar).where(Avatar.id == avatar_id))).scalar_one()
        avatar.status = "ready"
        avatar.assets = {**avatar.assets, "hello": hello_key, "feedback": feedback_key}
        await s.commit()
    hello_url = await ctx.storage.presign_get(hello_key)
    feedback_url = await ctx.storage.presign_get(feedback_key)
    await publish(ctx.redis, avatar_id, "hello_ready",
                  {"hello_url": hello_url, "feedback_url": feedback_url})


async def handle_fast_generate(ctx: WorkerContext, payload: dict) -> None:
    video_id = payload["video_id"]
    await publish(ctx.redis, video_id, "progress", {"step": "scripting"})
    await asyncio.sleep(0.5)  # latencia artificial visivel na UI
    for n in (1, 2, 3):
        await publish(ctx.redis, video_id, "progress", {"step": f"component_{n}_of_3"})
        await asyncio.sleep(0.5)
    key = f"videos/{video_id}/fast.mp4"
    await _render_and_upload(ctx, key, 30, "DOPPEL FAST STUB")
    async with ctx.session_factory() as s:
        video = (await s.execute(select(Video).where(Video.id == video_id))).scalar_one()
        video.status_fast = "ready"
        video.assets = {**video.assets, "fast": key}
        video.script = {"narration": {"text": "stub"}, "scenes": [], "music": {}, "captions": {}}
        await s.commit()
    url = await ctx.storage.presign_get(key)
    await publish(ctx.redis, video_id, "fast_ready", {"fast_url": url})


HANDLERS = {"avatar_prep": handle_avatar_prep, "fast_generate": handle_fast_generate}


async def process_one(ctx: WorkerContext) -> bool:
    msg = await read_next(ctx.redis, consumer=ctx.consumer)
    if msg is None:
        return False
    async with ctx.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.id == msg["job_id"]))).scalar_one()
        job.status = "running"
        await s.commit()
        kind, payload = job.kind, dict(job.payload)
    try:
        await HANDLERS[kind](ctx, payload)
        status = "done"
    except Exception:
        status = "failed"
        entity_id = payload.get("avatar_id") or payload.get("video_id") or ""
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
        redis=redis, consumer="stub-1",
    )
    print("stub worker started")
    while True:
        worked = await process_one(ctx)
        if not worked:
            await asyncio.sleep(0.2)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Rodar e ver passar**

Run: `uv run pytest tests/test_stub_worker.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/workers backend/tests/test_stub_worker.py
git commit -m "feat(worker): stub worker with avatar_prep and fast_generate handlers"
```

---

### Task 8: Rotas de vídeo (criar, eventos, feedback, galeria, delete)

**Files:**
- Create: `backend/src/doppel_api/routes/videos.py`
- Modify: `backend/src/doppel_api/main.py` (registrar router e REMOVER o stub `/v1/gallery`)
- Test: `backend/tests/test_videos.py`

- [ ] **Step 1: Testes falhando**

`backend/tests/test_videos.py`:

```python
import asyncio

from sqlalchemy import select

from doppel_api.events import publish
from doppel_api.models import Avatar, Device, Job, Video


async def _seed_ready_avatar(app, device_token: str) -> str:
    async with app.state.session_factory() as s:
        device = (await s.execute(select(Device))).scalar_one()
        avatar = Avatar(device_id=device.id, status="ready", assets={"source": "raw/k"})
        s.add(avatar)
        await s.commit()
        return avatar.id


async def test_create_video_enqueues_fast_generate(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos",
        headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id},
        files={"briefing": ("briefing.webm", b"audio-bytes", "audio/webm")},
    )
    assert resp.status_code == 201
    video_id = resp.json()["video_id"]
    async with app.state.session_factory() as s:
        job = (await s.execute(select(Job).where(Job.kind == "fast_generate"))).scalar_one()
        assert job.payload == {"video_id": video_id}
    data = await app.state.storage.get(f"videos/{video_id}/briefing.webm")
    assert data == b"audio-bytes"


async def test_video_events_sse(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id},
        files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    video_id = resp.json()["video_id"]

    async def emit():
        await asyncio.sleep(0.2)
        await publish(app.state.redis, video_id, "fast_ready", {"fast_url": "memory://f"})

    task = asyncio.create_task(emit())
    lines = []
    async with client.stream(
        "GET", f"/v1/videos/{video_id}/events", headers={"X-Device-Token": device_token}
    ) as r:
        async for line in r.aiter_lines():
            lines.append(line)
            if line == "event: fast_ready":
                break
    await task
    assert "event: status" in lines


async def test_feedback_up_sets_rating(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id}, files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    video_id = resp.json()["video_id"]
    resp = await client.post(
        f"/v1/videos/{video_id}/feedback",
        headers={"X-Device-Token": device_token}, json={"rating": "up"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"video_id": video_id, "action": "gallery"}


async def test_feedback_down_creates_regen_video(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    resp = await client.post(
        "/v1/videos", headers={"X-Device-Token": device_token},
        data={"avatar_id": avatar_id}, files={"briefing": ("b.webm", b"x", "audio/webm")},
    )
    first_id = resp.json()["video_id"]
    resp = await client.post(
        f"/v1/videos/{first_id}/feedback",
        headers={"X-Device-Token": device_token}, json={"rating": "down"},
    )
    assert resp.status_code == 200
    new_id = resp.json()["video_id"]
    assert new_id != first_id
    assert resp.json()["action"] == "regenerate"
    async with app.state.session_factory() as s:
        jobs = (await s.execute(select(Job).where(Job.kind == "fast_generate"))).scalars().all()
        assert {j.payload["video_id"] for j in jobs} == {first_id, new_id}


async def test_gallery_lists_ready_videos_with_urls(app, client, device_token):
    avatar_id = await _seed_ready_avatar(app, device_token)
    async with app.state.session_factory() as s:
        device = (await s.execute(select(Device))).scalar_one()
        v = Video(device_id=device.id, avatar_id=avatar_id, status_fast="ready",
                  assets={"fast": "videos/v1/fast.mp4"}, rating="up")
        s.add(v)
        await s.commit()
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": device_token})
    assert resp.status_code == 200
    videos = resp.json()["videos"]
    assert len(videos) == 1
    assert videos[0]["fast_url"] == "memory://videos/v1/fast.mp4"


async def test_delete_me_revokes_token_and_rows(app, client, device_token):
    resp = await client.delete("/v1/me", headers={"X-Device-Token": device_token})
    assert resp.status_code == 204
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": device_token})
    assert resp.status_code == 401
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `uv run pytest tests/test_videos.py -q`
Expected: FAIL (404 nas rotas)

- [ ] **Step 3: Implementar**

`backend/src/doppel_api/routes/videos.py`:

```python
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from doppel_api.deps import get_device, get_redis, get_session, get_storage
from doppel_api.events import sse_format, subscribe
from doppel_api.models import Avatar, Device, Video
from doppel_api.queue import enqueue

router = APIRouter()


class FeedbackIn(BaseModel):
    rating: str  # "up" | "down"


@router.post("/v1/videos", status_code=201)
async def create_video(
    avatar_id: str = Form(...),
    briefing: UploadFile | None = None,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
    redis=Depends(get_redis),
) -> dict:
    result = await session.execute(
        select(Avatar).where(Avatar.id == avatar_id, Avatar.device_id == device.id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="avatar not found")

    video = Video(device_id=device.id, avatar_id=avatar_id)
    session.add(video)
    await session.flush()
    if briefing is not None:
        key = f"videos/{video.id}/briefing.webm"
        await storage.put(key, await briefing.read(), briefing.content_type or "audio/webm")
        video.assets = {"briefing": key}
    await enqueue(redis, session, kind="fast_generate", lane="interactive",
                  payload={"video_id": video.id})
    await session.commit()
    return {"video_id": video.id}


@router.get("/v1/videos/{video_id}/events")
async def video_events(
    video_id: str,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
    storage=Depends(get_storage),
):
    result = await session.execute(
        select(Video).where(Video.id == video_id, Video.device_id == device.id)
    )
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404)

    async def stream():
        data = {"value": video.status_fast}
        if video.status_fast == "ready" and "fast" in video.assets:
            data["fast_url"] = await storage.presign_get(video.assets["fast"])
        yield sse_format("status", data)
        if video.status_fast == "ready":
            return
        async for event, payload in subscribe(redis, video_id):
            yield sse_format(event, payload)
            if event in ("fast_ready", "failed"):
                return

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/v1/videos/{video_id}/feedback")
async def feedback(
    video_id: str,
    body: FeedbackIn,
    device: Device = Depends(get_device),
    session=Depends(get_session),
    redis=Depends(get_redis),
) -> dict:
    result = await session.execute(
        select(Video).where(Video.id == video_id, Video.device_id == device.id)
    )
    video = result.scalar_one_or_none()
    if video is None:
        raise HTTPException(status_code=404)
    video.rating = body.rating
    if body.rating == "up":
        await session.commit()
        return {"video_id": video_id, "action": "gallery"}
    regen = Video(device_id=device.id, avatar_id=video.avatar_id)
    session.add(regen)
    await session.flush()
    await enqueue(redis, session, kind="fast_generate", lane="interactive",
                  payload={"video_id": regen.id})
    await session.commit()
    return {"video_id": regen.id, "action": "regenerate"}


@router.get("/v1/gallery")
async def gallery(
    device: Device = Depends(get_device),
    session=Depends(get_session),
    storage=Depends(get_storage),
) -> dict:
    result = await session.execute(
        select(Video).where(
            Video.device_id == device.id, Video.status_fast == "ready", Video.rating == "up"
        ).order_by(Video.created_at.desc())
    )
    videos = []
    for v in result.scalars():
        videos.append({
            "video_id": v.id,
            "created_at": v.created_at.isoformat(),
            "fast_url": await storage.presign_get(v.assets["fast"]),
        })
    return {"videos": videos}


@router.delete("/v1/me", status_code=204)
async def delete_me(
    device: Device = Depends(get_device),
    session=Depends(get_session),
) -> None:
    from datetime import datetime, timezone

    await session.execute(sql_delete(Video).where(Video.device_id == device.id))
    await session.execute(sql_delete(Avatar).where(Avatar.device_id == device.id))
    merged = await session.merge(device)
    merged.deleted_at = datetime.now(timezone.utc)
    await session.commit()
```

Em `backend/src/doppel_api/main.py`: adicionar `videos` ao import de routes, registrar `app.include_router(videos.router)` e **remover por completo** a função `gallery_stub` e o import de `get_device`/`Device` que só existiam para ela.

- [ ] **Step 4: Rodar a suíte inteira**

Run: `uv run pytest -q`
Expected: todos passam (test_sessions usa a galeria real agora; comportamento idêntico)

- [ ] **Step 5: Commit**

```bash
git add backend/src/doppel_api backend/tests/test_videos.py
git commit -m "feat(backend): video creation, SSE, feedback loop, gallery and LGPD delete"
```

---

### Task 9: Dockerfile do backend e docker-compose com floci

**Files:**
- Create: `backend/Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`

- [ ] **Step 1: Dockerfile**

`backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY src ./src
COPY workers ./workers
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "doppel_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: docker-compose.yml**

```yaml
name: doppel

services:
  postgres:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: doppel
      POSTGRES_PASSWORD: doppel
      POSTGRES_DB: doppel
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U doppel"]
      interval: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      retries: 10

  floci:
    image: hectorvent/floci:latest
    ports: ["4566:4566"]
    volumes: [flocidata:/app/data]

  api:
    build: ./backend
    environment: &doppel_env
      DOPPEL_DATABASE_URL: postgresql+asyncpg://doppel:doppel@postgres:5432/doppel
      DOPPEL_REDIS_URL: redis://redis:6379/0
      DOPPEL_S3_ENDPOINT: http://floci:4566
      DOPPEL_S3_BUCKET: doppel-media
      AWS_ACCESS_KEY_ID: test
      AWS_SECRET_ACCESS_KEY: test
      AWS_DEFAULT_REGION: us-east-1
    ports: ["8000:8000"]
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
      floci: {condition: service_started}

  stub-worker:
    build: ./backend
    command: ["python", "-m", "workers.stub_worker"]
    environment: *doppel_env
    depends_on:
      api: {condition: service_started}

volumes:
  pgdata:
  flocidata:
```

`.env.example`:

```bash
# Frontend (vite): API base; default proxy assume localhost:8000
VITE_API_URL=http://localhost:8000
# Backend fora do compose (uvicorn local):
DOPPEL_DATABASE_URL=postgresql+asyncpg://doppel:doppel@localhost:5432/doppel
DOPPEL_REDIS_URL=redis://localhost:6379/0
DOPPEL_S3_ENDPOINT=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
```

- [ ] **Step 3: Subir e validar de ponta a ponta com curl**

```bash
cd /Users/savio/Project && docker compose up -d --build
sleep 5
TOKEN=$(curl -s -X POST localhost:8000/v1/sessions | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -s localhost:8000/v1/gallery -H "X-Device-Token: $TOKEN"
```

Expected: `{"videos":[]}`. Logs limpos: `docker compose logs api stub-worker | tail -20` sem tracebacks.

A presigned URL gerada pela api aponta para `http://floci:4566` (hostname interno). Para o browser funcionar no M0, o host `floci` precisa resolver no Mac:

```bash
grep -q "floci" /etc/hosts || echo "127.0.0.1 floci" | sudo tee -a /etc/hosts
```

(Documentar no README do M1 a alternativa definitiva: presign com endpoint público configurável.)

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml .env.example
git commit -m "feat(infra): docker compose with postgres, redis, floci, api and stub worker"
```

---

### Task 10: Scaffold do frontend, strings e state machine (com testes)

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`
- Create: `frontend/src/strings.ts`, `frontend/src/machine.ts`, `frontend/src/style.css`
- Test: `frontend/src/machine.test.ts`

- [ ] **Step 1: Scaffold**

`frontend/package.json`:

```json
{
  "name": "doppel-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "test": "vitest run"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true,
    "noEmit": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`frontend/vite.config.ts`:

```typescript
import { defineConfig } from "vite";

export default defineConfig({});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Doppel</title>
  </head>
  <body>
    <div id="stage"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 2: Strings PT-BR**

`frontend/src/strings.ts`:

```typescript
export const STR = {
  start: "Começar",
  galleryLink: "Galeria",
  permissionError: "Preciso da câmera e do microfone para criar seu avatar.",
  typewriterIntro: "Agora leia em voz alta o texto a seguir...",
  readingText:
    "Eu, em sã consciência, autorizo a criação de um avatar digital com meu rosto " +
    "e minha voz, para gerar vídeos sob meu comando dentro deste aplicativo. " +
    "Sei que posso apagar meus dados a qualquer momento. " +
    "O vento sopra forte sobre o juazeiro enquanto doze garotos observam o equilibrista.",
  readingDone: "Terminei a leitura",
  processing: "Construindo seu avatar...",
  briefingPrompt: "Me conta: que vídeo vamos fazer? Onde, sobre o quê, em que clima?",
  briefingDone: "Pronto",
  generatingSteps: {
    scripting: "Escrevendo o roteiro...",
    component_1_of_3: "Gerando cena 1 de 3...",
    component_2_of_3: "Gerando cena 2 de 3...",
    component_3_of_3: "Gerando cena 3 de 3...",
  } as Record<string, string>,
  thumbsUp: "Curti",
  thumbsDown: "Não curti",
  newVideo: "Criar outro vídeo",
  deleteMe: "Apagar meus dados",
  genericError: "Algo deu errado. Vamos tentar de novo?",
  retry: "Recomeçar",
} as const;
```

- [ ] **Step 3: Teste falhando da máquina**

`frontend/src/machine.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { Machine } from "./machine";

describe("Machine", () => {
  it("starts idle and follows the happy path", () => {
    const m = new Machine();
    expect(m.state).toBe("idle");
    for (const s of ["permission", "reading", "processing", "hello",
                     "briefing", "generating", "reveal", "feedback", "gallery"] as const) {
      m.go(s);
      expect(m.state).toBe(s);
    }
  });

  it("allows thumbs-down regeneration loop", () => {
    const m = new Machine();
    m.go("permission"); m.go("reading"); m.go("processing"); m.go("hello");
    m.go("briefing"); m.go("generating"); m.go("reveal"); m.go("feedback");
    m.go("generating");
    expect(m.state).toBe("generating");
  });

  it("throws on illegal transition", () => {
    const m = new Machine();
    expect(() => m.go("reveal")).toThrow(/illegal transition/);
  });

  it("notifies listeners on change", () => {
    const m = new Machine();
    const seen: string[] = [];
    m.onChange((s) => seen.push(s));
    m.go("permission");
    expect(seen).toEqual(["permission"]);
  });
});
```

- [ ] **Step 4: Rodar e ver falhar**

Run: `cd /Users/savio/Project/frontend && npm install && npm test`
Expected: FAIL (machine.ts não existe)

- [ ] **Step 5: Implementar a máquina**

`frontend/src/machine.ts`:

```typescript
export type State =
  | "idle" | "permission" | "reading" | "processing" | "hello"
  | "briefing" | "generating" | "reveal" | "feedback" | "gallery" | "error";

const TRANSITIONS: Record<State, State[]> = {
  idle: ["permission", "gallery"],
  permission: ["reading", "error"],
  reading: ["processing", "error"],
  processing: ["hello", "error"],
  hello: ["briefing"],
  briefing: ["generating", "error"],
  generating: ["reveal", "error"],
  reveal: ["feedback"],
  feedback: ["gallery", "generating"],
  gallery: ["briefing", "idle"],
  error: ["idle"],
};

export class Machine {
  state: State = "idle";
  private listeners: Array<(s: State) => void> = [];

  go(next: State): void {
    if (!TRANSITIONS[this.state].includes(next)) {
      throw new Error(`illegal transition ${this.state} -> ${next}`);
    }
    this.state = next;
    for (const listener of this.listeners) listener(next);
  }

  onChange(cb: (s: State) => void): void {
    this.listeners.push(cb);
  }
}
```

- [ ] **Step 6: Rodar e ver passar**

Run: `npm test`
Expected: `4 passed`

- [ ] **Step 7: CSS base**

`frontend/src/style.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { height: 100%; background: #000; color: #eee;
  font-family: ui-monospace, "SF Mono", Menlo, monospace; }
#stage { position: fixed; inset: 0; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 24px; padding: 24px;
  text-align: center; transition: opacity 600ms ease; }
#stage.faded { opacity: 0; }
button { background: transparent; color: #eee; border: 1px solid #555;
  padding: 12px 28px; font: inherit; font-size: 16px; cursor: pointer;
  border-radius: 6px; }
button:hover { border-color: #eee; }
.reading-text { max-width: 640px; font-size: 22px; line-height: 1.6; }
.rec-dot { width: 12px; height: 12px; border-radius: 50%; background: #e33;
  display: inline-block; animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0.2; } }
.typewriter { font-size: 20px; min-height: 28px; }
video.player { max-width: 100%; max-height: 80vh; aspect-ratio: 9 / 16;
  background: #000; }
canvas.fx { position: fixed; inset: 0; width: 100%; height: 100%; }
.label { font-size: 16px; color: #999; }
.gallery-grid { display: grid; grid-template-columns: repeat(auto-fill, 180px);
  gap: 16px; max-width: 800px; overflow-y: auto; max-height: 70vh; }
.gallery-grid video { width: 180px; aspect-ratio: 9 / 16; background: #111; }
.row { display: flex; gap: 16px; }
```

- [ ] **Step 8: Commit**

```bash
git add frontend/
git commit -m "feat(web): vite scaffold, PT-BR strings, state machine with tests"
```

---

### Task 11: Efeitos visuais (typewriter, engrenagens, TV static)

**Files:**
- Create: `frontend/src/fx/typewriter.ts`
- Create: `frontend/src/fx/gears.ts`
- Create: `frontend/src/fx/tvstatic.ts`

Efeitos são validados visualmente na Task 14 (smoke manual); sem testes unitários de canvas.

- [ ] **Step 1: Typewriter**

`frontend/src/fx/typewriter.ts`:

```typescript
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function typewriter(
  el: HTMLElement, text: string, msPerChar = 45,
): Promise<void> {
  el.textContent = "";
  for (const ch of text) {
    el.textContent += ch;
    await sleep(msPerChar);
  }
}
```

- [ ] **Step 2: Engrenagens em canvas**

`frontend/src/fx/gears.ts`:

```typescript
function drawGear(
  ctx: CanvasRenderingContext2D, cx: number, cy: number,
  radius: number, teeth: number, angle: number,
): void {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(angle);
  ctx.strokeStyle = "#4ad";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(0, 0, radius, 0, Math.PI * 2);
  ctx.stroke();
  for (let i = 0; i < teeth; i++) {
    const a = (i / teeth) * Math.PI * 2;
    ctx.save();
    ctx.rotate(a);
    ctx.strokeRect(radius - 2, -4, 14, 8);
    ctx.restore();
  }
  ctx.beginPath();
  ctx.arc(0, 0, radius * 0.25, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

export class Gears {
  private canvas: HTMLCanvasElement;
  private raf = 0;
  private label = "";

  constructor(parent: HTMLElement) {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "fx";
    parent.appendChild(this.canvas);
  }

  setLabel(text: string): void {
    this.label = text;
  }

  start(): void {
    const ctx = this.canvas.getContext("2d")!;
    const tick = (t: number) => {
      this.canvas.width = this.canvas.clientWidth;
      this.canvas.height = this.canvas.clientHeight;
      const { width: w, height: h } = this.canvas;
      ctx.clearRect(0, 0, w, h);
      drawGear(ctx, w / 2 - 40, h / 2 - 30, 56, 10, t / 900);
      drawGear(ctx, w / 2 + 48, h / 2 + 42, 38, 8, -t / 600);
      ctx.fillStyle = "#999";
      ctx.font = "16px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText(this.label, w / 2, h / 2 + 140);
      this.raf = requestAnimationFrame(tick);
    };
    this.raf = requestAnimationFrame(tick);
  }

  stop(): void {
    cancelAnimationFrame(this.raf);
    this.canvas.remove();
  }
}
```

- [ ] **Step 3: TV static**

`frontend/src/fx/tvstatic.ts`:

```typescript
export async function tvStatic(parent: HTMLElement, durationMs = 900): Promise<void> {
  const canvas = document.createElement("canvas");
  canvas.className = "fx";
  parent.appendChild(canvas);
  const ctx = canvas.getContext("2d")!;
  const start = performance.now();
  return new Promise((resolve) => {
    const tick = (now: number) => {
      const progress = (now - start) / durationMs;
      if (progress >= 1) {
        canvas.remove();
        resolve();
        return;
      }
      canvas.width = 270;
      canvas.height = 480;
      const img = ctx.createImageData(canvas.width, canvas.height);
      const intensity = 255 * (1 - progress); // estabiliza ao longo do tempo
      for (let i = 0; i < img.data.length; i += 4) {
        const v = Math.random() * intensity;
        img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
        img.data[i + 3] = 255;
      }
      ctx.putImageData(img, 0, 0);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}
```

- [ ] **Step 4: Conferir tipos e commitar**

Run: `cd /Users/savio/Project/frontend && npx tsc --noEmit`
Expected: sem erros

```bash
git add frontend/src/fx
git commit -m "feat(web): typewriter, gears and tv-static canvas effects"
```

---

### Task 12: Cliente de API (sessão, upload WS, SSE por fetch)

**Files:**
- Create: `frontend/src/api.ts`

EventSource não envia headers, então o SSE é consumido com `fetch` + parser de stream, mantendo a autenticação por `X-Device-Token`.

- [ ] **Step 1: Implementar**

`frontend/src/api.ts`:

```typescript
const BASE: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const WS_BASE = BASE.replace(/^http/, "ws");

let token = localStorage.getItem("doppel_token") ?? "";

export async function ensureSession(): Promise<void> {
  if (token) return;
  const resp = await fetch(`${BASE}/v1/sessions`, { method: "POST" });
  const body = await resp.json();
  token = body.token;
  localStorage.setItem("doppel_token", token);
}

function authHeaders(): Record<string, string> {
  return { "X-Device-Token": token };
}

export interface AvatarUpload {
  avatarId: Promise<string>;
  finish: () => Promise<void>;
}

export function startAvatarUpload(stream: MediaStream): AvatarUpload {
  const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9")
    ? "video/webm;codecs=vp9"
    : "video/mp4";
  const ws = new WebSocket(`${WS_BASE}/v1/avatars/stream?t=${token}`);
  const recorder = new MediaRecorder(stream, { mimeType: mime });

  let resolveId!: (id: string) => void;
  const avatarId = new Promise<string>((r) => (resolveId = r));
  let resolveDone!: () => void;
  const done = new Promise<void>((r) => (resolveDone = r));

  ws.onopen = () => {
    ws.send(JSON.stringify({ mime }));
    recorder.start(1000); // chunks de 1s: upload durante a leitura
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.avatar_id && msg.status === undefined) resolveId(msg.avatar_id);
    if (msg.status === "processing") {
      ws.close();
      resolveDone();
    }
  };
  recorder.ondataavailable = async (ev) => {
    if (ev.data.size > 0 && ws.readyState === WebSocket.OPEN) {
      ws.send(await ev.data.arrayBuffer());
    }
  };
  recorder.onstop = () => {
    // garante flush do ultimo chunk antes do done
    setTimeout(() => ws.send(JSON.stringify({ done: true })), 300);
  };

  return {
    avatarId,
    finish: () => {
      recorder.stop();
      return done;
    },
  };
}

export type SseHandler = (event: string, data: Record<string, unknown>) => void;

export async function consumeSse(path: string, onEvent: SseHandler): Promise<void> {
  const resp = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let event = "message";
      let data = "{}";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        if (line.startsWith("data: ")) data = line.slice(6);
      }
      onEvent(event, JSON.parse(data));
    }
  }
}

export async function createVideo(avatarId: string, briefing: Blob): Promise<string> {
  const form = new FormData();
  form.append("avatar_id", avatarId);
  form.append("briefing", briefing, "briefing.webm");
  const resp = await fetch(`${BASE}/v1/videos`, {
    method: "POST", headers: authHeaders(), body: form,
  });
  return (await resp.json()).video_id;
}

export async function sendFeedback(
  videoId: string, rating: "up" | "down",
): Promise<{ video_id: string; action: string }> {
  const resp = await fetch(`${BASE}/v1/videos/${videoId}/feedback`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ rating }),
  });
  return resp.json();
}

export interface GalleryItem {
  video_id: string;
  created_at: string;
  fast_url: string;
}

export async function fetchGallery(): Promise<GalleryItem[]> {
  const resp = await fetch(`${BASE}/v1/gallery`, { headers: authHeaders() });
  return (await resp.json()).videos;
}

export async function deleteMe(): Promise<void> {
  await fetch(`${BASE}/v1/me`, { method: "DELETE", headers: authHeaders() });
  localStorage.removeItem("doppel_token");
  token = "";
}
```

- [ ] **Step 2: Conferir tipos e commitar**

Run: `npx tsc --noEmit`
Expected: sem erros

```bash
git add frontend/src/api.ts
git commit -m "feat(web): api client with ws upload and fetch-based sse"
```

---

### Task 13: Cenas e composição (main.ts)

**Files:**
- Create: `frontend/src/scenes/permission.ts`, `reading.ts`, `processing.ts`, `hello.ts`, `briefing.ts`, `generating.ts`, `reveal.ts`, `feedback.ts`, `gallery.ts`
- Create: `frontend/src/main.ts`

Cada cena é `run(ctx) -> Promise<State>`. O contexto compartilhado carrega stream, ids e urls entre cenas. A cena de erro é inline no `main.ts` (8 linhas, não justifica arquivo).

- [ ] **Step 1: Contexto e cenas**

`frontend/src/scenes/permission.ts`:

```typescript
import type { AppCtx } from "../main";
import type { State } from "../machine";

export async function run(ctx: AppCtx): Promise<State> {
  try {
    ctx.stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 540 }, height: { ideal: 960 }, facingMode: "user" },
      audio: true,
    });
    return "reading";
  } catch {
    return "error";
  }
}
```

`frontend/src/scenes/reading.ts`:

```typescript
import { startAvatarUpload } from "../api";
import { typewriter } from "../fx/typewriter";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `<p class="typewriter"></p>`;
  await typewriter(stage.querySelector(".typewriter")!, STR.typewriterIntro);
  await sleep(2500);

  stage.innerHTML = `
    <p><span class="rec-dot"></span></p>
    <p class="reading-text">${STR.readingText}</p>
    <button id="done">${STR.readingDone}</button>`;

  const upload = startAvatarUpload(ctx.stream!);
  ctx.avatarId = await upload.avatarId;

  await new Promise<void>((resolve) => {
    stage.querySelector("#done")!.addEventListener("click", () => resolve(), { once: true });
  });
  await upload.finish();
  ctx.stream!.getTracks().forEach((t) => t.stop());
  ctx.stream = null;
  return "processing";
}
```

`frontend/src/scenes/processing.ts`:

```typescript
import { consumeSse } from "../api";
import { Gears } from "../fx/gears";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  ctx.stage.innerHTML = "";
  const gears = new Gears(ctx.stage);
  gears.setLabel(STR.processing);
  gears.start();
  let failed = false;
  await new Promise<void>((resolve) => {
    consumeSse(`/v1/avatars/${ctx.avatarId}/events`, (event, data) => {
      if (event === "hello_ready") {
        ctx.helloUrl = data.hello_url as string;
        ctx.feedbackUrl = (data.feedback_url as string) ?? null;
        resolve();
      }
      if (event === "failed") { failed = true; resolve(); }
    }).then(resolve);
  });
  gears.stop();
  return failed || !ctx.helloUrl ? "error" : "hello";
}
```

`frontend/src/scenes/hello.ts`:

```typescript
import type { AppCtx } from "../main";
import type { State } from "../machine";

export function playerScene(ctx: AppCtx, url: string): Promise<void> {
  const stage = ctx.stage;
  stage.innerHTML = "";
  const video = document.createElement("video");
  video.className = "player";
  video.src = url;
  video.playsInline = true;
  video.autoplay = true;
  stage.appendChild(video);
  return new Promise((resolve) => {
    video.addEventListener("ended", () => resolve(), { once: true });
    video.addEventListener("error", () => resolve(), { once: true });
  });
}

export async function run(ctx: AppCtx): Promise<State> {
  await playerScene(ctx, ctx.helloUrl!);
  return "briefing";
}
```

`frontend/src/scenes/briefing.ts`:

```typescript
import { createVideo } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `
    <p><span class="rec-dot"></span></p>
    <p class="reading-text">${STR.briefingPrompt}</p>
    <button id="done">${STR.briefingDone}</button>`;

  let audio: MediaStream;
  try {
    audio = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    return "error";
  }
  const recorder = new MediaRecorder(audio);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (ev) => chunks.push(ev.data);
  recorder.start();

  const blob = await new Promise<Blob>((resolve) => {
    stage.querySelector("#done")!.addEventListener("click", () => {
      recorder.onstop = () => resolve(new Blob(chunks, { type: "audio/webm" }));
      recorder.stop();
      audio.getTracks().forEach((t) => t.stop());
    }, { once: true });
  });
  ctx.videoId = await createVideo(ctx.avatarId!, blob);
  return "generating";
}
```

`frontend/src/scenes/generating.ts`:

```typescript
import { consumeSse } from "../api";
import { Gears } from "../fx/gears";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  ctx.stage.innerHTML = "";
  const gears = new Gears(ctx.stage);
  gears.setLabel(STR.generatingSteps.scripting);
  gears.start();
  let failed = false;
  await new Promise<void>((resolve) => {
    consumeSse(`/v1/videos/${ctx.videoId}/events`, (event, data) => {
      if (event === "progress") {
        const step = data.step as string;
        gears.setLabel(STR.generatingSteps[step] ?? step);
      }
      if (event === "status" && data.fast_url) {
        ctx.fastUrl = data.fast_url as string;
        resolve();
      }
      if (event === "fast_ready") {
        ctx.fastUrl = data.fast_url as string;
        resolve();
      }
      if (event === "failed") { failed = true; resolve(); }
    }).then(resolve);
  });
  gears.stop();
  return failed || !ctx.fastUrl ? "error" : "reveal";
}
```

`frontend/src/scenes/reveal.ts`:

```typescript
import { tvStatic } from "../fx/tvstatic";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { playerScene } from "./hello";

export async function run(ctx: AppCtx): Promise<State> {
  ctx.stage.innerHTML = "";
  await tvStatic(ctx.stage, 900);
  await playerScene(ctx, ctx.fastUrl!);
  return "feedback";
}
```

`frontend/src/scenes/feedback.ts`:

```typescript
import { sendFeedback } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";
import { playerScene } from "./hello";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  stage.innerHTML = `
    <div class="row">
      <button id="up">${STR.thumbsUp}</button>
      <button id="down">${STR.thumbsDown}</button>
    </div>`;
  const rating = await new Promise<"up" | "down">((resolve) => {
    stage.querySelector("#up")!.addEventListener("click", () => resolve("up"), { once: true });
    stage.querySelector("#down")!.addEventListener("click", () => resolve("down"), { once: true });
  });
  const result = await sendFeedback(ctx.videoId!, rating);
  if (rating === "up") return "gallery";
  if (ctx.feedbackUrl) await playerScene(ctx, ctx.feedbackUrl);
  ctx.videoId = result.video_id; // novo video da regeneracao
  return "generating";
}
```

`frontend/src/scenes/gallery.ts`:

```typescript
import { deleteMe, fetchGallery } from "../api";
import type { AppCtx } from "../main";
import type { State } from "../machine";
import { STR } from "../strings";

export async function run(ctx: AppCtx): Promise<State> {
  const stage = ctx.stage;
  const items = await fetchGallery();
  stage.innerHTML = `
    <div class="gallery-grid">
      ${items.map((i) => `<video src="${i.fast_url}" controls playsinline></video>`).join("")}
    </div>
    <div class="row">
      ${ctx.avatarId ? `<button id="new">${STR.newVideo}</button>` : ""}
      <button id="del">${STR.deleteMe}</button>
    </div>`;
  return new Promise<State>((resolve) => {
    stage.querySelector("#new")?.addEventListener("click", () => resolve("briefing"), { once: true });
    stage.querySelector("#del")!.addEventListener("click", async () => {
      await deleteMe();
      ctx.avatarId = null;
      resolve("idle");
    }, { once: true });
  });
}
```

- [ ] **Step 2: main.ts**

`frontend/src/main.ts`:

```typescript
import "./style.css";
import { ensureSession } from "./api";
import { Machine, type State } from "./machine";
import { STR } from "./strings";
import * as briefing from "./scenes/briefing";
import * as feedback from "./scenes/feedback";
import * as gallery from "./scenes/gallery";
import * as generating from "./scenes/generating";
import * as hello from "./scenes/hello";
import * as permission from "./scenes/permission";
import * as processing from "./scenes/processing";
import * as reading from "./scenes/reading";
import * as reveal from "./scenes/reveal";

export interface AppCtx {
  stage: HTMLElement;
  stream: MediaStream | null;
  avatarId: string | null;
  videoId: string | null;
  helloUrl: string | null;
  feedbackUrl: string | null;
  fastUrl: string | null;
}

const stage = document.getElementById("stage")!;
const ctx: AppCtx = {
  stage, stream: null, avatarId: null, videoId: null,
  helloUrl: null, feedbackUrl: null, fastUrl: null,
};

async function idleScene(): Promise<State> {
  stage.innerHTML = `
    <h1>doppel</h1>
    <div class="row">
      <button id="start">${STR.start}</button>
      <button id="gal">${STR.galleryLink}</button>
    </div>`;
  return new Promise((resolve) => {
    stage.querySelector("#start")!.addEventListener("click", () => resolve("permission"), { once: true });
    stage.querySelector("#gal")!.addEventListener("click", () => resolve("gallery"), { once: true });
  });
}

async function errorScene(): Promise<State> {
  stage.innerHTML = `
    <p class="reading-text">${STR.genericError}</p>
    <button id="retry">${STR.retry}</button>`;
  return new Promise((resolve) => {
    stage.querySelector("#retry")!.addEventListener("click", () => resolve("idle"), { once: true });
  });
}

const SCENES: Record<State, (ctx: AppCtx) => Promise<State>> = {
  idle: idleScene,
  permission: permission.run,
  reading: reading.run,
  processing: processing.run,
  hello: hello.run,
  briefing: briefing.run,
  generating: generating.run,
  reveal: reveal.run,
  feedback: feedback.run,
  gallery: gallery.run,
  error: errorScene,
};

async function fadeTo(next: () => Promise<State>): Promise<State> {
  stage.classList.add("faded");
  await new Promise((r) => setTimeout(r, 600));
  stage.classList.remove("faded");
  return next();
}

async function loop(): Promise<void> {
  await ensureSession();
  const machine = new Machine();
  for (;;) {
    const scene = SCENES[machine.state];
    const next = await fadeTo(() => scene(ctx));
    machine.go(next);
  }
}

loop();
```

- [ ] **Step 3: Tipos e testes**

Run: `npx tsc --noEmit && npm test`
Expected: sem erros, `4 passed`

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "feat(web): full scene flow wired to the state machine"
```

---

### Task 14: Smoke E2E manual (critério de aceite do M0)

**Files:**
- Create: `docs/m0-smoke-checklist.md`

- [ ] **Step 1: Subir tudo**

```bash
cd /Users/savio/Project && docker compose up -d --build
cd frontend && npm run dev
```

- [ ] **Step 2: Executar o roteiro no browser (Chrome, http://localhost:5173)**

Criar `docs/m0-smoke-checklist.md` com o roteiro e marcar cada item ao validar:

```markdown
# M0 Smoke Checklist

- [ ] Tela inicial "doppel" com botões Começar e Galeria
- [ ] Começar pede camera/mic; negar leva à cena de erro com Recomeçar
- [ ] Permitir: fade para preto, typewriter "Agora leia em voz alta..."
- [ ] Texto de leitura aparece com REC piscando; upload corre durante a leitura
      (verificar no Network: frames WS a cada ~1s)
- [ ] "Terminei a leitura": engrenagens girando com label
- [ ] Em ~5-15s o hello stub (6s, "HELLO") toca sozinho
- [ ] Ao fim do hello, prompt de briefing com REC; falar e clicar Pronto
- [ ] Engrenagens com steps trocando (roteiro, cena 1/2/3)
- [ ] TV static estabiliza e o vídeo de 30s ("DOPPEL FAST STUB") toca
- [ ] Thumbs down: vídeo FEEDBACK toca, gera de novo, novo reveal
- [ ] Thumbs up: galeria mostra o vídeo com controls
- [ ] Criar outro vídeo: volta ao briefing sem regravar avatar
- [ ] Apagar meus dados: volta ao início; galeria vazia (token novo)
- [ ] Recarregar a página no meio: volta ao idle sem erro de console
```

- [ ] **Step 3: Corrigir o que falhar no roteiro** (bugs de integração são esperados aqui; corrigir e re-rodar a suíte `uv run pytest -q` + `npm test`)

- [ ] **Step 4: Commit final do M0**

```bash
git add docs/m0-smoke-checklist.md
git commit -m "docs: M0 smoke checklist executed - walking skeleton complete"
```

---

## Self-review do plano (executado na escrita)

1. **Cobertura do spec (M0)**: experiência completa navegável (Tasks 10-14), compose managed + floci (Task 9), fluxo com stubs (Tasks 7-8), state machine com todas as cenas do PDR seção 2 (Task 10/13). Métricas north star e validação de rosto ficam para M1 conforme decisões de escopo declaradas no topo.
2. **Placeholders**: nenhum TBD/TODO; todo step de código tem o código.
3. **Consistência de tipos**: `WorkerContext`/`process_one` (Task 7) usados no teste da mesma task; `AppCtx` definido em main.ts e importado pelas cenas; eventos `hello_ready {hello_url, feedback_url}`, `fast_ready {fast_url}`, `progress {step}` consistentes entre worker (Task 7), rotas SSE (Tasks 6/8) e cenas (Task 13).

