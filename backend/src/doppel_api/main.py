from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.db import make_engine, make_session_factory
from doppel_api.routes import avatars, plans, sessions, videos, voices
from doppel_api.storage import S3Storage, Storage


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    storage: Storage | None = None,
    redis=None,
    run_startup: bool = True,
) -> FastAPI:
    """App factory. Injected deps are for tests and only honored with run_startup=False;
    with run_startup=True the lifespan wires real deps and overwrites app.state."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = None
        if run_startup:
            engine = make_engine()
            app.state.session_factory = make_session_factory(engine)
            app.state.storage = S3Storage(settings)
            app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await app.state.storage.ensure_bucket()
        yield
        if engine is not None:
            await app.state.redis.aclose()
            await engine.dispose()

    app = FastAPI(title="doppel-api", lifespan=lifespan)
    if session_factory is not None:
        app.state.session_factory = session_factory
    if storage is not None:
        app.state.storage = storage
    if redis is not None:
        app.state.redis = redis

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sessions.router)
    app.include_router(avatars.router)
    app.include_router(videos.router)
    app.include_router(plans.router)
    app.include_router(voices.router)

    return app
