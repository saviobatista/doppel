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
