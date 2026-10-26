#!/usr/bin/env python3
"""The `deployer` command line for everyday work, no browser and no sudo needed (docs/CLI.md).

    deployer login                 # prints a link + code; approve it on any device through the public URL
    deployer apps                  # every app you can see
    deployer env set kanban GOOGLE_CLIENT_SECRET      # asks for the value with hidden input
    deployer env set kanban SESSION_SECRET --generate # random 64-hex value, never printed

`deployer.sh` hands these commands here before its sudo re-run; the server-management commands
(status, update, ...) stay in deployer.sh. Python 3.9+ standard library only, so the same file works
on a laptop: `python3 deployer_cli.py login --url https://deployer.example.com`.
"""

from __future__ import annotations

import argparse
import functools
import getpass
import json
import os
import platform
import secrets
import socket
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


def _home() -> Path:
    # `sudo deployer login --local` writes the token for the person who ran sudo, not for root.
    user = os.environ.get("SUDO_USER")
    if os.geteuid() == 0 and user and user != "root":
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
    if os.geteuid() == 0 and user and user != "root":
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

    def call(self, method: str, path: str, body: dict | None = None, *, auth: bool = True):
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise self._error(exc) from None
        except urllib.error.URLError as exc:
            raise CliError(f"Can't reach Deployer at {self.url}: {exc.reason}") from None
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
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip())


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


# --- lookups -----------------------------------------------------------------------------------


def _match(items: list[dict], ref: str, what: str, keys=("id", "slug", "name")) -> dict:
    ref_l = ref.lower()
    hits = [i for i in items if any(str(i.get(k) or "").lower() == ref_l for k in keys)]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise CliError(f"No {what} called '{ref}'.")
    names = ", ".join(f"{h.get('_project', '')}{'/' if h.get('_project') else ''}{h.get('slug') or h['id']}" for h in hits)
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
    if os.geteuid() != 0:
        cmd = ["sudo", "deployer", "login", "--local"] + (["--email", args.email] if args.email else [])
        os.execvp("sudo", cmd)
    cmd = ["deployer", "cli-token", "--json"] + ([args.email] if args.email else [])
    env = {**os.environ, "DEPLOYER_CLI_TOKEN_NAME": args.name or f"deployer CLI on {socket.gethostname()} (local)"}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise CliError((result.stdout + result.stderr).strip().splitlines()[-1] if result.stdout + result.stderr else "failed")
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
            [[r["id"], r["name"], r["prefix"] + "...", r["last_used_at"] or "never", "this one" if r["current"] else ""] for r in rs],
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
        print(f"  push deploy: {'on (webhook)' if gh and gh.get('hook_active') else 'off - connect GitHub in Account settings'}")

    emit(args, app, human)
    return 0


def cmd_app_create(args) -> int:
    api = api_from_config(args)
    project = find_project(api, args.project)
    base = f"/projects/{project['id']}/apps"
    draft = api.call("POST", base + "/detect", {"repo_url": args.repo, **({"branch": args.branch} if args.branch else {})})
    for w in draft.get("warnings") or []:
        print(f"warning: {w}", file=sys.stderr)
    fields = (
        "name", "repo_url", "branch", "root_dir", "preset", "install_command",
        "build_command", "start_command", "output_dir", "container_port",
    )
    body = {k: draft.get(k) for k in fields if draft.get(k) is not None}
    for key, value in (("name", args.name), ("root_dir", args.root_dir), ("container_port", args.port), ("preset", args.preset)):
        if value:
            body[key] = value
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
                raise CliError(f"{args.hostname} already has a DNS record. Run again with --overwrite to replace it.") from None
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
    if len(args.keys) != 1 and not (len(args.keys) == 2 and not args.generate):
        raise CliError("Usage: deployer env set <app> NAME [value | --generate | --stdin]")
    key = args.keys[0]
    if args.generate:
        value = secrets.token_hex(args.bytes)
    elif len(args.keys) == 2:
        value = args.keys[1]
        print("note: a value on the command line is kept in your shell history; leave it out to be asked.", file=sys.stderr)
    else:
        value = ask_secret(f"{key} for {app['slug']} (hidden)")
    out = api.call("PATCH", app_path(app), {"env_set": {key: value}})
    shown = "a new random value (not shown)" if args.generate else "the value"
    print(f"Set {key} to {shown}. {_apply_hint(args.app, out)}")
    return 0


def _apply_hint(ref: str, app: dict) -> str:
    if app.get("env_deployment_id"):
        return "The live app is being republished with it."
    return f"It applies at the next deploy: deployer deploy {ref}"


# --- commands: Google sign-in for an app -------------------------------------------------------


def cmd_google_oauth(args) -> int:
    """Google has no API for creating OAuth web clients: this prints exactly what to enter in its console
    (from any device), then stores the ID and secret in each app's environment with hidden input."""
    api = api_from_config(args)
    apps = [find_app(api, ref) for ref in args.apps]
    uris = list(args.redirect or [])
    for app in apps:
        hosts = [d["hostname"] for d in app.get("domains") or [] if d.get("status") == "active"]
        if not hosts and not args.redirect:
            raise CliError(f"{app['slug']} has no hostname yet: deployer domain add {app['slug']} <hostname> first, or pass --redirect.")
        uris += [f"https://{h}{args.path}" for h in hosts]
    print("\n1. Open https://console.cloud.google.com/auth/clients/create on any device")
    print("   (first time: also fill in Branding, and under Audience choose External and Publish app).")
    print("2. Application type: Web application. Add these Authorized redirect URIs:\n")
    for uri in dict.fromkeys(uris):
        print(f"     {uri}")
    print("\n3. Create, then copy the Client ID and Client secret (Google shows the secret only once).\n")
    client_id = input("Client ID: ").strip() if sys.stdin.isatty() else sys.stdin.readline().strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise CliError("That doesn't look like a Google Client ID (it ends in .apps.googleusercontent.com).")
    secret = ask_secret("Client secret (hidden)")
    for app in apps:
        api.call("PATCH", app_path(app), {"env_set": {args.id_var: client_id, args.secret_var: secret}})
        print(f"Saved {args.id_var} and {args.secret_var} on {app['_project']}/{app['slug']}.")
    print("They apply at each app's next deploy (deployer deploy <app>).")
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
    s.set_defaults(func=cmd_env)

    s = sub.add_parser("google-oauth", help="Google sign-in for apps: what to enter in Google's console, then save it")
    s.add_argument("apps", nargs="+")
    s.add_argument("--path", default="/auth/callback", help="the apps' callback path (default /auth/callback)")
    s.add_argument("--redirect", action="append", help="a redirect URI to list instead (repeatable)")
    s.add_argument("--id-var", default="GOOGLE_CLIENT_ID")
    s.add_argument("--secret-var", default="GOOGLE_CLIENT_SECRET")
    s.set_defaults(func=cmd_google_oauth)
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
