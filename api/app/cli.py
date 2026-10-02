"""Local administration commands, run inside the api container.

    python -m app.cli device status            # link, connection state, hosted databases
    python -m app.cli device detach [--force]  # forget the main Deployer (emergency local detach)
    python -m app.cli oauth status             # sign-in apps: client IDs, secret set?, callback URLs (JSON)
    python -m app.cli oauth set --provider google|github   # JSON {"client_id", "client_secret"} on stdin
    python -m app.cli oauth clear --provider google|github
    python -m app.cli user reset-password [--email E]  # JSON {"password"} on stdin; no --email = the owner
    python -m app.cli platform list                # platform snapshots, newest first (JSON)
    python -m app.cli platform restore --yes [--backup-id ID]  # default: the newest snapshot

`device detach` refuses while this device still hosts databases unless `--force` is given. Forced
detach keeps the hosted databases and their credentials on this machine (nothing is dropped); the
main Deployer will show the device as offline until its owner removes it there.

`user reset-password` is the forgotten-password recovery: only someone with access to this PC can run
it. It signs that account out everywhere and clears the sign-in rate limits (a locked-out user can sign
in at once).

`platform restore` loads a daily platform snapshot (users, projects, settings) back into the platform
database after snapshotting the current data first (docs/BACKUPS.md "Restoring platform data").
"""

from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.errors import ApiError
from app.models import User
from app.serializers import iso
from app.services import audit, backups, device_agent, device_host, instance_settings, rate_limit, tokens
from app.services.instance_settings import validate_oauth_value
from app.services.passwords import hash_password, normalize_email, validate_password

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
        "rejected": bool(agent.get("rejected")),
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
        from app.services import device_apps

        try:
            device_apps.remove_all()
        except Exception as exc:  # noqa: BLE001 - Docker or the tunnel sidecar may be down
            print(f"Could not stop this PC's co-hosted apps and apps tunnel: {exc}", file=sys.stderr)
            if not force:
                print("Fix that and try again, or run with --force to detach anyway.", file=sys.stderr)
                return 2
        device_host.clear_link(session)
        session.commit()
    finally:
        session.close()
    device_agent.write_status(mode="standalone", connected=False, last_error=None, rejected=False)
    print(f"Detached from {link.get('primary_url')}. The device agent disconnects within a few seconds.")
    if hosted:
        print(f"Kept {len(hosted)} hosted database(s) and their credentials on this machine.")
    return 0


def _read_json_stdin() -> object:
    try:
        # Bytes, not text: json detects the UTF-8 BOM that Windows' .NET stdin writer may prepend.
        return json.loads(sys.stdin.buffer.read() or b"null")
    except ValueError:
        return None


def _reset_password(email: str | None) -> int:
    """Reads {"password"} JSON from stdin (never argv). Errors are one line on stdout with exit code 2."""
    data = _read_json_stdin()
    password = data.get("password") if isinstance(data, dict) else None
    if not isinstance(password, str):
        print('Expected JSON on stdin: {"password": "..."}')
        return 2
    try:
        validate_password(password)
    except ApiError as exc:
        print(exc.message)
        return 2
    session = get_sessionmaker()()
    try:
        if email:
            user = session.scalar(select(User).where(func.lower(User.email) == normalize_email(email)))
            if user is None:
                print(f"No account uses the email {email.strip()}.")
                return 2
        else:
            owners = session.scalars(select(User).where(User.is_instance_owner.is_(True))).all()
            if len(owners) != 1:
                print("Enter the account's email." if owners else "Deployer has no owner account yet.")
                return 2
            user = owners[0]
        if not user.is_active:  # sign-in refuses it whatever the password, so a "success" would mislead
            print(f"{user.email} is disabled. The owner enables it again in Instance settings -> Users first.")
            return 2
        user.password_hash = hash_password(password)
        tokens.revoke_user_tokens(session, user.id)
        audit.record(session, "auth.password_change", user_id=user.id, kind="reset", source="cli")
        session.commit()
        rate_limit.reset_logins()
        print(f"Password reset for {user.email}. Sign in with the new password; other sessions were signed out.")
    finally:
        session.close()
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
    data = _read_json_stdin()
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


def _platform_list() -> int:
    session = get_sessionmaker()()
    try:
        rows = [
            {"id": b.id, "started_at": iso(b.started_at), "trigger": b.trigger, "size_bytes": b.size_bytes}
            for b in backups.platform_backups(session)
        ]
    finally:
        session.close()
    print(json.dumps(rows, indent=2))
    return 0


def _platform_restore(backup_id: str | None, yes: bool) -> int:
    if not yes:
        print(
            "This replaces all platform data (users, projects, settings) with a snapshot; anything changed since "
            "is forgotten. The current data is snapshotted first. Run again with --yes to go ahead."
        )
        return 2
    try:
        out = backups.restore_platform(get_sessionmaker(), backup_id)
    except ApiError as exc:
        print(exc.message)
        return 2
    print(
        f"Restored the platform snapshot from {out['restored']['started_at']}. The data from before is kept as "
        f"snapshot {out['safety_backup_id']}. Restart Deployer now."
    )
    return 0


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
    user = sub.add_parser("user", help="account recovery")
    user_sub = user.add_subparsers(dest="command", required=True)
    reset = user_sub.add_parser("reset-password", help='set a new password, read as JSON {"password"} from stdin')
    reset.add_argument("--email", help="the account to reset (default: the instance owner)")
    platform = sub.add_parser("platform", help="platform data snapshots")
    platform_sub = platform.add_subparsers(dest="command", required=True)
    platform_sub.add_parser("list", help="list platform snapshots, newest first")
    restore = platform_sub.add_parser(
        "restore", help="load a platform snapshot back (snapshots the current data first)"
    )
    restore.add_argument("--backup-id", help="the snapshot to restore (default: the newest)")
    restore.add_argument("--yes", action="store_true", help="confirm replacing the platform data")
    args = parser.parse_args(argv)
    if args.group == "platform":
        return _platform_list() if args.command == "list" else _platform_restore(args.backup_id, args.yes)
    if args.group == "user" and args.command == "reset-password":
        return _reset_password(args.email)
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
