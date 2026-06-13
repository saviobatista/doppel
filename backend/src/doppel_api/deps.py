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
        raise HTTPException(status_code=401, detail="missing token",
                            headers={"WWW-Authenticate": "X-Device-Token"})
    result = await session.execute(
        select(Device).where(Device.token == x_device_token, Device.deleted_at.is_(None))
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=401, detail="invalid token",
                            headers={"WWW-Authenticate": "X-Device-Token"})
    return device
