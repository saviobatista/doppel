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
