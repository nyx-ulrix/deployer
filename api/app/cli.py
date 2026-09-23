"""Local administration commands, run inside the api container.

    python -m app.cli device status            # link, connection state, hosted databases
    python -m app.cli device detach [--force]  # forget the main Deployer (emergency local detach)
    python -m app.cli oauth status             # sign-in apps: client IDs, secret set?, callback URLs (JSON)
    python -m app.cli oauth set --provider google|github   # JSON {"client_id", "client_secret"} on stdin
    python -m app.cli oauth clear --provider google|github

`device detach` refuses while this device still hosts databases unless `--force` is given. Forced
detach keeps the hosted databases and their credentials on this machine (nothing is dropped); the
main Deployer will show the device as offline until its owner removes it there.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db import get_sessionmaker
from app.errors import ApiError
from app.services import audit, device_agent, device_host, instance_settings
from app.services.instance_settings import validate_oauth_value

PROVIDERS = ("google", "github")


def _status() -> int:
    session = get_sessionmaker()()
    try:
        link = device_host.load_link(session)
        hosted = device_host.hosted_summary(session)
    finally:
        session.close()
    agent = device_agent.read_status() if link else {}
    out = {
        "mode": "host" if link else "standalone",
        "primary_url": link.get("primary_url") if link else None,
        "device_id": link.get("device_id") if link else None,
        "device_name": link.get("device_name") if link else None,
        "connected": bool(agent.get("connected")),
        "last_error": agent.get("last_error"),
        "last_connected_at": agent.get("last_connected_at"),
        "hosted_sources": hosted,
    }
    print(json.dumps(out, indent=2))
    return 0


def _detach(force: bool) -> int:
    session = get_sessionmaker()()
    try:
        link = device_host.load_link(session)
        if not link:
            print("This installation is not attached to a main Deployer.")
            return 0
        hosted = device_host.load_credentials(session)
        if hosted and not force:
            print(
                f"This device still hosts {len(hosted)} database(s): {', '.join(sorted(hosted))}.\n"
                "Move them to another host from the main Deployer first, or run with --force to detach anyway "
                "(the databases stay on this machine but the main Deployer can no longer reach them).",
                file=sys.stderr,
            )
            return 2
        device_host.clear_link(session)
        session.commit()
    finally:
        session.close()
    device_agent.write_status(mode="standalone", connected=False, last_error=None)
    print(f"Detached from {link.get('primary_url')}. The device agent disconnects within a few seconds.")
    if hosted:
        print(f"Kept {len(hosted)} hosted database(s) and their credentials on this machine.")
    return 0


def _oauth_status() -> int:
    session = get_sessionmaker()()
    try:
        out = {"public_url": instance_settings.public_url(session)}
        for provider in PROVIDERS:
            app = instance_settings.oauth_app(session, provider)
            out[provider] = {
                "client_id": app.client_id or None,
                "has_secret": bool(app.client_secret),
                "configured": app.configured,
                "callback_url": instance_settings.oauth_callback_url(session, provider),
            }
    finally:
        session.close()
    print(json.dumps(out, indent=2))
    return 0


def _oauth_write(provider: str, values: dict[str, str | None]) -> None:
    session = get_sessionmaker()()
    try:
        for key, value in values.items():
            instance_settings.set_value(session, f"{provider}_{key}", value)
        audit.record(session, "instance.settings_update", source="cli", keys=[f"{provider}_{k}" for k in values])
        session.commit()
    finally:
        session.close()


def _oauth_set(provider: str) -> int:
    """Reads {"client_id", "client_secret"} JSON from stdin (never argv). An empty secret keeps the stored one.
    Errors are one line on stdout with exit code 2, for the Control app to show."""
    try:
        # Bytes, not text: json detects the UTF-8 BOM that Windows' .NET stdin writer may prepend.
        data = json.loads(sys.stdin.buffer.read() or b"null")
    except ValueError:
        data = None
    if not isinstance(data, dict):
        print('Expected JSON on stdin: {"client_id": "...", "client_secret": "..."}')
        return 2
    try:
        values = {"client_id": validate_oauth_value(f"{provider}_client_id", str(data.get("client_id") or ""))}
        secret = validate_oauth_value(f"{provider}_client_secret", str(data.get("client_secret") or ""))
    except ApiError as exc:
        print(exc.message)
        return 2
    if not values["client_id"]:
        print("The Client ID is required.")
        return 2
    if secret:
        values["client_secret"] = secret
    elif not _stored_secret(provider):
        print("The Client secret is required.")
        return 2
    _oauth_write(provider, values)
    print(f"Saved the {provider} sign-in app.")
    return 0


def _stored_secret(provider: str) -> bool:
    session = get_sessionmaker()()
    try:
        return bool(instance_settings.oauth_app(session, provider).client_secret)
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="group", required=True)
    oauth = sub.add_parser("oauth", help="Google/GitHub sign-in apps")
    oauth_sub = oauth.add_subparsers(dest="command", required=True)
    oauth_sub.add_parser("status", help="show client IDs, whether secrets are set, and the callback URLs")
    for name, help_ in (("set", "store a client ID/secret read as JSON from stdin"), ("clear", "remove the app")):
        cmd = oauth_sub.add_parser(name, help=help_)
        cmd.add_argument("--provider", required=True, choices=PROVIDERS)
    device = sub.add_parser("device", help="host device commands")
    device_sub = device.add_subparsers(dest="command", required=True)
    device_sub.add_parser("status", help="show the host device link and hosted databases")
    detach = device_sub.add_parser("detach", help="forget the main Deployer on this machine")
    detach.add_argument("--force", action="store_true", help="detach even while databases are hosted here")
    args = parser.parse_args(argv)
    if args.group == "device" and args.command == "status":
        return _status()
    if args.group == "device" and args.command == "detach":
        return _detach(args.force)
    if args.group == "oauth" and args.command == "status":
        return _oauth_status()
    if args.group == "oauth" and args.command == "set":
        return _oauth_set(args.provider)
    if args.group == "oauth" and args.command == "clear":
        _oauth_write(args.provider, {"client_id": None, "client_secret": None})
        print(f"Removed the {args.provider} sign-in app.")
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
