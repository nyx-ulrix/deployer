"""A-153: container settings have one source of truth (compose / Caddy), not repeats in the images."""

import re
from pathlib import Path

import yaml

from app import shell_runner

ROOT = Path(__file__).resolve().parents[2]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_api_healthcheck_and_backup_dir_live_in_compose_only():
    dockerfile = read("api/Dockerfile")
    assert "HEALTHCHECK" not in dockerfile
    assert "ENV BACKUP_DIR" not in dockerfile
    compose = read("deploy/docker-compose.yml")
    assert "BACKUP_DIR: /backups" in compose
    assert "http://127.0.0.1:8000/v1/health" in compose


def test_security_headers_are_set_by_caddy_not_nginx():
    nginx = read("dashboard/nginx.conf")
    assert "add_header X-Content-Type-Options" not in nginx
    assert "add_header Referrer-Policy" not in nginx
    caddy = read("deploy/Caddyfile")
    assert 'X-Content-Type-Options "nosniff"' in caddy
    assert "Referrer-Policy" in caddy


def test_query_shell_sidecar_holds_no_secrets():
    """A-001: mongosh (full Node.js for developers and service keys) runs only in the query-shell
    service: no environment, volumes or Docker socket, capabilities dropped, reachable only from the
    api, worker and mongodb. CI starts the same container for tests/integration/test_query_console.py."""
    compose = yaml.safe_load(read("deploy/docker-compose.yml"))
    services = compose["services"]
    shell = services["query-shell"]
    assert not {"environment", "env_file", "volumes", "build"} & set(shell)
    assert shell["command"] == ["python", "-m", "app.shell_runner"] and shell["entrypoint"] == []
    assert shell["cap_drop"] == ["ALL"] and shell["read_only"] is True
    assert "no-new-privileges:true" in shell["security_opt"]
    assert shell["networks"] == ["query", "query_egress"] and compose["networks"]["query"]["internal"] is True
    on = {
        net: {name for name, svc in services.items() if net in (svc.get("networks") or [])}
        for net in compose["networks"]
    }
    assert on["query"] == {"api", "worker", "mongodb", "query-shell"} and on["query_egress"] == {"query-shell"}
    url = f"http://query-shell:{shell_runner.PORT}"
    assert services["api"]["environment"]["QUERY_SHELL_URL"] == url
    assert services["worker"]["environment"]["QUERY_SHELL_URL"] == url
    ci = read(".github/workflows/ci.yml")
    assert re.findall(r"--cap-add (\w+)", ci) == shell["cap_add"]
    dockerfile = read("api/Dockerfile")
    assert "for i in 1 2 3 4; do" in dockerfile and '--uid "2000$i"' in dockerfile
    assert shell_runner.SLOT_UIDS == (20001, 20002, 20003, 20004)
