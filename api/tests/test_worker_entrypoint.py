"""The worker is started with `python -m app.worker` in Docker; plugins register background tasks by
importing `app.worker`. Both must end up on the same module object or the tasks silently never run."""

import runpy


def test_python_m_entrypoint_hands_off_to_canonical_module(monkeypatch):
    import app.worker as canonical

    calls: list[str] = []
    monkeypatch.setattr(canonical, "main", lambda: calls.append("main"))

    # Same as `python -m app.worker`: the file executes under the name `__main__`.
    runpy.run_module("app.worker", run_name="__main__", alter_sys=True)

    assert calls == ["main"]


def test_device_worker_plugin_registers_tasks_on_canonical_module(monkeypatch):
    import app.worker as canonical
    from app.services import device_executor, device_worker

    registry: list = []
    monkeypatch.setattr(canonical, "_tasks", registry)

    try:
        # Importing the plugin already ran install() once; run it again against the patched registry.
        device_worker.install()
        assert {name for name, _ in registry} >= {"device-agent", "device-maintenance"}
    finally:
        # install() also registers the device backup executor globally; undo that for later tests.
        device_executor.unregister()
