"""A-101: router 404/405s and unhandled errors use the {"error": {...}} envelope, not plain text."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_unknown_route_is_enveloped(client):
    r = client.get("/v1/no-such-route")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_wrong_method_is_enveloped_with_allow(client):
    r = client.delete("/v1/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in r.headers["allow"]


def test_unhandled_error_is_enveloped():
    app = create_app()

    @app.get("/v1/boom")
    async def boom():
        raise RuntimeError("secret internals")

    r = TestClient(app, raise_server_exceptions=False).get("/v1/boom")
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "internal_error"
    assert "deployer logs api" in err["message"]
    assert "secret" not in r.text
