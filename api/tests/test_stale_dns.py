"""Stale tunnel DNS records (docs/REMOTE_ACCESS.md step 6) against the fake Cloudflare API."""

import pytest

from app.models import AuditLog, Domain
from app.services import cloudflare as cf
from tests.test_remote_access import BASE, add_host, link

STALE = f"{BASE}/cloudflare/stale-records"


def stale(client, headers):
    resp = client.get(STALE, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["records"]


def delete(client, headers, ids):
    return client.post(f"{STALE}/delete", json={"record_ids": ids}, headers=headers)


@pytest.fixture
def linked(client, owner_headers, fake_cf, set_setting):
    """Linked account with one active hostname, a second zone and an apps tunnel id."""
    tunnel_id = link(client, owner_headers)["cloudflare"]["tunnel"]["id"]
    fake_cf.zones.append({"id": "zone2", "name": "other.org", "status": "active", "account": {"id": "acc1"}})
    set_setting("cloudflare_apps_tunnel_id", "apps-tunnel-1")
    assert add_host(client, owner_headers, "live.example.com").status_code == 200
    return tunnel_id


def test_lists_only_unknown_tunnel_cnames(client, owner_headers, fake_cf, linked):
    target = cf.tunnel_cname_target(linked)
    gone = fake_cf.add_record("gone.example.com", "CNAME", target)
    apps = fake_cf.add_record("old-app.other.org", "CNAME", "apps-tunnel-1.cfargotunnel.com.", zone_id="zone2")
    fake_cf.add_record("elsewhere.example.com", "CNAME", "somewhere.else.net")  # not ours
    fake_cf.add_record("a-record.example.com", "A", "192.0.2.1")
    fake_cf.add_record("foreign.example.com", "CNAME", "other-tunnel.cfargotunnel.com")
    # A second record for a known hostname is not stale either.
    fake_cf.add_record("LIVE.example.com", "CNAME", target)

    records = stale(client, owner_headers)
    assert records == [
        {
            "zone_id": "zone1",
            "zone_name": "example.com",
            "record_id": gone,
            "hostname": "gone.example.com",
            "target": target,
        },
        {
            "zone_id": "zone2",
            "zone_name": "other.org",
            "record_id": apps,
            "hostname": "old-app.other.org",
            "target": "apps-tunnel-1.cfargotunnel.com",
        },
    ]
    # Listing changes nothing.
    assert fake_cf.calls("DELETE") == []


def test_delete_rechecks_and_skips_records_that_are_no_longer_stale(client, owner_headers, fake_cf, linked, db):
    target = cf.tunnel_cname_target(linked)
    gone = fake_cf.add_record("gone.example.com", "CNAME", target)
    revived = fake_cf.add_record("revived.example.com", "CNAME", target)
    repointed = fake_cf.add_record("repointed.example.com", "CNAME", target)
    elsewhere = fake_cf.add_record("elsewhere.example.com", "CNAME", "somewhere.else.net")
    live_id = db.query(Domain).filter_by(hostname="live.example.com").one().dns_record_id
    assert {r["record_id"] for r in stale(client, owner_headers)} == {gone, revived, repointed}

    # Between the listing and the delete: one hostname is known again, one record now points elsewhere.
    db.add(Domain(hostname="revived.example.com", provider="cloudflare", zone_id="zone1", status="active"))
    db.commit()
    fake_cf.records[repointed]["content"] = "somewhere.else.net"

    resp = delete(client, owner_headers, [gone, revived, repointed, elsewhere, live_id, "nope", gone])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [d["record_id"] for d in body["deleted"]] == [gone]
    assert body["skipped"] == [
        {"record_id": rid, "reason": "not_stale"} for rid in (revived, repointed, elsewhere, live_id, "nope")
    ]
    assert gone not in fake_cf.records
    for rid in (revived, repointed, elsewhere, live_id):
        assert rid in fake_cf.records
    assert len(fake_cf.calls("DELETE", r"/dns_records/")) == 1

    audit = db.query(AuditLog).filter_by(action="remote_access.stale_dns_delete").one()
    assert audit.details == {"hostnames": ["gone.example.com"]}


def test_delete_reports_a_record_that_vanished(client, owner_headers, fake_cf, linked, monkeypatch):
    gone = fake_cf.add_record("gone.example.com", "CNAME", cf.tunnel_cname_target(linked))
    real = cf.CloudflareClient.delete_dns_record

    def vanish(self, zone_id, record_id):
        fake_cf.records.pop(record_id, None)  # deleted by someone else in the meantime
        return real(self, zone_id, record_id)

    monkeypatch.setattr(cf.CloudflareClient, "delete_dns_record", vanish)
    body = delete(client, owner_headers, [gone]).json()
    assert body == {
        "deleted": [],
        "skipped": [{"record_id": gone, "hostname": "gone.example.com", "reason": "not_found"}],
    }


def test_cloudflare_errors_are_mapped(client, owner_headers, fake_cf, linked):
    fake_cf.forbidden = [r"/dns_records"]
    resp = client.get(STALE, headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (400, "cloudflare_permission_missing")
    assert resp.json()["error"]["details"]["missing_permissions"] == [cf.PERM_DNS]


def test_not_linked(client, owner_headers, fake_cf):
    resp = client.get(STALE, headers=owner_headers)
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "not_linked")
    resp = delete(client, owner_headers, ["abc"])
    assert (resp.status_code, resp.json()["error"]["code"]) == (409, "not_linked")
    assert fake_cf.requests == []


def test_non_owner_forbidden(client, make_user, auth_headers, fake_cf):
    headers = auth_headers(make_user())
    assert client.get(STALE, headers=headers).status_code == 403
    assert delete(client, headers, ["abc"]).status_code == 403
    assert fake_cf.requests == []


@pytest.mark.parametrize("ids", [[], ["x"] * 101, [""]])
def test_delete_validates_record_ids(client, owner_headers, fake_cf, ids):
    assert delete(client, owner_headers, ids).status_code == 422
