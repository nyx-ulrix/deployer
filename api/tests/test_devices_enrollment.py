"""Device enrollment (device authorization flow) and device-token authentication."""

import re
from datetime import timedelta

from sqlalchemy import select

from app.models import Device, DeviceEnrollment, utcnow
from app.services import device_rpc, devices

ENROLL = {
    "name": "Home PC",
    "hostname": "home-pc",
    "os": "Linux 6",
    "version": "0.1.0",
    "capabilities": {"engines": {"mariadb": True, "mongodb": False}},
}


def _enroll(client):
    resp = client.post("/v1/devices/enrollments", json=ENROLL)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _allow_poll(fake_redis, enrollment_id):
    fake_redis.delete(f"device:enroll:poll:{enrollment_id}")


def test_user_code_format():
    for _ in range(200):
        code = devices.generate_user_code()
        assert re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", code)
        assert not set(code) & set("01OI")
    assert devices.normalize_user_code("abcd efgh") == "ABCD-EFGH"
    assert devices.normalize_user_code("ABCD-EFG0") is None
    assert devices.normalize_user_code("ABC") is None


def test_full_enrollment_flow(client, db, owner, owner_headers, fake_redis):
    data = _enroll(client)
    assert data["expires_in"] == 900
    assert data["verification_uri"].endswith(f"/devices/approve?code={data['user_code']}")
    eid, secret = data["enrollment_id"], data["poll_secret"]

    resp = client.post(f"/v1/devices/enrollments/{eid}/poll", json={"poll_secret": secret})
    assert resp.json()["status"] == "pending"
    resp = client.post(f"/v1/devices/enrollments/{eid}/poll", json={"poll_secret": secret})
    assert resp.status_code == 429 and resp.json()["error"]["code"] == "slow_down"
    _allow_poll(fake_redis, eid)
    assert client.post(f"/v1/devices/enrollments/{eid}/poll", json={"poll_secret": "wrong"}).status_code == 404

    # Lookup requires a signed-in user.
    assert client.get("/v1/devices/enrollments", params={"code": data["user_code"]}).status_code == 401
    code = data["user_code"].lower().replace("-", "")
    resp = client.get("/v1/devices/enrollments", params={"code": code}, headers=owner_headers)
    assert resp.status_code == 200 and resp.json()["name"] == "Home PC"
    resp = client.get(f"/v1/devices/enrollments/by-code/{data['user_code']}", headers=owner_headers)
    assert resp.json()["id"] == eid

    # Wrong code for the id is rejected.
    resp = client.post(f"/v1/devices/enrollments/{eid}/approve", json={"user_code": "AAAA-AAAA"}, headers=owner_headers)
    assert resp.status_code == 404
    resp = client.post(
        f"/v1/devices/enrollments/{eid}/approve",
        json={"user_code": data["user_code"], "name": "Office", "roles": ["database_host", "backup_storage"]},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    device = resp.json()
    assert device["name"] == "Office" and device["owner_id"] == owner.id and device["online"] is False
    assert device["roles"] == ["database_host", "backup_storage"]

    # Single use.
    resp = client.post(f"/v1/devices/enrollments/{eid}/approve", json={}, headers=owner_headers)
    assert resp.status_code == 409

    _allow_poll(fake_redis, eid)
    resp = client.post(f"/v1/devices/enrollments/{eid}/poll", json={"poll_secret": secret})
    body = resp.json()
    assert body["status"] == "approved" and body["device_id"] == device["id"]
    token = body["device_token"]
    assert token.startswith("dpd_")
    db.expire_all()
    stored = db.get(Device, device["id"])
    assert stored.token_hash == devices.hash_token(token) and token not in stored.token_hash
    row = db.get(DeviceEnrollment, eid)
    assert row.status == "consumed" and row.device_token_encrypted is None

    # Token delivered only once.
    _allow_poll(fake_redis, eid)
    body = client.post(f"/v1/devices/enrollments/{eid}/poll", json={"poll_secret": secret}).json()
    assert body["status"] == "consumed" and "device_token" not in body


def test_device_token_does_not_work_on_user_endpoints(client, db, owner, owner_headers, fake_redis):
    data = _enroll(client)
    client.post(f"/v1/devices/enrollments/{data['enrollment_id']}/approve", json={}, headers=owner_headers)
    _allow_poll(fake_redis, data["enrollment_id"])
    token = client.post(
        f"/v1/devices/enrollments/{data['enrollment_id']}/poll", json={"poll_secret": data["poll_secret"]}
    ).json()["device_token"]
    for header in (f"Device {token}", f"Bearer {token}"):
        assert client.get("/v1/devices", headers={"Authorization": header}).status_code == 401
        assert client.get("/v1/projects", headers={"Authorization": header}).status_code == 401
    # ...and user tokens don't work on device endpoints.
    tid = device_rpc.create_transfer(db.scalars(select(Device.id)).first(), "put")
    assert client.put(f"/v1/devices/transfers/{tid}", content=b"x", headers=owner_headers).status_code == 401
    device_headers = {"Authorization": f"Device {token}"}
    assert client.put(f"/v1/devices/transfers/{tid}", content=b"x", headers=device_headers).status_code == 200


def test_deny_and_expiry(client, db, owner, owner_headers, fake_redis):
    data = _enroll(client)
    resp = client.post(
        f"/v1/devices/enrollments/{data['enrollment_id']}/deny",
        json={"user_code": data["user_code"]},
        headers=owner_headers,
    )
    assert resp.status_code == 200
    body = client.post(
        f"/v1/devices/enrollments/{data['enrollment_id']}/poll", json={"poll_secret": data["poll_secret"]}
    ).json()
    assert body["status"] == "denied" and "device_token" not in body

    data = _enroll(client)
    row = db.get(DeviceEnrollment, data["enrollment_id"])
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    resp = client.post(f"/v1/devices/enrollments/{data['enrollment_id']}/approve", json={}, headers=owner_headers)
    assert resp.status_code == 409
    body = client.post(
        f"/v1/devices/enrollments/{data['enrollment_id']}/poll", json={"poll_secret": data["poll_secret"]}
    ).json()
    assert body["status"] == "expired"


def test_approve_selected_projects(client, db, make_user, make_project, auth_headers):
    user = make_user()
    other = make_user()
    mine = make_project(user, "Mine")
    theirs = make_project(other, "Theirs")
    data = _enroll(client)
    resp = client.post(
        f"/v1/devices/enrollments/{data['enrollment_id']}/approve",
        json={"sharing_mode": "selected", "project_ids": [theirs.id]},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422
    resp = client.post(
        f"/v1/devices/enrollments/{data['enrollment_id']}/approve",
        json={"sharing_mode": "selected", "project_ids": [mine.id]},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["project_ids"] == [mine.id]


def test_enrollment_rate_limit(client):
    for _ in range(20):
        assert client.post("/v1/devices/enrollments", json=ENROLL).status_code == 200
    assert client.post("/v1/devices/enrollments", json=ENROLL).status_code == 429
