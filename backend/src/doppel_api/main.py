from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from doppel_api.config import get_settings
from doppel_api.db import init_db, make_engine, make_session_factory
from doppel_api.deps import get_device
from doppel_api.models import Device
from doppel_api.routes import sessions
from doppel_api.storage import S3Storage, Storage


def create_app(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
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
