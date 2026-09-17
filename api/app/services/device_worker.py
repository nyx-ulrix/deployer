"""Host-device work inside `python -m app.worker` (docs/DEVICES.md).

Loaded as a worker plugin: `WORKER_PLUGINS=app.services.device_worker`. Importing this module

- registers the device backup executor, remote job dispatcher and copy target (so backup jobs for
  device-hosted sources work in the worker process), and
- registers two background tasks with `app.worker.register_background_task`:
  - `device-agent`: the outbound connection to the main Deployer; it idles until this installation
    has a `device_link` (so the same worker image works on main servers and devices);
  - `device-maintenance`: every minute, drops old copies of moved databases whose keep period ended
    and deletes expired transfer files (main server side).
"""

from __future__ import annotations

import asyncio
import logging
import threading

log = logging.getLogger(__name__)

MAINTENANCE_SECONDS = 60


def agent_task(stop: threading.Event) -> None:
    from app.services import device_agent

    async def main() -> None:
        async_stop = asyncio.Event()

        async def bridge() -> None:
            while not stop.is_set():
                await asyncio.sleep(1)
            async_stop.set()

        bridge_task = asyncio.create_task(bridge())
        try:
            await device_agent.run_agent(async_stop)
        finally:
            bridge_task.cancel()

    asyncio.run(main())


def maintenance_task(stop: threading.Event) -> None:
    from app.services import device_moves, device_rpc

    while not stop.is_set():
        try:
            device_moves.run_due_cleanups()
            device_rpc.cleanup_transfers()
        except Exception:  # noqa: BLE001
            log.warning("device maintenance failed", exc_info=True)
        stop.wait(MAINTENANCE_SECONDS)


def install() -> None:
    from app.services import device_executor

    device_executor.register()
    try:
        from app import worker
    except Exception:  # noqa: BLE001
        log.warning("worker module unavailable; device agent not started", exc_info=True)
        return
    names = {name for name, _ in getattr(worker, "_tasks", [])}
    if "device-agent" not in names:
        worker.register_background_task("device-agent", agent_task)
    if "device-maintenance" not in names:
        worker.register_background_task("device-maintenance", maintenance_task)


install()
