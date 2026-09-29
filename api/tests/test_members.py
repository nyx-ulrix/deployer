from datetime import timedelta

import pytest

from app.deps import load_api_key_access
from app.models import AuditLog, ProjectInvite, ProjectMember, utcnow
from app.services import invites


@pytest.fixture
def team(owner, make_user, make_project):
    users = {
        "owner": owner,
        "admin": make_user("admin@example.com", display_name="Admin"),
        "admin2": make_user("admin2@example.com"),
        "dev": make_user("dev@example.com"),
        "viewer": make_user("viewer@example.com"),
    }
    project = make_project(
        owner,
        members={
            users["admin"]: "admin",
            users["admin2"]: "admin",
            users["dev"]: "developer",
            users["viewer"]: "viewer",
        },
    )
    return project, users


def test_list_members(client, team, auth_headers):
    project, users = team
    resp = client.get(f"/v1/projects/{project.id}/members", headers=auth_headers(users["viewer"]))
    assert resp.status_code == 200
    members = resp.json()
    assert [m["role"] for m in members] == ["owner", "admin", "admin", "developer", "viewer"]
    assert set(members[0]) == {"user_id", "email", "display_name", "avatar_url", "role", "can_cohost", "created_at"}


def test_change_role_rules(client, team, auth_headers, db):
    project, users = team
    base = f"/v1/projects/{project.id}/members"

    def patch(actor, target, role):
        return client.patch(f"{base}/{users[target].id}", json={"role": role}, headers=auth_headers(users[actor]))

    assert patch("dev", "viewer", "developer").status_code == 403
    assert patch("admin", "owner", "viewer").status_code == 403
    assert patch("owner", "owner", "admin").status_code == 403
    assert patch("owner", "dev", "owner").status_code == 422
    assert patch("admin", "admin2", "viewer").status_code == 403  # admins can't change other admins

    resp = patch("admin", "viewer", "developer")
    assert resp.status_code == 200
    assert resp.json()["role"] == "developer"
    assert patch("admin", "dev", "admin").status_code == 200
    assert patch("owner", "admin2", "viewer").status_code == 200
    assert patch("admin", "admin", "developer").status_code == 200  # self-demotion
    assert (
        client.patch(f"{base}/nobody", json={"role": "viewer"}, headers=auth_headers(users["owner"])).status_code == 404
    )
    assert db.query(AuditLog).filter_by(action="member.role_change").count() == 4


def test_remove_member_rules(client, team, auth_headers, db):
    project, users = team
    base = f"/v1/projects/{project.id}/members"

    def remove(actor, target):
        return client.delete(f"{base}/{users[target].id}", headers=auth_headers(users[actor]))

    assert remove("dev", "viewer").status_code == 403
    assert remove("admin", "owner").status_code == 403
    assert remove("owner", "owner").status_code == 403
    assert remove("admin", "admin2").status_code == 403
    assert remove("viewer", "viewer").status_code == 200  # self
    assert remove("admin", "dev").status_code == 200
    assert remove("owner", "admin2").status_code == 200
    assert remove("dev", "dev").status_code == 404  # no longer a member
    remaining = {m.user_id for m in db.query(ProjectMember).filter_by(project_id=project.id)}
    assert remaining == {users["owner"].id, users["admin"].id}
    assert db.query(AuditLog).filter_by(action="member.remove").count() == 3


def test_invite_lifecycle(client, team, auth_headers, make_user, db):
    project, users = team
    base = f"/v1/projects/{project.id}/invites"
    admin_h = auth_headers(users["admin"])

    assert client.post(base, json={"role": "viewer"}, headers=auth_headers(users["dev"])).status_code == 403
    assert client.post(base, json={"role": "owner"}, headers=admin_h).status_code == 422
    assert client.post(base, json={"role": "viewer", "expires_in_days": 31}, headers=admin_h).status_code == 422
    assert client.post(base, json={"role": "viewer", "expires_in_days": 0}, headers=admin_h).status_code == 422

    resp = client.post(base, json={"role": "developer", "email": "", "expires_in_days": 3}, headers=admin_h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    invite = body["invite"]
    assert invite["email"] is None and invite["role"] == "developer" and invite["invited_by"] == users["admin"].id
    assert body["invite_url"].startswith("http://localhost:8080/invite/")
    token = body["invite_url"].rsplit("/", 1)[1]
    stored = db.get(ProjectInvite, invite["id"])
    assert stored.token_hash != token and len(stored.token_hash) == 64

    listed = client.get(base, headers=admin_h).json()
    assert [i["id"] for i in listed] == [invite["id"]]
    assert "token" not in listed[0]

    public = client.get(f"/v1/invites/{token}")
    assert public.status_code == 200
    assert public.json()["project_name"] == project.name
    assert public.json()["invited_by_name"] == "Admin"
    assert public.json()["role"] == "developer"

    newcomer = make_user("newcomer@example.com")
    assert client.post(f"/v1/invites/{token}/accept").status_code == 401
    resp = client.post(f"/v1/invites/{token}/accept", headers=auth_headers(newcomer))
    assert resp.status_code == 200
    assert resp.json() == {"project_id": project.id}
    member = db.query(ProjectMember).filter_by(project_id=project.id, user_id=newcomer.id).one()
    assert member.role == "developer"

    # Single use.
    assert client.get(f"/v1/invites/{token}").status_code == 404
    other = make_user()
    assert client.post(f"/v1/invites/{token}/accept", headers=auth_headers(other)).status_code == 404
    assert client.get(base, headers=admin_h).json() == []
    assert db.query(AuditLog).filter_by(action="invite.create").count() == 1
    assert db.query(AuditLog).filter_by(action="invite.accept").count() == 1


@pytest.mark.parametrize(
    ("url", "reachable"),
    [
        (None, False),
        ("http://127.0.0.1:8080", False),
        ("http://deployer.localhost", False),
        ("http://192.168.1.20:8080", True),
        ("https://deployer.example.com", True),
    ],
)
def test_invite_says_whether_the_link_opens_elsewhere(client, team, auth_headers, set_setting, url, reachable):
    """A-020: a localhost public URL makes invite links (and API snippets) that only open on this PC."""
    project, users = team
    if url:
        set_setting("public_url", url)
    resp = client.post(
        f"/v1/projects/{project.id}/invites", json={"role": "viewer"}, headers=auth_headers(users["owner"])
    )
    assert resp.json()["reachable_elsewhere"] is reachable
    assert client.get("/v1/setup/status").json()["reachable_elsewhere"] is reachable


def test_invite_email_lock(client, team, auth_headers, make_user):
    project, users = team
    resp = client.post(
        f"/v1/projects/{project.id}/invites",
        json={"role": "viewer", "email": "Locked@Example.com"},
        headers=auth_headers(users["owner"]),
    )
    token = resp.json()["invite_url"].rsplit("/", 1)[1]
    assert resp.json()["invite"]["email"] == "locked@example.com"
    wrong = make_user("wrong@example.com")
    resp = client.post(f"/v1/invites/{token}/accept", headers=auth_headers(wrong))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "invite_email_mismatch"
    right = make_user("locked@example.com")
    assert client.post(f"/v1/invites/{token}/accept", headers=auth_headers(right)).status_code == 200


def test_accept_when_already_member_keeps_role(client, team, auth_headers, db):
    project, users = team
    invite, token = invites.create_invite(db, project=project, inviter=users["owner"], role="viewer")
    db.commit()
    resp = client.post(f"/v1/invites/{token}/accept", headers=auth_headers(users["admin"]))
    assert resp.json() == {"project_id": project.id}
    db.expire_all()
    assert db.query(ProjectMember).filter_by(project_id=project.id, user_id=users["admin"].id).one().role == "admin"


def test_revoke_and_expired_invites(client, team, auth_headers, db):
    project, users = team
    h = auth_headers(users["admin"])
    invite, token = invites.create_invite(db, project=project, inviter=users["owner"], role="viewer")
    expired, expired_token = invites.create_invite(db, project=project, inviter=users["owner"], role="viewer")
    expired.expires_at = utcnow() - timedelta(minutes=1)
    db.commit()

    assert client.get(f"/v1/invites/{expired_token}").status_code == 404
    assert [i["id"] for i in client.get(f"/v1/projects/{project.id}/invites", headers=h).json()] == [invite.id]

    resp = client.delete(f"/v1/projects/{project.id}/invites/{invite.id}", headers=h)
    assert resp.status_code == 200
    assert client.get(f"/v1/invites/{token}").status_code == 404
    assert client.delete(f"/v1/projects/{project.id}/invites/nope", headers=h).status_code == 404
    assert client.get(f"/v1/projects/{project.id}/invites", headers=h).json() == []
    assert db.query(AuditLog).filter_by(action="invite.revoke").count() == 1


def test_invite_other_project_not_found(client, team, auth_headers, make_project, db):
    project, users = team
    other = make_project(users["owner"], "Other")
    invite, _ = invites.create_invite(db, project=other, inviter=users["owner"], role="viewer")
    db.commit()
    resp = client.delete(f"/v1/projects/{project.id}/invites/{invite.id}", headers=auth_headers(users["owner"]))
    assert resp.status_code == 404


def test_remove_or_demote_lists_keys_to_rotate(client, team, auth_headers, make_user, db):
    # A-024: a removed or demoted admin's keys keep working, so the API names them for revoking.
    project, users = team
    keys = f"/v1/projects/{project.id}/api-keys"

    def make_key(actor, name):
        resp = client.post(keys, json={"name": name, "role": "service"}, headers=auth_headers(users[actor]))
        return resp.json()["api_key"]["id"]

    admins_key, owners_key, _other = make_key("admin", "a"), make_key("owner", "b"), make_key("owner", "c")
    assert client.get(f"{keys}/{owners_key}/reveal", headers=auth_headers(users["admin"])).status_code == 200
    admin2s_key = make_key("admin2", "d")

    demote = client.patch(
        f"/v1/projects/{project.id}/members/{users['admin2'].id}",
        json={"role": "developer"},
        headers=auth_headers(users["owner"]),
    )
    assert [k["id"] for k in demote.json()["api_keys_to_rotate"]] == [admin2s_key]
    promote = client.patch(
        f"/v1/projects/{project.id}/members/{users['dev'].id}",
        json={"role": "admin"},
        headers=auth_headers(users["owner"]),
    )
    assert promote.json()["api_keys_to_rotate"] == []

    removed = client.delete(
        f"/v1/projects/{project.id}/members/{users['admin'].id}", headers=auth_headers(users["owner"])
    )
    assert removed.status_code == 200
    assert {k["id"] for k in removed.json()["api_keys_to_rotate"]} == {admins_key, owners_key}


def test_key_of_a_removed_member_acts_as_the_owner(client, team, auth_headers, db):
    # A-024: the audit trail must not credit someone who is no longer in the project.
    project, users = team
    resp = client.post(
        f"/v1/projects/{project.id}/api-keys",
        json={"name": "k", "role": "service"},
        headers=auth_headers(users["admin"]),
    )
    secret = resp.json()["secret"]
    client.delete(f"/v1/projects/{project.id}/members/{users['admin'].id}", headers=auth_headers(users["owner"]))
    assert load_api_key_access(db, secret, project.id).user.id == users["owner"].id
