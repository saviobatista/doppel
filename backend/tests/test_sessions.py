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


async def test_auth_rejects_unknown_token(client):
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": "nope"})
    assert resp.status_code == 401


async def test_auth_rejects_deleted_device(app, client, device_token):
    from datetime import UTC, datetime

    from sqlalchemy import select

    from doppel_api.models import Device

    async with app.state.session_factory() as s:
        device = (await s.execute(select(Device))).scalar_one()
        device.deleted_at = datetime.now(UTC)
        await s.commit()
    resp = await client.get("/v1/gallery", headers={"X-Device-Token": device_token})
    assert resp.status_code == 401
