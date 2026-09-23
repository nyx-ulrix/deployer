"""GitHub connections and the GitHub REST calls behind "Connect a Git repository" (docs/DEPLOYMENTS.md).

A user connects GitHub once (OAuth, `oauth.begin(intent="github_connect")`); the token is stored with
`encrypt_secret` in `github_connections`, never logged or returned, and only used to list/read the
user's repositories, clone apps they created with `use_github_connection`, and manage those apps'
push webhooks.

All HTTP goes through `_api` so tests can monkeypatch it (no network in tests).
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crypto import decrypt_secret, encrypt_secret
from app.errors import ApiError, conflict
from app.models import App, GitHubConnection
from app.services import repo_detect
from app.services.instance_settings import oauth_app

log = logging.getLogger(__name__)

API = "https://api.github.com"
HTTP_TIMEOUT = 10.0
CONNECT_SCOPE = "repo admin:repo_hook read:user"
REVOKE_HINT = "You can also revoke Deployer's access at https://github.com/settings/applications."
MAX_FILE_BYTES = 256 * 1024
MAX_FILES = 40
_REPO_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$", re.I)
NOT_ACCESSIBLE = "Repository not found or not accessible — connect GitHub for private repositories"


class GitHubError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _api(method: str, path: str, *, token: str | None = None, params=None, json_body=None) -> tuple[int, Any]:
    """(status, parsed JSON body or None). Raises GitHubError when GitHub can't be reached."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Deployer", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            resp = client.request(method, API + path, headers=headers, params=params, json=json_body)
    except httpx.HTTPError as exc:
        log.warning("GitHub %s %s failed: %s", method, path, type(exc).__name__)
        raise GitHubError("GitHub could not be reached") from exc
    try:
        body = resp.json() if resp.content else None
    except ValueError:
        body = None
    return resp.status_code, body


def _message(status: int, body: Any) -> str:
    text = body.get("message") if isinstance(body, dict) else None
    return f"GitHub answered {status}" + (f": {text}" if text else "")


def parse_repo(url: str | None) -> tuple[str, str] | None:
    """(owner, repo) of a https://github.com/<owner>/<repo> URL, else None."""
    m = _REPO_URL.match((url or "").strip())
    return (m.group(1), m.group(2)) if m else None


# --- connections ---------------------------------------------------------------------------------


def get_connection(db: Session, user_id: str | None) -> GitHubConnection | None:
    if not user_id:
        return None
    return db.scalar(select(GitHubConnection).where(GitHubConnection.user_id == user_id))


def token_of(conn: GitHubConnection) -> str:
    return decrypt_secret(conn.token_encrypted)


def require_token(db: Session, user_id: str) -> str:
    conn = get_connection(db, user_id)
    if conn is None:
        raise conflict("github_not_connected", "Connect GitHub first (New app → Connect GitHub)")
    return token_of(conn)


def save_connection(db: Session, user_id: str, *, login: str, github_user_id: str, token: str, scopes: str) -> None:
    conn = get_connection(db, user_id) or GitHubConnection(user_id=user_id)
    conn.github_login, conn.github_user_id = login[:100], github_user_id[:40]
    conn.token_encrypted, conn.scopes = encrypt_secret(token), scopes[:255]
    db.add(conn)
    db.flush()


def status_out(db: Session, user_id: str) -> dict:
    conn = get_connection(db, user_id)
    return {
        "connected": conn is not None,
        "login": conn.github_login if conn else None,
        "scopes": conn.scopes.split() if conn and conn.scopes else [],
        "configured": oauth_app(db, "github").configured,
    }


def apps_using(db: Session, user_id: str) -> int:
    return len(list(db.scalars(select(App.id).where(App.github_connection_user_id == user_id))))


# --- repositories --------------------------------------------------------------------------------


def _check_token_status(status: int, body: Any) -> None:
    if status == 401:
        raise conflict("github_not_connected", "GitHub rejected the connection (revoked?); connect GitHub again")
    if status != 200:
        raise ApiError(502, "github_error", _message(status, body))


def list_repos(token: str, q: str = "", page: int = 1) -> list[dict]:
    """Repositories the user can access, most recently pushed first. With `q`, up to 5 pages are
    searched (name/description, case-insensitive)."""
    needle = q.strip().lower()
    out: list[dict] = []
    for p in range(page, page + (5 if needle else 1)):
        try:
            status, body = _api(
                "GET",
                "/user/repos",
                token=token,
                params={
                    "affiliation": "owner,collaborator,organization_member",
                    "sort": "pushed",
                    "per_page": 100,
                    "page": p,
                },
            )
        except GitHubError as exc:
            raise ApiError(502, "github_error", exc.message) from exc
        _check_token_status(status, body)
        rows = [r for r in (body if isinstance(body, list) else []) if isinstance(r, dict)]
        for r in rows:
            item = {
                "full_name": r.get("full_name"),
                "private": bool(r.get("private")),
                "default_branch": r.get("default_branch") or "main",
                "html_url": r.get("html_url"),
                "clone_url": r.get("clone_url"),
                "pushed_at": r.get("pushed_at"),
                "description": r.get("description"),
            }
            if not needle or needle in f"{item['full_name']} {item['description'] or ''}".lower():
                out.append(item)
        if len(rows) < 100:
            break
    return out


def _read_repo(owner: str, repo: str, branch: str | None, token: str | None) -> tuple[dict, str, list[str], dict]:
    """(repo info, branch, tree paths, {path: text}) read through the API."""
    base = f"/repos/{quote(owner)}/{quote(repo)}"
    status, info = _api("GET", base, token=token)
    if status in (401, 403, 404) and not (status == 403 and "rate limit" in _message(status, info).lower()):
        raise ApiError(422, "repo_not_accessible", NOT_ACCESSIBLE)
    if status != 200 or not isinstance(info, dict):
        raise ApiError(502, "github_error", _message(status, info))
    ref = branch or info.get("default_branch") or "main"
    status, tree = _api("GET", f"{base}/git/trees/{quote(ref, safe='')}", token=token, params={"recursive": "1"})
    if status in (404, 409, 422):
        raise ApiError(422, "branch_not_found", f"Branch '{ref}' was not found in {owner}/{repo}")
    if status != 200 or not isinstance(tree, dict):
        raise ApiError(502, "github_error", _message(status, tree))
    entries = [e for e in tree.get("tree") or [] if isinstance(e, dict) and e.get("type") == "blob"]
    paths = [str(e.get("path")) for e in entries]
    sizes = {str(e.get("path")): int(e.get("size") or 0) for e in entries}
    files: dict[str, str] = {}
    for path in repo_detect.wanted_files(paths)[:MAX_FILES]:
        if sizes.get(path, 0) > MAX_FILE_BYTES:
            continue
        status, body = _api("GET", f"{base}/contents/{quote(path)}", token=token, params={"ref": ref})
        if status == 200 and isinstance(body, dict) and body.get("encoding") == "base64":
            try:
                files[path] = base64.b64decode(body.get("content") or "").decode("utf-8", "replace")
            except ValueError:
                continue
    return info, ref, paths, files


def detect_draft(db: Session, user_id: str, repo_url: str, branch: str | None) -> dict:
    """`POST /apps/detect`: a suggested app draft, never persisted."""
    parsed = parse_repo(repo_url)
    if parsed is None:
        name = repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
        draft = repo_detect.detect({}, [], name=name, branch=branch or "main")
        draft["warnings"] = [
            "Only GitHub repositories can be inspected; choose a preset and fill in the commands yourself."
        ]
        return {**draft, "repo_url": repo_url, "private": None}
    conn = get_connection(db, user_id)
    token = token_of(conn) if conn else None
    try:
        info, ref, paths, files = _read_repo(parsed[0], parsed[1], branch, token)
    except GitHubError as exc:
        raise ApiError(502, "github_error", exc.message) from exc
    draft = repo_detect.detect(files, paths, name=str(info.get("name") or parsed[1]), branch=ref)
    url = info.get("html_url") or f"https://github.com/{parsed[0]}/{parsed[1]}"
    return {**draft, "repo_url": url, "private": bool(info.get("private"))}


# --- webhooks ------------------------------------------------------------------------------------


def unreachable_reason(url: str) -> str | None:
    """Why GitHub can't deliver to `url` (localhost / private address), else None."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    private = host in ("", "localhost") or host.endswith((".localhost", ".local", ".lan", ".internal"))
    try:
        ip = ipaddress.ip_address(host)
        private = private or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        pass
    if not private:
        return None
    return (
        f"GitHub can't reach {parts.scheme}://{parts.netloc} — set up a public URL (Settings → Domains) "
        "to deploy on push"
    )


def sync_hook(db: Session, app: App, url: str, secret: str) -> list[str]:
    """Creates (or updates) the repo's push webhook for an app that uses a GitHub connection; sets
    `app.github_hook_id`. Returns warnings; never raises for GitHub failures."""
    if not app.github_connection_user_id:
        return []
    repo = parse_repo(app.repo_url)
    conn = get_connection(db, app.github_connection_user_id)
    if repo is None or conn is None:
        return ["The webhook was not added automatically; add it by hand (app Settings → Webhook)."]
    if problem := unreachable_reason(url):
        return [problem]
    config = {"url": url, "content_type": "json", "secret": secret, "insecure_ssl": "0"}
    hooks = f"/repos/{quote(repo[0])}/{quote(repo[1])}/hooks"
    token = token_of(conn)
    try:
        if app.github_hook_id:
            status, body = _api(
                "PATCH", f"{hooks}/{app.github_hook_id}", token=token, json_body={"active": True, "config": config}
            )
            if status == 200:
                return []
            app.github_hook_id = None
            if status != 404:
                return [f"Couldn't update the webhook on GitHub ({_message(status, body)}); add it by hand."]
        status, body = _api(
            "POST", hooks, token=token, json_body={"name": "web", "active": True, "events": ["push"], "config": config}
        )
    except GitHubError as exc:
        return [f"Couldn't add the webhook on GitHub ({exc.message}); add it by hand (app Settings → Webhook)."]
    if status == 201 and isinstance(body, dict) and body.get("id"):
        app.github_hook_id = str(body["id"])
        return []
    return [f"Couldn't add the webhook on GitHub ({_message(status, body)}); add it by hand (app Settings → Webhook)."]


def delete_hook(db: Session, app: App) -> None:
    """Best effort: removes the webhook Deployer created (app deleted or repository changed)."""
    repo = parse_repo(app.repo_url)
    conn = get_connection(db, app.github_connection_user_id)
    if app.github_hook_id and repo and conn:
        try:
            _api("DELETE", f"/repos/{quote(repo[0])}/{quote(repo[1])}/hooks/{app.github_hook_id}", token=token_of(conn))
        except GitHubError:
            log.info("could not remove the GitHub webhook of app %s", app.id)
    app.github_hook_id = None
