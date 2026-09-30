"""A-102: the audit log and refresh tokens are pruned, and the owner can read the audit log."""

from datetime import timedelta

from sqlalchemy import select

from app.models import AuditLog, RefreshToken, utcnow
from app.services import audit


def test_prune(db, owner):
    now = utcnow()
    for days, action in ((0, "auth.login"), (91, "auth.login"), (91, "api_key.reveal"), (91, "instance.export")):
        db.add(AuditLog(action=action, created_at=now - timedelta(days=days)))
    for n, expires in enumerate((now + timedelta(days=5), now - timedelta(hours=2), now - timedelta(days=2))):
        db.add(RefreshToken(user_id=owner.id, token_hash=f"{n:064d}", family_id="f", expires_at=expires))
    db.commit()

    assert audit.prune(db, now) == 2
    db.commit()
    kept = sorted(db.scalars(select(AuditLog.action)))
    assert kept == ["api_key.reveal", "auth.login", "instance.export"]
    assert len(db.scalars(select(RefreshToken)).all()) == 2  # live + expired less than a day ago
    assert audit.prune(db, now) == 0


def test_owner_reads_audit_log(client, owner, owner_headers, make_user, auth_headers):
    client.post("/v1/auth/login", json={"email": owner.email, "password": "wrong-password-1"})
    client.post("/v1/auth/login", json={"email": owner.email, "password": "wrong-password-2"})
    assert client.get("/v1/instance/audit", headers=auth_headers(make_user())).status_code == 403

    rows = client.get("/v1/instance/audit", headers=owner_headers).json()
    assert [r["action"] for r in rows] == ["auth.login_failed", "auth.login_failed"]
    assert rows[0]["user_email"] == owner.email and rows[0]["id"] > rows[1]["id"]

    page = client.get(f"/v1/instance/audit?before={rows[0]['id']}&limit=5", headers=owner_headers).json()
    assert [r["id"] for r in page] == [rows[1]["id"]]
    assert client.get("/v1/instance/audit?action=auth.login", headers=owner_headers).json() == []
