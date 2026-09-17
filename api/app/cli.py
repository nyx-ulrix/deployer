"""Local administration commands, run inside the api container.

    python -m app.cli device status            # link, connection state, hosted databases
    python -m app.cli device detach [--force]  # forget the main Deployer (emergency local detach)

`device detach` refuses while this device still hosts databases unless `--force` is given. Forced
detach keeps the hosted databases and their credentials on this machine (nothing is dropped); the
main Deployer will show the device as offline until its owner removes it there.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.db import get_sessionmaker
from app.services import device_agent, device_host


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="group", required=True)
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
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
