"""A-153: container settings have one source of truth (compose / Caddy), not repeats in the images."""

from pathlib import Path

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
