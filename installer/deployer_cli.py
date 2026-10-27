#!/usr/bin/env python3
"""The `deployer` command line for everyday work, no browser and no sudo needed (docs/CLI.md).

    deployer login                 # prints a link + code; approve it on any device through the public URL
    deployer apps                  # every app you can see
    deployer env set kanban GOOGLE_CLIENT_SECRET      # prints a link; type the value on any device
    deployer env set kanban SESSION_SECRET --generate # random 64-hex value, never printed

`deployer.sh` hands these commands here before its sudo re-run; the server-management commands
(status, update, ...) stay in deployer.sh. Python 3.9+ standard library only, so the same file works
on a laptop: `python3 deployer_cli.py login --url https://deployer.example.com`.
"""

from __future__ import annotations

import argparse
import functools
import getpass
import http.client
import json
import os
import platform
import secrets
import select
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "deployer-cli/1"
LOCAL_URL = "http://127.0.0.1:8080"
ENV_FILE = Path("/opt/deployer/.env")


class CliError(Exception):
    pass


# --- config ------------------------------------------------------------------------------------


def _is_root() -> bool:
    return getattr(os, "geteuid", lambda: -1)() == 0  # Windows has no geteuid


def _home() -> Path:
    # `sudo deployer login --local` writes the token for the person who ran sudo, not for root.
    user = os.environ.get("SUDO_USER")
    if _is_root() and user and user != "root":
        import pwd

        return Path(pwd.getpwnam(user).pw_dir)
    return Path.home()


def config_path() -> Path:
    if os.environ.get("DEPLOYER_CONFIG"):
        return Path(os.environ["DEPLOYER_CONFIG"])
    base = os.environ.get("XDG_CONFIG_HOME") if not os.environ.get("SUDO_USER") else None
    return Path(base) / "deployer" / "cli.json" if base else _home() / ".config" / "deployer" / "cli.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise CliError(f"Can't read {config_path()}: {exc}") from exc


def save_config(data: dict) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, path)
    user = os.environ.get("SUDO_USER")
    if _is_root() and user and user != "root":
        import pwd

        pw = pwd.getpwnam(user)
        for p in (path.parent, path):
            os.chown(p, pw.pw_uid, pw.pw_gid)
    return path


def local_url() -> str:
    """This server's dashboard: the port in /opt/deployer/.env when readable (root), else 8080."""
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("DEPLOYER_HTTP_PORT="):
                port = line.split("=", 1)[1].strip().strip("'\"")
                if port.isdigit():
                    return f"http://127.0.0.1:{port}"
    except OSError:
        pass
    return LOCAL_URL


# --- HTTP --------------------------------------------------------------------------------------


class Api:
    def __init__(self, url: str, token: str | None = None):
        self.url = url.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: dict | None = None, *, auth: bool = True, timeout: float = 60):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + "/v1" + path, data=data, method=method)
        req.add_header("User-Agent", USER_AGENT)
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if auth:
            if not self.token:
                raise CliError("Not signed in. Run: deployer login")
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise self._error(exc) from None
        except urllib.error.URLError as exc:
            raise CliError(f"Can't reach Deployer at {self.url}: {exc.reason}") from None
        except (OSError, http.client.HTTPException) as exc:
            # A dropped or reset connection, or a timeout: like URLError, a CliError without a status.
            raise CliError(f"Lost the connection to Deployer at {self.url}: {exc!r}") from None
        return json.loads(raw) if raw else None

    def _error(self, exc: urllib.error.HTTPError) -> CliError:
        try:
            err = json.loads(exc.read()).get("error") or {}
        except ValueError:
            err = {}
        code, message = err.get("code", ""), err.get("message") or f"HTTP {exc.code}"
        if exc.code == 401 and code != "invalid_credentials":
            message += " - run: deployer login"
        out = CliError(message)
        out.status, out.code, out.details = exc.code, code, err.get("details")  # type: ignore[attr-defined]
        return out


def api_from_config(args) -> Api:
    cfg = load_config()
    url = getattr(args, "url", None) or os.environ.get("DEPLOYER_URL") or cfg.get("url")
    token = os.environ.get("DEPLOYER_TOKEN") or cfg.get("token")
    if not token:
        raise CliError("Not signed in. Run: deployer login")
    return Api(url or local_url(), token)


# --- output ------------------------------------------------------------------------------------


def table(rows: list[list[str]], headers: list[str]) -> None:
    if not rows:
        print("(none)")
        return
    widths = [max(len(str(r[i])) for r in [headers, *rows]) for i in range(len(headers))]
    for r in [headers, *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=False)).rstrip())


def emit(args, data, human) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
    else:
        human(data)


def ask_secret(prompt: str) -> str:
    if not sys.stdin.isatty():
        value = sys.stdin.readline().rstrip("\n")
    else:
        value = getpass.getpass(f"{prompt}: ")
    if not value:
        raise CliError("Nothing entered; nothing was changed.")
    return value


PIPE_WAIT = 5.0  # seconds a pipe gets for its first line before the value is asked for on the web


def piped_stdin() -> str | None:
    """A value piped or redirected in (`echo x | deployer env set ...`, `< file`); None at a terminal or when
    nothing arrives. A regular file is read. A pipe gets PIPE_WAIT seconds for its first line or EOF: agents
    often run with an idle stdin that never closes, and then the value is asked for on the web (slower
    producers: --stdin). On Windows, where select() only takes sockets, a pipe is read blocking."""
    stdin = sys.stdin
    try:
        if stdin is None or stdin.isatty():
            return None
    except ValueError:
        return None
    try:
        fd = stdin.fileno()
    except (OSError, ValueError):
        fd = None  # an in-memory stream: read it
    if fd is not None:
        try:
            mode = os.fstat(fd).st_mode
        except OSError:
            return None
        if not stat.S_ISREG(mode) and os.name != "nt":
            try:
                ready, _, _ = select.select([fd], [], [], PIPE_WAIT)
            except (OSError, ValueError):
                ready = [fd]  # select can't watch it: read it, as a terminal-less stdin always was
            if not ready:
                return None
    try:
        value = stdin.readline().rstrip("\r\n")
    except (OSError, ValueError):
        return None
    return value or None


def read_stdin(what: str) -> str:
    """--stdin: one line from stdin, waiting as long as the producer needs (hidden prompt at a terminal)."""
    if sys.stdin.isatty():
        return ask_secret(what)
    value = sys.stdin.readline().rstrip("\r\n")
    if not value:
        raise CliError("Nothing was piped in; nothing was changed.")
    return value


def _interrupt_on_signals() -> dict:
    """SIGTERM and SIGHUP (an agent's tool timeout, a closed SSH session) stop a wait like Ctrl+C does, so
    the request is cancelled instead of left open. Returns the old handlers for _restore_signals."""

    def handler(signum, frame):
        raise KeyboardInterrupt

    old = {}
    for name in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            previous = signal.signal(sig, handler)
        except (ValueError, OSError):  # not the main thread
            continue
        old[sig] = previous if previous is not None else signal.SIG_DFL
    return old


def _restore_signals(old: dict) -> None:
    for sig, previous in old.items():
        try:
            signal.signal(sig, previous)
        except (ValueError, OSError, TypeError):
            pass


def _cancel_input(api: Api, base: str) -> str | None:
    """Best effort: never raises, waits at most 5 s. Returns the request's status after the cancel."""
    try:
        out = api.call("POST", base + "/cancel", timeout=5)
    except Exception:  # noqa: BLE001 - best effort by design: any failure means "unknown"
        return None
    return out.get("status") if isinstance(out, dict) else None


def _transient(exc: CliError) -> bool:
    """No answer, a server or proxy error (API restarting, tunnel reconnecting) or a rate limit: retry.
    401/403/404 and other client errors won't get better by waiting."""
    status = getattr(exc, "status", None)
    return status is None or status >= 500 or status == 429


def ask_web(
    api: Api, title: str, fields: list[dict], *, description: str | None = None, app_ids: list[str] | None = None
) -> dict:
    """An input request (docs/CLI.md, "Input requests"): prints a link the owner opens on any device, then
    waits until they fill it in. Returns the values, or with app_ids (the values went straight into those
    apps' Environment and never come back) {"keys": [...], "apps": [{id, name}]}. Any other way out
    (Ctrl+C, SIGTERM, an error) cancels the request. Its messages go to stderr so that stdout stays clean
    for `deployer ask`."""
    body: dict = {"title": title, "fields": fields}
    if description:
        body["description"] = description
    if app_ids:
        body["app_ids"] = app_ids
    start = api.call("POST", "/auth/cli/inputs", body)
    err = sys.stderr
    print("\nOpen this link on your phone or computer to fill it in:\n", file=err)
    print(f"    {start['url']}\n", file=err)
    if urllib.parse.urlsplit(start["url"]).hostname in ("localhost", "127.0.0.1"):
        print(
            "Note: Deployer has no public address yet, so that link only opens on this server. Set one up under\n"
            "Settings -> Domains & remote access, or use an SSH tunnel (ssh -L 8080:localhost:8080 ...).\n",
            file=err,
        )
    expires = int(start.get("expires_in") or 1800)
    print(f"Waiting for it (Ctrl+C to cancel; the link expires in {expires // 60} minutes)...", file=err, flush=True)
    interval = int(start.get("interval") or 3)
    deadline = time.monotonic() + expires + 5
    base = f"/auth/cli/inputs/{start['id']}"
    old_signals = _interrupt_on_signals()
    ended = False  # the server reported a final status: nothing left to cancel
    try:
        lost: CliError | None = None
        backoff = 0
        while time.monotonic() < deadline:
            time.sleep(backoff or interval)
            try:
                out = api.call("POST", base + "/poll")
            except CliError as exc:
                if getattr(exc, "code", "") == "slow_down":
                    interval += 1
                    continue
                if not _transient(exc):
                    raise
                if lost is None:
                    print("Connection to Deployer lost, retrying...", file=err, flush=True)
                lost, backoff = exc, min(30, max(interval, backoff * 2))
                continue
            lost, backoff = None, 0
            interval = int(out.get("interval") or interval)
            status = out.get("status")
            if status == "submitted":
                ended = True
                if "values" in out:
                    return out["values"]
                return {"keys": out.get("keys") or [], "apps": out.get("apps") or []}
            if status in ("cancelled", "expired", "consumed"):
                ended = True
                raise CliError(f"The request was {status}; nothing was changed. Run the command again.")
            if status == "pending" and out.get("unavailable_apps"):
                n = int(out["unavailable_apps"])
                raise CliError(
                    f"{n} of the apps this request saves to {'no longer exists' if n == 1 else 'no longer exist'} "
                    "or you can no longer change it; the request was cancelled and nothing was changed. "
                    "Run the command again."
                )
        if lost is not None:
            raise CliError(f"{lost} - gave up when the link expired. Run the command again.")
        raise CliError("The link expired; nothing was changed. Run the command again.")
    except BaseException:
        if not ended and _cancel_input(api, base) == "submitted":
            # An app_ids request filled just before the stop: cancelling does not undo it (docs/CLI.md).
            print(
                "Note: the values had already been saved in the apps' Environment; stopping did not undo that.",
                file=err,
            )
        raise
    finally:
        _restore_signals(old_signals)


# --- lookups -----------------------------------------------------------------------------------


def _match(items: list[dict], ref: str, what: str, keys=("id", "slug", "name")) -> dict:
    ref_l = ref.lower()
    hits = [i for i in items if any(str(i.get(k) or "").lower() == ref_l for k in keys)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CliError(f"No {what} called '{ref}'.")
    names = ", ".join(
        f"{h.get('_project', '')}{'/' if h.get('_project') else ''}{h.get('slug') or h['id']}" for h in hits
    )
    raise CliError(f"'{ref}' matches several {what}s: {names}. Use project/app or the id.")


def find_project(api: Api, ref: str) -> dict:
    return _match(api.call("GET", "/projects"), ref, "project")


def all_apps(api: Api) -> list[dict]:
    out = []
    for project in api.call("GET", "/projects"):
        for app in api.call("GET", f"/projects/{project['id']}/apps"):
            out.append({**app, "_project": project["slug"], "_project_name": project["name"]})
    return out


def find_app(api: Api, ref: str) -> dict:
    if "/" in ref:
        project_ref, app_ref = ref.split("/", 1)
        project = find_project(api, project_ref)
        apps = [{**a, "_project": project["slug"]} for a in api.call("GET", f"/projects/{project['id']}/apps")]
        return _match(apps, app_ref, "app")
    return _match(all_apps(api), ref, "app")


def app_path(app: dict, suffix: str = "") -> str:
    return f"/projects/{app['project_id']}/apps/{app['id']}{suffix}"


# --- commands: login -----------------------------------------------------------------------------


def cmd_login(args) -> int:
    if args.local:
        return _login_local(args)
    cfg = load_config()
    url = (args.url or os.environ.get("DEPLOYER_URL") or cfg.get("url") or local_url()).rstrip("/")
    api = Api(url)
    host = socket.gethostname()
    start = api.call(
        "POST",
        "/auth/cli/logins",
        {"name": args.name or f"deployer CLI on {host}", "hostname": host, "os": platform.platform(terse=True)},
        auth=False,
    )
    link = start["verification_uri"]
    print("\nTo sign in, open this link on your phone or computer:\n")
    print(f"    {link}\n")
    print(f"and check that it shows this code:  {start['user_code']}\n")
    if urllib.parse.urlsplit(link).hostname in ("localhost", "127.0.0.1"):
        print(
            "Note: Deployer has no public address yet, so that link only opens on this server. Set one up under\n"
            "Settings -> Domains & remote access, use an SSH tunnel (ssh -L 8080:localhost:8080 ...), or run\n"
            "`sudo deployer login --local` instead.\n"
        )
    print("Waiting for approval (Ctrl+C to cancel; the code expires in 10 minutes)...", flush=True)
    interval = int(start.get("interval") or 3)
    deadline = time.monotonic() + int(start.get("expires_in") or 600) + 5
    poll = f"/auth/cli/logins/{start['login_id']}/poll"
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            out = api.call("POST", poll, {"poll_secret": start["poll_secret"]}, auth=False)
        except CliError as exc:
            if getattr(exc, "code", "") == "slow_down":
                interval += 1
                continue
            raise
        status = out.get("status")
        if status == "approved":
            path = save_config({"url": url, "token": out["token"], "email": out.get("email")})
            print(f"\nSigned in as {out.get('email')}. Token saved to {path} (only you can read it).")
            return 0
        if status in ("denied", "expired", "consumed"):
            raise CliError(f"The login was {status}. Run `deployer login` again.")
    raise CliError("The code expired. Run `deployer login` again.")


def _login_local(args) -> int:
    """No browser at all: root on this server mints the token directly (`deployer cli-token`)."""
    if os.name == "nt":
        raise CliError("--local works on the Linux server only; on Windows run: deployer login")
    if not _is_root():
        cmd = ["sudo", "deployer", "login", "--local"] + (["--email", args.email] if args.email else [])
        os.execvp("sudo", cmd)
    cmd = ["deployer", "cli-token", "--json"] + ([args.email] if args.email else [])
    env = {**os.environ, "DEPLOYER_CLI_TOKEN_NAME": args.name or f"deployer CLI on {socket.gethostname()} (local)"}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise CliError(
            (result.stdout + result.stderr).strip().splitlines()[-1] if result.stdout + result.stderr else "failed"
        )
    out = json.loads(result.stdout.strip().splitlines()[-1])
    path = save_config({"url": local_url(), "token": out["token"], "email": out.get("email")})
    print(f"Signed in as {out.get('email')}. Token saved to {path}.")
    return 0


def cmd_logout(args) -> int:
    cfg = load_config()
    if cfg.get("token"):
        try:
            Api(cfg.get("url") or local_url(), cfg["token"]).call("DELETE", "/auth/cli/tokens/current")
        except CliError as exc:
            print(f"(The server did not revoke the token: {exc})", file=sys.stderr)
    try:
        config_path().unlink()
    except FileNotFoundError:
        pass
    print("Signed out; the token was revoked.")
    return 0


def cmd_whoami(args) -> int:
    api = api_from_config(args)
    me = api.call("GET", "/auth/me")
    emit(args, me, lambda m: print(f"{m['email']}{' (instance owner)' if m['is_instance_owner'] else ''} at {api.url}"))
    return 0


def cmd_tokens(args) -> int:
    api = api_from_config(args)
    if args.revoke:
        api.call("DELETE", f"/auth/cli/tokens/{args.revoke}")
        print("Revoked.")
        return 0
    rows = api.call("GET", "/auth/cli/tokens")
    emit(
        args,
        rows,
        lambda rs: table(
            [
                [
                    r["id"],
                    r["name"],
                    r["prefix"] + "...",
                    r["last_used_at"] or "never",
                    "this one" if r["current"] else "",
                ]
                for r in rs
            ],
            ["ID", "NAME", "TOKEN", "LAST USED", ""],
        ),
    )
    return 0


# --- commands: projects and apps ---------------------------------------------------------------


def cmd_projects(args) -> int:
    api = api_from_config(args)
    if args.action == "create":
        if not args.name:
            raise CliError("Usage: deployer projects create <name> [--sql] [--nosql]")
        body = {"name": args.name, "provision": {"sql": args.sql, "nosql": args.nosql}}
        project = api.call("POST", "/projects", body)
        print(f"Created project {project['name']} ({project['slug']}).")
        return 0
    rows = api.call("GET", "/projects")
    emit(args, rows, lambda rs: table([[r["slug"], r["name"], r["my_role"]] for r in rs], ["PROJECT", "NAME", "ROLE"]))
    return 0


def _app_status(app: dict) -> str:
    live = app.get("live_deployment")
    return live["status"] if live else "not deployed"


def cmd_apps(args) -> int:
    api = api_from_config(args)
    if args.project:
        project = find_project(api, args.project)
        apps = [{**a, "_project": project["slug"]} for a in api.call("GET", f"/projects/{project['id']}/apps")]
    else:
        apps = all_apps(api)
    emit(
        args,
        apps,
        lambda rs: table(
            [[f"{a['_project']}/{a['slug']}", a["preset"], _app_status(a), " ".join(a.get("urls") or [])] for a in rs],
            ["APP", "TYPE", "STATUS", "URLS"],
        ),
    )
    return 0


def cmd_app_show(args) -> int:
    api = api_from_config(args)
    app = find_app(api, args.app)

    def human(a):
        print(f"{a['name']}  ({a['_project']}/{a['slug']}, id {a['id']})")
        print(f"  repository : {a['repo_url']} @ {a['branch']} ({a['root_dir']})")
        print(f"  type       : {a['preset']}, target {a['target']}")
        print(f"  status     : {_app_status(a)}")
        print(f"  addresses  : {' '.join(a.get('urls') or []) or '-'}")
        print(f"  env        : {', '.join(a['env_keys']) or '-'}")
        gh = a.get("github")
        print(
            "  push deploy: "
            + ("on (webhook)" if gh and gh.get("hook_active") else "off - connect GitHub in Account settings")
        )

    emit(args, app, human)
    return 0


def cmd_app_create(args) -> int:
    api = api_from_config(args)
    project = find_project(api, args.project)
    base = f"/projects/{project['id']}/apps"
    draft = api.call(
        "POST", base + "/detect", {"repo_url": args.repo, **({"branch": args.branch} if args.branch else {})}
    )
    for w in draft.get("warnings") or []:
        print(f"warning: {w}", file=sys.stderr)
    fields = (
        "name",
        "repo_url",
        "branch",
        "root_dir",
        "preset",
        "install_command",
        "build_command",
        "start_command",
        "output_dir",
        "container_port",
    )
    body = {k: draft.get(k) for k in fields if draft.get(k) is not None}
    overrides = (
        ("name", args.name),
        ("root_dir", args.root_dir),
        ("container_port", args.port),
        ("preset", args.preset),
        ("install_command", args.install),
        ("build_command", args.build),
        ("start_command", args.start),
    )
    for key, value in overrides:
        if value:
            body[key] = value
    if args.api_key:
        keys = api.call("GET", f"/projects/{project['id']}/api-keys")
        match = [k for k in keys if args.api_key in (k["id"], k["name"]) and not k.get("revoked_at")]
        if not match:
            raise CliError(f"No API key {args.api_key!r} in {project['slug']}: create it under the project's API keys")
        body["api_key_id"] = match[0]["id"]
    github = api.call("GET", "/integrations/github")
    body["use_github_connection"] = bool(github.get("connected")) and "github.com" in args.repo
    app = api.call("POST", base, body)
    print(f"Created {project['slug']}/{app['slug']} ({app['preset']}).")
    if draft.get("env_keys"):
        print(f"The repository's example env file lists: {', '.join(draft['env_keys'])}")
        print(f"Set them with: deployer env set {project['slug']}/{app['slug']} <NAME>")
    if not body["use_github_connection"]:
        print("GitHub is not connected, so pushes won't deploy automatically: connect it under Settings -> Account.")
    for w in app.get("warnings") or []:
        print(f"warning: {w}", file=sys.stderr)
    print(f"Deploy it with: deployer deploy {project['slug']}/{app['slug']}")
    return 0


def cmd_deploy(args) -> int:
    api = api_from_config(args)
    app = find_app(api, args.app)
    dep = api.call("POST", app_path(app, "/deploy"), {"branch": args.branch} if args.branch else {})
    if dep.get("github_actions"):
        print(f"Started on GitHub Actions: {dep.get('runs_url')}")
        return 0
    print(f"Deployment {dep['id']} {dep['status']}.")
    if not args.wait:
        print(f"Follow it with: deployer deploy {args.app} --wait   (or the Deploys tab)")
        return 0
    seen = 0
    while True:
        time.sleep(3)
        cur = api.call("GET", app_path(app, f"/deployments/{dep['id']}?log=1"))
        log = cur.get("log") or ""
        if len(log) > seen:
            sys.stdout.write(log[seen:])
            sys.stdout.flush()
            seen = len(log)
        if cur["status"] in ("live", "failed", "cancelled", "superseded"):
            print(f"\nDeployment {cur['status']}.")
            return 0 if cur["status"] == "live" else 1


def cmd_logs(args) -> int:
    api = api_from_config(args)
    app = find_app(api, args.app)
    out = api.call("GET", app_path(app, f"/logs?tail={args.tail}"))
    print("\n".join(out.get("lines") or ["(no output yet)"]))
    return 0


def cmd_domain(args) -> int:
    api = api_from_config(args)
    app = find_app(api, args.app)
    if args.action == "add":
        try:
            dom = api.call("POST", app_path(app, "/domains"), {"hostname": args.hostname, "overwrite": args.overwrite})
        except CliError as exc:
            if getattr(exc, "code", "") == "dns_record_exists":
                recs = (getattr(exc, "details", None) or {}).get("records") or []
                for r in recs:
                    print(f"  existing: {r.get('type')} {r.get('content')}", file=sys.stderr)
                raise CliError(
                    f"{args.hostname} already has a DNS record. Run again with --overwrite to replace it."
                ) from None
            raise
        print(f"Added https://{dom['hostname']} ({dom['status']}).")
        return 0
    domains = app.get("domains") or []
    for d in domains:
        if d["hostname"].lower() == (args.hostname or "").lower():
            api.call("DELETE", app_path(app, f"/domains/{d['id']}"))
            print(f"Removed {d['hostname']}.")
            return 0
    raise CliError(f"{app['slug']} has no hostname {args.hostname}.")


# --- commands: environment ---------------------------------------------------------------------


def cmd_env(args) -> int:
    api = api_from_config(args)
    app = find_app(api, args.app)
    if args.action == "list":
        if args.show:
            env = api.call("GET", app_path(app, "/env"))["env"]
            emit(args, env, lambda e: [print(f"{k}={v}") for k, v in sorted(e.items())])
        else:
            emit(args, app["env_keys"], lambda keys: print("\n".join(keys) if keys else "(no variables)"))
        return 0
    if args.action == "unset":
        out = api.call("PATCH", app_path(app), {"env_unset": args.keys})
        print(f"Removed {', '.join(args.keys)}. {_apply_hint(args.app, out)}")
        return 0
    sources = (len(args.keys) == 2) + args.generate + args.prompt + args.stdin
    if len(args.keys) not in (1, 2) or sources > 1:
        raise CliError("Usage: deployer env set <app> NAME [value | --generate | --prompt | --stdin]")
    key = args.keys[0]
    if args.generate:
        value = secrets.token_hex(args.bytes)
    elif len(args.keys) == 2:
        value = args.keys[1]
        print(
            "note: a value on the command line is kept in your shell history; leave it out to be asked.",
            file=sys.stderr,
        )
    elif args.prompt:
        value = ask_secret(f"{key} for {app['slug']} (hidden)")
    elif args.stdin:
        value = read_stdin(f"{key} for {app['slug']} (hidden)")
    else:
        value = piped_stdin()
        if value is None:
            # The page names the app (and its project) itself, so the title stays short.
            field = {"key": key, "label": key, "secret": True}
            out = ask_web(api, f"Set {key}", [field], app_ids=[app["id"]])
            if not out["keys"]:
                print(NOTHING_ENTERED)
                return 0
            print(f"Set {key} to the value you typed. {_web_hint(args.app)}")
            return 0
    out = api.call("PATCH", app_path(app), {"env_set": {key: value}})
    shown = "a new random value (not shown)" if args.generate else "the value"
    print(f"Set {key} to {shown}. {_apply_hint(args.app, out)}")
    return 0


NOTHING_ENTERED = "Nothing was entered; nothing was changed."


def _apply_hint(ref: str, app: dict) -> str:
    if app.get("env_deployment_id"):
        return "The live app is being republished with it."
    return f"It applies at the next deploy: deployer deploy {ref}"


def _web_hint(ref: str | None = None) -> str:
    """After a web submit the server already wrote the values, and republished live App Runner / Cloud Run
    apps; the poll doesn't say which, so the hint covers both."""
    if ref:
        return (
            f"It applies at the next deploy (deployer deploy {ref}); "
            "an app on App Runner or Cloud Run is republished with it now."
        )
    return (
        "They apply at each app's next deploy (deployer deploy <app>); "
        "apps on App Runner or Cloud Run are republished with them now."
    )


# --- commands: Google sign-in for an app -------------------------------------------------------


GOOGLE_CONSOLE = "https://console.cloud.google.com/auth/clients/create"
GOOGLE_CLIENT_ID_PATTERN = r"^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$"


def cmd_google_oauth(args) -> int:
    """Google has no API for creating OAuth web clients: this prints exactly what to enter in its console
    (from any device), then asks for the ID and secret through one input request (--prompt: in this
    terminal) and stores them in each app's environment."""
    api = api_from_config(args)
    apps = [find_app(api, ref) for ref in args.apps]
    uris = list(args.redirect or [])
    for app in apps:
        hosts = [d["hostname"] for d in app.get("domains") or [] if d.get("status") == "active"]
        if not hosts and not args.redirect:
            raise CliError(
                f"{app['slug']} has no hostname yet: deployer domain add {app['slug']} <hostname> first, "
                "or pass --redirect."
            )
        uris += [f"https://{h}{args.path}" for h in hosts]
    print(f"\n1. Open {GOOGLE_CONSOLE} on any device")
    print("   (first time: also fill in Branding, and under Audience choose External and Publish app).")
    print("2. Application type: Web application. Add these Authorized redirect URIs:\n")
    for uri in dict.fromkeys(uris):
        print(f"     {uri}")
    print("\n3. Create, then copy the Client ID and Client secret (Google shows the secret only once).\n")
    piped = None if args.prompt else piped_stdin()  # `printf 'ID\nSECRET\n' | deployer google-oauth ...`
    if not args.prompt and piped is None:
        lines = [
            "In Google's console create an OAuth client of type Web application with these Authorized redirect URIs:",
            *dict.fromkeys(uris),
            f"Console: {GOOGLE_CONSOLE}",
            "Then paste the Client ID and Client secret here (Google shows the secret only once).",
        ]
        fields = [
            {
                "key": args.id_var,
                "label": "Client ID",
                "placeholder": "123-abc.apps.googleusercontent.com",
                "pattern": GOOGLE_CLIENT_ID_PATTERN,
                "link": GOOGLE_CONSOLE,
                "link_label": "Google console",
            },
            {"key": args.secret_var, "label": "Client secret", "secret": True},
        ]
        out = ask_web(api, "Google sign-in", fields, description="\n\n".join(lines), app_ids=[a["id"] for a in apps])
        if not out["keys"]:
            print(NOTHING_ENTERED)
            return 0
        for app in apps:
            print(f"Saved {', '.join(out['keys'])} on {app['_project']}/{app['slug']}.")
        print(_web_hint())
        return 0
    if piped is not None:
        client_id = piped.strip()
    else:
        client_id = input("Client ID: ").strip() if sys.stdin.isatty() else sys.stdin.readline().strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise CliError("That doesn't look like a Google Client ID (it ends in .apps.googleusercontent.com).")
    secret = ask_secret("Client secret (hidden)")
    for app in apps:
        ref = f"{app['_project']}/{app['slug']}"
        out = api.call("PATCH", app_path(app), {"env_set": {args.id_var: client_id, args.secret_var: secret}})
        print(f"Saved {args.id_var} and {args.secret_var} on {ref}. {_apply_hint(ref, out)}")
    return 0


# --- commands: ask for anything ----------------------------------------------------------------


def cmd_ask(args) -> int:
    """`deployer ask "<title>" KEY[:secret] ...`: a generic input request for scripts and agents."""
    api = api_from_config(args)
    fields = []
    for spec in args.fields:
        key, _, flags = spec.partition(":")
        flags_set = {f for f in flags.lower().split(",") if f}
        unknown = flags_set - {"secret", "optional", "multiline"}
        if unknown:
            raise CliError(
                f"Unknown option {', '.join(sorted(unknown))} in {spec!r}: "
                "use KEY, KEY:secret, KEY:optional or KEY:multiline."
            )
        field = {"key": key, "label": key}
        field.update({f: True for f in flags_set})
        fields.append(field)
    if args.link:
        fields[0]["link"] = args.link
    apps = [find_app(api, ref) for ref in args.app or []]
    out = ask_web(api, args.title, fields, description=args.description, app_ids=[a["id"] for a in apps] or None)
    if not apps or args.json:
        print(json.dumps(out, indent=2))
        return 0
    if not out["keys"]:
        print(NOTHING_ENTERED)
        return 0
    names = ", ".join(f"{a['_project']}/{a['slug']}" for a in apps)
    print(f"Saved {', '.join(out['keys'])} on {names}. {_web_hint()}")
    return 0


# --- commands: provider setup through your own sign-ins (gcloud, gh) ---------------------------
# What a provider's own command line can do once you are signed in to it there; Deployer never sees
# those credentials.

GOOGLE_API_ALIASES = {
    "calendar": "calendar-json.googleapis.com",
    "drive": "drive.googleapis.com",
    "gmail": "gmail.googleapis.com",
    "sheets": "sheets.googleapis.com",
    "docs": "docs.googleapis.com",
    "people": "people.googleapis.com",
    "tasks": "tasks.googleapis.com",
    "youtube": "youtube.googleapis.com",
    "maps": "maps-backend.googleapis.com",
}


def _run(cmd: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess:
    exe = shutil.which(cmd[0])  # also finds gcloud.cmd on Windows, which a bare name doesn't
    if exe is None:
        raise CliError(f"{cmd[0]} is not installed here.")
    try:
        return subprocess.run([exe, *cmd[1:]], input=stdin, capture_output=True, text=True)
    except FileNotFoundError:
        raise CliError(f"{cmd[0]} is not installed here.") from None


def _last_line(result: subprocess.CompletedProcess) -> str:
    lines = (result.stderr or result.stdout or "").strip().splitlines()
    return lines[-1] if lines else f"exit code {result.returncode}"


def cmd_google_apis(args) -> int:
    """`deployer google-apis <api>... --app <app> | --project <id>`: turns Google APIs on with gcloud, in the
    Google Cloud project of the app's GOOGLE_CLIENT_ID (its number is the ID's prefix)."""
    if bool(args.app) == bool(args.project):
        raise CliError("Name the project: --app <app> (from its GOOGLE_CLIENT_ID) or --project <id or number>.")
    project = args.project
    if args.app:
        api = api_from_config(args)
        app = find_app(api, args.app)
        client_id = api.call("GET", app_path(app, "/env"))["env"].get(args.id_var, "")
        project = client_id.split("-", 1)[0]
        if not project.isdigit():
            raise CliError(f"{args.app} has no Google {args.id_var} to take the project from; pass --project.")
    services = [GOOGLE_API_ALIASES.get(a.lower(), a) for a in args.apis]
    for s in services:
        if "." not in s:
            raise CliError(
                f"Unknown API {s!r}: use one of {', '.join(GOOGLE_API_ALIASES)} or a full name like x.googleapis.com."
            )
    gcloud = ["gcloud", "--quiet"]
    account = _run([*gcloud, "config", "get-value", "account"]).stdout.strip()
    if not account:
        raise CliError("gcloud is not signed in. Run it yourself first: gcloud auth login --no-launch-browser")
    result = _run([*gcloud, "services", "enable", *services, f"--project={project}"])
    if result.returncode != 0:
        raise CliError(f"gcloud: {_last_line(result)}")
    listed = _run([*gcloud, "services", "list", "--enabled", f"--project={project}", "--format=value(config.name)"])
    enabled = set(listed.stdout.split())
    missing = [s for s in services if s not in enabled]
    if missing:
        raise CliError(
            f"gcloud reported success but these are not on yet: {', '.join(missing)}. Try again in a minute."
        )
    print(f"On in project {project} (as {account}): {', '.join(services)}")
    return 0


def cmd_webhook(args) -> int:
    """`deployer webhook <app> [--rotate]`: the repository's push webhook, so a push deploys. Through the
    app's GitHub connection when it has one, else through the GitHub CLI (`gh`) you are signed in to."""
    api = api_from_config(args)
    app = find_app(api, args.app)
    ref = f"{app['_project']}/{app['slug']}"
    gh_conn = app.get("github")
    if gh_conn and gh_conn.get("hook_active") and not args.rotate:
        print(
            f"{ref}: the push webhook is already on "
            f"(added through {gh_conn['connected_by_email']}'s GitHub connection)."
        )
        return 0
    if gh_conn:
        out = api.call("POST", app_path(app, "/webhook/rotate"))
        for w in out.get("warnings") or []:
            print(f"warning: {w}", file=sys.stderr)
        if not out.get("hook_active"):
            raise CliError("GitHub didn't accept the webhook (see above); nothing else was changed.")
        print(f"{ref}: push webhook on; a push to {app.get('branch') or 'its branch'} deploys it.")
        return 0
    parts = urllib.parse.urlsplit(app.get("repo_url") or "")
    path = parts.path.strip("/").removesuffix(".git").split("/")
    if parts.hostname != "github.com" or len(path) != 2:
        raise CliError(f"{ref} doesn't deploy from a github.com repository.")
    repo = "/".join(path)
    if _run(["gh", "api", "user", "--jq", ".login"]).returncode != 0:
        raise CliError(
            "No GitHub connection on this app and the GitHub CLI isn't signed in. Either connect GitHub in "
            "Deployer (Account settings) or sign in yourself with: gh auth login"
        )
    hook = api.call("POST" if args.rotate else "GET", app_path(app, "/webhook" + ("/rotate" if args.rotate else "")))
    config = {"url": hook["url"], "content_type": "json", "secret": hook["secret"], "insecure_ssl": "0"}
    listed = _run(["gh", "api", f"repos/{repo}/hooks", "--jq", f'.[] | select(.config.url == "{hook["url"]}") | .id'])
    if listed.returncode != 0:
        raise CliError(f"gh: {_last_line(listed)} (adding webhooks needs admin rights on {repo})")
    existing = listed.stdout.split()
    if existing:
        cmd = ["gh", "api", "-X", "PATCH", f"repos/{repo}/hooks/{existing[0]}", "--input", "-"]
        body = {"active": True, "events": ["push"], "config": config}
    else:
        cmd = ["gh", "api", "-X", "POST", f"repos/{repo}/hooks", "--input", "-"]
        body = {"name": "web", "active": True, "events": ["push"], "config": config}
    result = _run(cmd, stdin=json.dumps(body))  # the secret goes on stdin, never the command line
    if result.returncode != 0:
        raise CliError(f"gh: {_last_line(result)}")
    print(f"{ref}: push webhook {'updated' if existing else 'added'} on {repo}; a push deploys it.")
    return 0


# --- commands: instance settings (instance owner) ----------------------------------------------
# Each asks for its values through an input request (--prompt: in this terminal), so a headless
# server needs neither sudo nor a browser on it. The values go straight to the API, never to stdout.


def _ask_values(args, title: str, fields: list[dict], description: str) -> dict:
    if not getattr(args, "prompt", False):
        return ask_web(api_from_config(args), title, fields, description=description)
    print(description + "\n")
    out = {}
    for f in fields:
        if f.get("secret"):
            out[f["key"]] = ask_secret(f"{f['label']} (hidden)")
        else:
            out[f["key"]] = input(f"{f['label']}: ").strip()
    return out


def _oauth_guide(provider: str, settings: dict) -> tuple[str, str]:
    """The console link and what to do there, for Deployer's own sign-in app (docs/SETUP.md)."""
    callback = settings[provider]["callback_url"]
    home = settings["public_url"]
    if provider == "github":
        query = urllib.parse.urlencode(
            {
                "oauth_application[name]": "Deployer",
                "oauth_application[url]": home,
                "oauth_application[callback_url]": callback,
            }
        )
        link = f"https://github.com/settings/applications/new?{query}"
        steps = (
            f"Open GitHub's 'Register a new OAuth app' form (the link fills it in: name Deployer, "
            f"Homepage URL {home}, Authorization callback URL {callback}). Click Register application, "
            "then Generate a new client secret, and paste both values here."
        )
        return link, steps
    link = "https://console.cloud.google.com/auth/clients/create"
    steps = (
        "In Google's console create an OAuth client: Application type Web application, name Deployer, "
        f"Authorized redirect URI {callback}. (First time in this project: fill in Branding, and under "
        "Audience choose External.) Create, then paste the Client ID and Client secret here; Google shows "
        "the secret only once."
    )
    return link, steps


def cmd_oauth(args) -> int:
    """`deployer oauth status|set|clear [google|github]` without sudo: Deployer's own sign-in buttons."""
    api = api_from_config(args)
    settings = api.call("GET", "/instance/settings")
    if args.action == "status":

        def human(s):
            for name in ("google", "github"):
                p = s[name]
                state = (
                    f"configured (Client ID {p['client_id']})"
                    if p["configured"]
                    else "Client secret missing"
                    if p["client_id"]
                    else "not configured"
                )
                print(f"{name.title().replace('Github', 'GitHub')}: {state}\n  Callback URL: {p['callback_url']}")

        emit(args, {k: settings[k] for k in ("public_url", "google", "github")}, human)
        return 0
    if not args.provider:
        raise CliError(f"Which one? deployer oauth {args.action} google|github")
    name = args.provider.title().replace("Github", "GitHub")
    if args.action == "clear":
        api.call("PUT", "/instance/settings", {f"{args.provider}_client_id": "", f"{args.provider}_client_secret": ""})
        print(f"Removed the {name} sign-in app; the dashboard no longer offers Continue with {name}.")
        return 0
    link, steps = _oauth_guide(args.provider, settings)
    fields = [
        {"key": "client_id", "label": "Client ID", "link": link, "link_label": f"{name} console"},
        {"key": "client_secret", "label": "Client secret", "secret": True},
    ]
    if not args.prompt:
        print(f"\n{steps}\n\n{name} console: {link}", file=sys.stderr)
    values = _ask_values(args, f"{name} sign-in for Deployer", fields, steps)
    client_id, secret = (values.get("client_id") or "").strip(), (values.get("client_secret") or "").strip()
    if not client_id or not secret:
        raise CliError("Both the Client ID and the Client secret are needed; nothing was changed.")
    out = api.call(
        "PUT", "/instance/settings", {f"{args.provider}_client_id": client_id, f"{args.provider}_client_secret": secret}
    )
    if not out[args.provider]["configured"]:
        raise CliError(f"Saved, but Deployer doesn't report {name} as configured. Check: deployer oauth status")
    print(f"Saved. The sign-in page now offers Continue with {name}: {settings['public_url']}/login")
    return 0


def cmd_alerts(args) -> int:
    """`deployer alerts status|set|clear`: the Slack/Discord/any-https webhook alerts go to (docs/MONITORING.md)."""
    api = api_from_config(args)
    if args.action == "status":
        url = api.call("GET", "/instance/settings").get("alert_webhook_url")
        emit(
            args,
            {"alert_webhook": bool(url)},
            lambda d: print("Alert webhook: " + ("set" if d["alert_webhook"] else "not set")),
        )
        return 0
    if args.action == "clear":
        api.call("PUT", "/instance/settings", {"alert_webhook_url": ""})
        print("Removed the alert webhook; alerts show only in the dashboard now.")
        return 0
    steps = (
        "Paste an incoming-webhook URL that alerts are posted to. Slack: Apps -> Incoming Webhooks -> Add to a "
        "channel. Discord: Channel settings -> Integrations -> Webhooks -> New webhook -> Copy URL, then add "
        "/slack to its end."
    )
    fields = [{"key": "url", "label": "Webhook URL", "secret": True, "pattern": "^https://\\S+$"}]
    url = (_ask_values(args, "Alert webhook", fields, steps).get("url") or "").strip()
    if not url:
        print(NOTHING_ENTERED)
        return 0
    api.call("PUT", "/instance/settings", {"alert_webhook_url": url})
    print("Saved. Deployer posts alerts (app down, disk nearly full, failed backups, ...) there.")
    return 0


CLOUD_FIELDS = {
    "aws": (
        "In the AWS console (IAM -> Users) create a user for Deployer with the policy shown in Deployer under "
        "Settings -> Cloud, then Security credentials -> Create access key, and paste it here.",
        [
            {
                "key": "access_key_id",
                "label": "Access key ID",
                "placeholder": "AKIA...",
                "pattern": "^A[A-Z0-9]{15,39}$",
                "link": "https://console.aws.amazon.com/iam/home#/users",
                "link_label": "AWS IAM",
            },
            {"key": "secret_access_key", "label": "Secret access key", "secret": True},
            {"key": "region", "label": "Region", "placeholder": "ap-southeast-1"},
            {"key": "role_arn", "label": "Role ARN to assume", "optional": True},
        ],
    ),
    "firebase": (
        "In Google Cloud (IAM -> Service accounts) create a key for a service account with the roles shown in "
        "Deployer under Settings -> Cloud: Keys -> Add key -> JSON. Paste the whole downloaded file here.",
        [
            {
                "key": "service_account_json",
                "label": "Service account key (JSON)",
                "secret": True,
                "multiline": True,
                "link": "https://console.cloud.google.com/iam-admin/serviceaccounts",
                "link_label": "Service accounts",
            },
            {"key": "region", "label": "Region", "placeholder": "asia-southeast1", "optional": True},
        ],
    ),
}


def cmd_cloud(args) -> int:
    """`deployer cloud list | cloud add aws|firebase <name>`: cloud accounts (docs/CLOUD.md)."""
    api = api_from_config(args)
    if args.action == "list":
        out = api.call("GET", "/instance/cloud")
        rows = [
            [c.get("name", ""), c.get("provider", ""), c.get("project_id") or "all projects", c.get("status") or ""]
            for c in out.get("connections", [])
        ]
        emit(args, out, lambda _d: table(rows, ["NAME", "PROVIDER", "SCOPE", "STATUS"]))
        return 0
    if args.provider not in CLOUD_FIELDS or not args.name:
        raise CliError("Usage: deployer cloud add aws|firebase <name> [--project <project>]")
    steps, fields = CLOUD_FIELDS[args.provider]
    title = f"{'AWS' if args.provider == 'aws' else 'Firebase'} account for Deployer"
    values = {k: v.strip() for k, v in _ask_values(args, title, fields, steps).items() if v and v.strip()}
    if not values:
        print(NOTHING_ENTERED)
        return 0
    body: dict = {"provider": args.provider, "name": args.name, args.provider: values}
    if args.project:
        body["project_id"] = find_project(api, args.project)["id"]
    conn = api.call("POST", "/instance/cloud", body)
    print(f"Connected {conn.get('name', args.name)} ({args.provider}). Check it any time in Settings -> Cloud.")
    return 0


def _cloudflare_stale(args, api: Api) -> int:
    """`deployer cloudflare stale [--delete] [--yes]`: tunnel CNAMEs no Deployer hostname uses any more."""
    base = "/instance/remote-access/cloudflare/stale-records"
    records = api.call("GET", base).get("records", [])
    rows = [[r.get("hostname", ""), r.get("zone_name", ""), r.get("target", "")] for r in records]
    if not args.delete:
        emit(args, {"records": records}, lambda _d: table(rows, ["HOSTNAME", "ZONE", "TARGET"]))
        return 0
    if not records:
        emit(args, {"records": [], "deleted": [], "skipped": []}, lambda _d: print("No stale DNS records."))
        return 0
    if not args.json:
        table(rows, ["HOSTNAME", "ZONE", "TARGET"])
    if not args.yes:
        if not sys.stdin.isatty():
            raise CliError("Not deleting without a terminal to confirm in; add --yes to delete them anyway.")
        print(
            f"Delete {len(records)} record{'s' if len(records) != 1 else ''}? [y/N] ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        if sys.stdin.readline().strip().lower() not in ("y", "yes"):
            print("Nothing was deleted.", file=sys.stderr)
            return 1
    ids = [r["record_id"] for r in records]
    out: dict = {"records": records, "deleted": [], "skipped": []}
    for i in range(0, len(ids), 100):  # the API takes up to 100 per call
        part = api.call("POST", f"{base}/delete", {"record_ids": ids[i : i + 100]})
        out["deleted"] += part.get("deleted", [])
        out["skipped"] += part.get("skipped", [])

    def human(d):
        for r in d["deleted"]:
            print(f"Deleted {r.get('hostname')} ({r.get('zone_name')})")
        for r in d["skipped"]:
            why = "no longer stale" if r.get("reason") == "not_stale" else "already gone"
            print(f"Skipped {r.get('hostname') or r.get('record_id')}: {why}")
        print(f"{len(d['deleted'])} deleted, {len(d['skipped'])} skipped.")

    emit(args, out, human)
    return 0


def cmd_cloudflare(args) -> int:
    """`deployer cloudflare link|stale`: a Cloudflare API token for permanent addresses on your own domain,
    or leftover tunnel DNS records (docs/REMOTE_ACCESS.md)."""
    api = api_from_config(args)
    if args.action == "stale":
        return _cloudflare_stale(args, api)
    steps = (
        "In Cloudflare (My Profile -> API Tokens -> Create Token -> Custom token) give the token Account: "
        "Cloudflare Tunnel Edit, and Zone: DNS Edit and Zone: Zone Read for your domain. Paste it here with "
        "your Account ID (on the domain's Overview page, bottom right)."
    )
    fields = [
        {
            "key": "api_token",
            "label": "API token",
            "secret": True,
            "link": "https://dash.cloudflare.com/profile/api-tokens",
            "link_label": "Cloudflare API tokens",
        },
        {"key": "account_id", "label": "Account ID", "pattern": "^[A-Za-z0-9]+$"},
    ]
    values = {k: (v or "").strip() for k, v in _ask_values(args, "Cloudflare for Deployer", fields, steps).items()}
    if not values.get("api_token") or not values.get("account_id"):
        raise CliError("Both the API token and the Account ID are needed; nothing was changed.")
    api.call("POST", "/instance/remote-access/cloudflare/link", values)
    print("Linked Cloudflare. Add an address: deployer domain add <app> <hostname>")
    return 0


# --- main --------------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--url", help="Deployer's address (default: the one you signed in to, else this server)")
    common.add_argument("--json", action="store_true", help="print JSON")
    p = argparse.ArgumentParser(prog="deployer", description="Deployer from the command line (docs/CLI.md).")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser = functools.partial(sub.add_parser, parents=[common])  # every command takes --url / --json

    s = sub.add_parser("login", help="sign in by approving a code in the dashboard from any device")
    s.add_argument("--name", help="what the token is called in Account settings")
    s.add_argument("--local", action="store_true", help="no browser: create the token as root on this server")
    s.add_argument("--email", help="with --local: the account (default: the instance owner)")
    s.set_defaults(func=cmd_login)
    sub.add_parser("logout", help="revoke this token and forget it").set_defaults(func=cmd_logout)
    sub.add_parser("whoami", help="who the saved token signs in as").set_defaults(func=cmd_whoami)
    s = sub.add_parser("tokens", help="your command-line tokens")
    s.add_argument("--revoke", metavar="ID", help="revoke one")
    s.set_defaults(func=cmd_tokens)

    s = sub.add_parser("projects", help="list projects, or: projects create <name>")
    s.add_argument("action", nargs="?", choices=["list", "create"], default="list")
    s.add_argument("name", nargs="?")
    s.add_argument("--sql", action="store_true", help="with create: a managed MariaDB database")
    s.add_argument("--nosql", action="store_true", help="with create: a managed MongoDB database")
    s.set_defaults(func=cmd_projects)

    s = sub.add_parser("apps", help="list apps")
    s.add_argument("project", nargs="?")
    s.set_defaults(func=cmd_apps)

    s = sub.add_parser("app", help="app show|logs <app> | app create <project> --repo URL")
    asub = s.add_subparsers(dest="action", required=True)
    asub.add_parser = functools.partial(asub.add_parser, parents=[common])
    a = asub.add_parser("show")
    a.add_argument("app")
    a.set_defaults(func=cmd_app_show)
    a = asub.add_parser("create")
    a.add_argument("project")
    a.add_argument("--repo", required=True, help="https://github.com/owner/name")
    a.add_argument("--name")
    a.add_argument("--branch")
    a.add_argument("--root-dir")
    a.add_argument("--port", type=int, help="the port the app listens on")
    a.add_argument("--preset", choices=["static", "node", "python", "dockerfile"])
    a.add_argument("--install", help="install command (default: detected)")
    a.add_argument("--build", help="build command (default: detected)")
    a.add_argument("--start", help="start command (default: detected)")
    a.add_argument("--api-key", help="attach this project API key (name or id)")
    a.set_defaults(func=cmd_app_create)
    a = asub.add_parser("logs", help="the app's recent runtime logs")
    a.add_argument("app")
    a.add_argument("--tail", type=int, default=200)
    a.set_defaults(func=cmd_logs)

    s = sub.add_parser("deploy", help="deploy an app now")
    s.add_argument("app")
    s.add_argument("--branch")
    s.add_argument("--wait", action="store_true", help="stream the build log until it finishes")
    s.set_defaults(func=cmd_deploy)

    s = sub.add_parser("domain", help="domain add|remove <app> <hostname>")
    s.add_argument("action", choices=["add", "remove"])
    s.add_argument("app")
    s.add_argument("hostname")
    s.add_argument("--overwrite", action="store_true", help="replace an existing DNS record")
    s.set_defaults(func=cmd_domain)

    s = sub.add_parser("env", help="env list|set|unset <app> ...")
    s.add_argument("action", choices=["list", "set", "unset"])
    s.add_argument("app")
    s.add_argument("keys", nargs="*", help="NAME [value] for set; NAME... for unset")
    s.add_argument("--generate", action="store_true", help="set: a random hex value (like openssl rand -hex 32)")
    s.add_argument("--bytes", type=int, default=32, help="with --generate: random bytes (default 32 = 64 hex)")
    s.add_argument("--show", action="store_true", help="list: also print the values")
    s.add_argument("--prompt", action="store_true", help="set: type the value here (hidden) instead of on a web page")
    s.add_argument(
        "--stdin", action="store_true", help="set: read the value from stdin, however long the producer takes"
    )
    s.set_defaults(func=cmd_env)

    s = sub.add_parser("google-oauth", help="Google sign-in for apps: what to enter in Google's console, then save it")
    s.add_argument("apps", nargs="+")
    s.add_argument("--path", default="/auth/callback", help="the apps' callback path (default /auth/callback)")
    s.add_argument("--redirect", action="append", help="a redirect URI to list instead (repeatable)")
    s.add_argument("--id-var", default="GOOGLE_CLIENT_ID")
    s.add_argument("--secret-var", default="GOOGLE_CLIENT_SECRET")
    s.add_argument("--prompt", action="store_true", help="type the ID and secret here instead of on a web page")
    s.set_defaults(func=cmd_google_oauth)

    s = sub.add_parser("ask", help='ask "<title>" KEY[:secret]...: the owner types values on any device')
    s.add_argument("title")
    s.add_argument("fields", nargs="+", metavar="KEY[:secret]", help="a field; :secret hides it, :optional, :multiline")
    s.add_argument("--description", help="text shown above the fields")
    s.add_argument("--link", help="an https link shown as an Open button next to the first field")
    s.add_argument(
        "--app", action="append", help="store the values in this app's Environment (repeatable); prints keys only"
    )
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("google-apis", help="google-apis <api>... --app <app>: turn Google APIs on with your gcloud")
    s.add_argument("apis", nargs="+", metavar="API", help=f"{', '.join(GOOGLE_API_ALIASES)} or a full x.googleapis.com")
    s.add_argument("--app", help="the project of this app's Google Client ID")
    s.add_argument("--project", help="a Google Cloud project ID or number instead")
    s.add_argument("--id-var", default="GOOGLE_CLIENT_ID", help="the app's variable holding the Client ID")
    s.set_defaults(func=cmd_google_apis)

    s = sub.add_parser("webhook", help="webhook <app> [--rotate]: GitHub push webhook so a push deploys")
    s.add_argument("app")
    s.add_argument("--rotate", action="store_true", help="a new secret (also updates the hook on GitHub)")
    s.set_defaults(func=cmd_webhook)

    s = sub.add_parser(
        "oauth", help="oauth status|set|clear google|github: Deployer's own Google/GitHub sign-in (owner)"
    )
    s.add_argument("action", choices=["status", "set", "clear"])
    s.add_argument("provider", nargs="?", choices=["google", "github"])
    s.add_argument("--prompt", action="store_true", help="set: type the values here instead of on a web page")
    s.set_defaults(func=cmd_oauth)

    s = sub.add_parser("alerts", help="alerts status|set|clear: the webhook alerts are posted to (owner)")
    s.add_argument("action", choices=["status", "set", "clear"])
    s.add_argument("--prompt", action="store_true", help="set: type the URL here instead of on a web page")
    s.set_defaults(func=cmd_alerts)

    s = sub.add_parser("cloud", help="cloud list | cloud add aws|firebase <name>: cloud accounts (owner)")
    s.add_argument("action", choices=["list", "add"])
    s.add_argument("provider", nargs="?", choices=["aws", "firebase"])
    s.add_argument("name", nargs="?")
    s.add_argument("--project", help="add: only this project may use it (default: every project)")
    s.add_argument("--prompt", action="store_true", help="add: type the keys here instead of on a web page")
    s.set_defaults(func=cmd_cloud)

    s = sub.add_parser(
        "cloudflare",
        help="cloudflare link|stale: a Cloudflare API token for your own domain / leftover DNS records (owner)",
    )
    s.add_argument("action", choices=["link", "stale"])
    s.add_argument("--prompt", action="store_true", help="link: type the token here instead of on a web page")
    s.add_argument("--delete", action="store_true", help="stale: delete the listed records (asks first)")
    s.add_argument("--yes", action="store_true", help="stale --delete: do not ask (needed without a terminal)")
    s.set_defaults(func=cmd_cloudflare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
