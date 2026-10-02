"""The query shell sidecar (`query-shell` in deploy/docker-compose.yml, docs/QUERY_CONSOLE.md).

MongoDB code from the query console runs in a real `mongosh`, i.e. with full Node.js. It never runs
in the API or worker containers (they hold MASTER_KEY, JWT_SECRET and the root database passwords):
they POST `{uri, database, code, batch, marker, timeout_seconds}` to this small HTTP server, which
runs the shell and answers `{returncode, stdout, stderr, timed_out, output_capped, duration_ms}`.

The container (same image as the API, `python -m app.shell_runner`) has no Deployer environment, no
volumes and no Docker socket, a read-only root filesystem, a memory/CPU/pids cap, and sits only on
the `query` network (api, worker, mongodb) plus an egress network for external MongoDB servers. This
server runs as root with every capability dropped except the ones needed to start each shell under
its own slot uid (`SLOT_UIDS`, created in api/Dockerfile) and clean up after it, so one run cannot
read another run's connection string (/proc/<pid>/environ, memory) or leave a process behind to watch
the next one: after every run all processes of the slot uid are killed and its files in /tmp and
/dev/shm removed; a slot whose processes cannot all be killed is retired, never reused. Elsewhere
(unit tests, development) every shell runs as the current user.

- Execution: `mongosh --nodb --quiet --norc --eval WRAPPER_JS` with a private temporary directory as
  HOME and cwd; URI, code file and marker reach the shell only through its environment (never argv),
  the process is killed at the timeout and when its output passes the caps; at most `MAX_SHELLS` run
  at once (more: 429).
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PORT = 8090
SLOT_UIDS = (20001, 20002, 20003, 20004)  # api/Dockerfile creates these users (and same-id groups)
MAX_SHELLS = len(SLOT_UIDS)
MAX_SHELL_STDOUT = 8 * 1024 * 1024
MAX_SHELL_STDERR = 1024 * 1024
MAX_TIMEOUT_SECONDS = 120
MAX_REQUEST_BYTES = 4 * 1024 * 1024
SWEPT_DIRS = ("/tmp", "/dev/shm")  # the writable places of the read-only container
PROC = "/proc"
KILL_ROUNDS = 50  # x KILL_WAIT_SECONDS: how long a slot's processes get to die before it is retired
KILL_WAIT_SECONDS = 0.1

# The wrapper passed with `--eval` (docs/QUERY_CONSOLE.md). Everything variable comes from the
# environment; it is deleted before the user's code runs. The user's code is evaluated through the
# shell's own evaluator (`MongoshNodeRepl.loadExternalCode`, what `load()` uses, so the async
# rewriter applies) and the raw result is turned into its printable form with the shell's
# `asPrintable` hook - for cursors that is the first `displayBatchSize` documents. An async IIFE
# because `--eval` scripts may not use top-level `await`; the shell awaits a Promise result before
# it prints (nothing, for undefined) and exits. Verified against mongosh 2.11.1
# (tests/integration/test_query_console.py).
WRAPPER_JS = """(async () => {
  const env = process.env;
  const marker = String(env.DEPLOYER_QUERY_MARKER || "");
  const emit = (obj) => { process.stdout.write(marker + EJSON.stringify(obj, { relaxed: true }) + "\\n"); };
  const describe = (e) => ({
    name: e && e.name ? String(e.name) : "Error",
    message: e && e.message !== undefined ? String(e.message) : String(e),
    code: e && e.code !== undefined ? e.code : null,
    codeName: e && e.codeName ? String(e.codeName) : null,
  });
  const file = env.DEPLOYER_QUERY_FILE;
  const uri = env.DEPLOYER_QUERY_URI;
  const dbName = env.DEPLOYER_QUERY_DB;
  const batch = parseInt(env.DEPLOYER_QUERY_BATCH, 10);
  delete env.DEPLOYER_QUERY_URI;
  delete env.DEPLOYER_QUERY_FILE;
  delete env.DEPLOYER_QUERY_MARKER;
  let code = null;
  let connected = false;
  try {
    code = require("fs").readFileSync(file, "utf8");
    await config.set("displayBatchSize", batch);
    db = (await connect(uri)).getSiblingDB(dbName);
    connected = true;
  } catch (e) {
    emit({ phase: "connect", error: describe(e) });
  }
  if (connected) {
    const listener = db.getMongo()._instanceState.evaluationListener;
    try {
      let raw = await listener.loadExternalCode(code, "@(query)");
      if (raw !== null && raw !== undefined && typeof raw.then === "function") raw = await raw;
      const asPrintable = Symbol.for("@@mongosh.asPrintable");
      let value = raw;
      if (raw !== null && raw !== undefined && (typeof raw === "object" || typeof raw === "function")
          && typeof raw[asPrintable] === "function") {
        value = await raw[asPrintable]();
      }
      if (value !== null && typeof value === "object" && !Array.isArray(value)
          && Array.isArray(value.documents) && typeof value.cursorHasMore === "boolean") {
        value = value.documents;  // CursorIterationResult: the first batch of a cursor
      }
      emit({ phase: "done", value: value === undefined ? null : value });
    } catch (e) {
      emit({ phase: "error", error: describe(e) });
    }
  }
})();
"""


class RunError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def mongosh_command() -> list[str] | None:
    """The mongosh executable as an argv prefix, or None when it is not installed (tests replace it)."""
    path = shutil.which("mongosh")
    return [path] if path else None


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _kill(proc: subprocess.Popen) -> None:
    try:
        proc.kill()
    except OSError:
        pass


def _as_uid(uid: int | None) -> dict[str, Any]:
    return {} if uid is None else {"user": uid, "group": uid, "extra_groups": []}


def _run_process(args: list[str], env: dict[str, str], timeout_seconds: int, cwd: str, uid: int | None) -> dict:
    """Runs the shell with a hard timeout (kill) and output caps (kill when exceeded)."""
    started = time.monotonic()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            **_as_uid(uid),
        )
    except OSError as exc:
        raise RunError(501, "mongosh_unavailable", f"The MongoDB shell could not be started: {exc}") from exc
    capped = threading.Event()

    def pump(stream: Any, limit: int, sink: list[bytes]) -> None:
        total = 0
        try:
            while True:
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    return
                if total < limit:
                    sink.append(chunk[: limit - total])
                total += len(chunk)
                if total > limit and not capped.is_set():
                    capped.set()
                    _kill(proc)
        except OSError:
            return

    out: list[bytes] = []
    err: list[bytes] = []
    threads = [
        threading.Thread(target=pump, args=(proc.stdout, MAX_SHELL_STDOUT, out), daemon=True),
        threading.Thread(target=pump, args=(proc.stderr, MAX_SHELL_STDERR, err), daemon=True),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    try:
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(proc)
            proc.wait()
        for thread in threads:
            thread.join(timeout=5)
    finally:
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
    return {
        "returncode": proc.returncode,
        "stdout": b"".join(out).decode("utf-8", "replace"),
        "stderr": b"".join(err).decode("utf-8", "replace"),
        "timed_out": timed_out,
        "output_capped": capped.is_set(),
        "duration_ms": _ms(started),
    }


def _child_env(home: str, values: dict[str, str]) -> dict[str, str]:
    """A minimal environment: nothing of this process reaches the shell."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": home,
        "TMPDIR": home,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        **values,
    }
    if os.name == "nt":  # development on Windows: python (fake shell) and Node resolve their home from these
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        env.update(USERPROFILE=home, APPDATA=home, LOCALAPPDATA=home, TEMP=home, TMP=home)
    return env


def _slot_pids(uid: int) -> list[int]:
    """The live (non-zombie) processes whose real, effective, saved or fs uid is the slot uid, read
    from /proc: no process is started, so this works with the pid budget used up (V-01)."""
    pids = []
    for name in [name for name in os.listdir(PROC) if name.isdigit()]:  # OSError: caller fails closed
        try:
            with open(os.path.join(PROC, name, "status"), encoding="utf-8", errors="replace") as fh:
                fields = dict(line.split(":", 1) for line in fh if ":" in line)
            if not fields.get("State", "").strip().startswith("Z") and str(uid) in fields.get("Uid", "").split():
                pids.append(int(name))
        except (OSError, ValueError):
            pass  # exited meanwhile
    return pids


def _clean_up_slot(uid: int) -> bool:
    """Kills every process of the slot uid (a script may have left one running to watch the next run)
    and removes its files. True only when no process of the uid is left. The kill is a /proc scan and
    os.kill from this process, never a new process: a script that used up pids_limit would make that
    fork fail and leave its watcher alive (V-01). Repeated, since a process may fork while we kill."""
    clean = False
    for _ in range(KILL_ROUNDS):
        try:
            pids = _slot_pids(uid)
        except OSError:
            break  # /proc unreadable: not verifiably clean
        if not pids:
            clean = True
            break
        for pid in pids:
            try:
                os.kill(pid, 9)  # SIGKILL (the name is missing on Windows, where the unit tests run)
            except OSError:
                pass
        time.sleep(KILL_WAIT_SECONDS)
    for base in SWEPT_DIRS:
        try:
            entries = list(os.scandir(base))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.stat(follow_symlinks=False).st_uid != uid:
                    continue
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path, ignore_errors=True)
                else:
                    os.unlink(entry.path)
            except OSError:
                pass
    return clean


def _field(body: dict, key: str, kind: type) -> Any:
    value = body.get(key)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise RunError(400, "validation_error", f"{key} must be a {kind.__name__}")
    return value


class Runner:
    """Runs shells in slots: a slot uid each when `isolate` (the sidecar, as root), else as this user."""

    def __init__(self, isolate: bool) -> None:
        self.slots: queue.SimpleQueue[int | None] = queue.SimpleQueue()
        for uid in SLOT_UIDS:
            self.slots.put(uid if isolate else None)

    def run(self, body: dict) -> dict:
        uri = _field(body, "uri", str)
        database = _field(body, "database", str)
        code = _field(body, "code", str)
        marker = _field(body, "marker", str)
        batch = _field(body, "batch", int)
        timeout_seconds = max(1, min(_field(body, "timeout_seconds", int), MAX_TIMEOUT_SECONDS))
        command = mongosh_command()
        if not command:
            raise RunError(501, "mongosh_unavailable", "The MongoDB shell (mongosh) is not installed in this image")
        try:
            uid = self.slots.get_nowait()
        except queue.Empty as exc:
            message = "Too many MongoDB shell queries are running; try again in a moment"
            raise RunError(429, "too_many_queries", message) from exc
        home = None
        try:
            home = tempfile.mkdtemp(prefix="deployer-query-")
            code_path = os.path.join(home, "query.js")
            fd = os.open(code_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(code)
            if uid is not None:
                os.chown(code_path, uid, uid)
                os.chown(home, uid, uid)
            env = _child_env(
                home,
                {
                    "DEPLOYER_QUERY_URI": uri,
                    "DEPLOYER_QUERY_DB": database,
                    "DEPLOYER_QUERY_FILE": code_path,
                    "DEPLOYER_QUERY_MARKER": marker,
                    "DEPLOYER_QUERY_BATCH": str(batch),
                },
            )
            args = [*command, "--nodb", "--quiet", "--norc", "--eval", WRAPPER_JS]
            return _run_process(args, env, timeout_seconds, home, uid)
        finally:
            # The slot's processes are killed (and `home`, which belongs to the slot uid, removed)
            # before the slot is reused; one with a process left would let it read the next run's
            # connection string from /proc/<pid>/environ, so it is retired instead (V-01).
            reusable = uid is None or _clean_up_slot(uid)
            if home:
                shutil.rmtree(home, ignore_errors=True)
            if reusable:
                self.slots.put(uid)
            else:
                print(f"query shell: slot uid {uid} retired, its processes could not be killed", file=sys.stderr)


def make_server(host: str, port: int, runner: Runner) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            try:
                if self.path != "/run":
                    raise RunError(404, "not_found", "Unknown path")
                header = self.headers.get("Content-Length") or ""
                length = int(header) if header.isdigit() else 0
                if not 0 < length <= MAX_REQUEST_BYTES:
                    raise RunError(413, "validation_error", "The request is empty or too large")
                try:
                    body = json.loads(self.rfile.read(length))
                except ValueError as exc:
                    raise RunError(400, "validation_error", "The request is not JSON") from exc
                if not isinstance(body, dict):
                    raise RunError(400, "validation_error", "The request must be a JSON object")
                self._reply(200, runner.run(body))
            except RunError as exc:
                self._reply(exc.status, {"code": exc.code, "message": exc.message})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - quiet: one line per query is noise
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    isolate = hasattr(os, "geteuid") and os.geteuid() == 0
    print(f"query shell listening on :{PORT} (slot uids: {isolate})", file=sys.stderr, flush=True)
    make_server("0.0.0.0", PORT, Runner(isolate)).serve_forever()  # noqa: S104 - container network only


if __name__ == "__main__":
    main()
