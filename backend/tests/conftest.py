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
