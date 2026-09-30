"""The worker's Docker / git interface for app deployments (docs/DEPLOYMENTS.md).

Everything that touches the Docker socket or a Git remote goes through `DockerCli` so the deploy
job can be tested end to end against a fake. Rules:

- subprocess argv only, never a shell; user-supplied strings are arguments, not command text;
- secrets (the repository token) travel in the environment (a git credential helper), never in argv,
  URLs or captured output, which is redacted with `connections.redact` before anyone sees it;
- captured output is capped (`MAX_OUTPUT`) so a chatty build can't exhaust the worker's memory.
"""

from __future__ import annotations

import json
import logging
import os
import re
import signal
import socket
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_OUTPUT = 256 * 1024
GIT_TIMEOUT = 600
BUILD_TIMEOUT = 45 * 60
DOCKER_TIMEOUT = 120
CANCEL_POLL_S = 2.0
LineFn = Callable[[str], None]
# Set by a job (e.g. to JobContext.cancelled) so a long git/docker command stops when the job is
# cancelled instead of only between steps.
cancel_check: ContextVar[Callable[[], bool] | None] = ContextVar("deployer_cancel_check", default=None)
_SHA = re.compile(r"[0-9a-f]{7,40}")
# A-135: `-e KEY` reads the value from the docker CLI's own environment, so these names would
# configure the worker's CLI (DOCKER_HOST sends every secret to another daemon, LD_PRELOAD, PATH).
# The API rejects them; saved ones are never passed.
_CLI_ENV = re.compile(r"(DOCKER_.*|LD_.*|PATH)", re.IGNORECASE)


def reserved_env(key: str) -> bool:
    """True for app variable names that would configure the worker's docker CLI."""
    return bool(_CLI_ENV.fullmatch(key))


_docker: DockerCli | None = None


class DockerError(RuntimeError):
    """A docker/git command failed; `output` holds its (capped, redacted-by-caller) output."""

    def __init__(self, message: str, output: str = ""):
        super().__init__(message)
        self.output = output


def get_docker() -> DockerCli:
    global _docker
    if _docker is None:
        _docker = DockerCli()
    return _docker


def set_docker(cli: DockerCli | None) -> None:
    """Test hook: replace the process-wide client (None resets to the real CLI)."""
    global _docker
    _docker = cli


def _git_env(token: str | None) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    if token:
        # The helper reads the token from its own environment: it never appears in argv, the URL,
        # .git/config or git's output.
        env["DEPLOYER_GIT_TOKEN"] = token
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "credential.helper"
        env["GIT_CONFIG_VALUE_0"] = '!f() { echo username=x-access-token; echo "password=$DEPLOYER_GIT_TOKEN"; }; f'
    return env


class DockerCli:
    def _run(
        self,
        args: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = DOCKER_TIMEOUT,
        on_line: LineFn | None = None,
        check: bool = True,
        stdin_text: str | None = None,
    ) -> str:
        log.debug("exec: %s", " ".join(args[:4]))
        proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
            args,
            stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            text=True,
            errors="replace",
            start_new_session=os.name == "posix",  # own process group: the watchdog kills git's helpers too
        )
        # A watchdog, not a check between lines: a silent process (a stalled clone, a build that
        # runs a server) never yields a line, so the deadline and the job's cancel must fire on their own.
        fired: list[str] = []
        done = threading.Event()
        cancelled = cancel_check.get()
        deadline = time.monotonic() + timeout

        def _kill(reason: str) -> None:
            fired.append(reason)
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except OSError:
                pass

        def _watch() -> None:
            while not done.wait(min(CANCEL_POLL_S, max(0.0, deadline - time.monotonic()))):
                if time.monotonic() >= deadline:
                    return _kill(f"timed out after {int(timeout)} s")
                try:
                    if cancelled is not None and cancelled():
                        return _kill("cancelled")
                except Exception:  # noqa: BLE001, S110 - a failed cancel check must not stop the deadline
                    pass

        threading.Thread(target=_watch, daemon=True).start()
        chunks: list[str] = []
        size = 0
        assert proc.stdout is not None
        try:
            if stdin_text is not None:  # secrets (registry passwords) travel on stdin, never in argv
                assert proc.stdin is not None
                proc.stdin.write(stdin_text)
                proc.stdin.close()
            for line in proc.stdout:
                if on_line is not None:
                    on_line(line.rstrip("\n"))
                if size < MAX_OUTPUT:
                    chunks.append(line)
                    size += len(line)
            code = proc.wait()
        except BaseException:
            _kill("interrupted")
            raise
        finally:
            done.set()
            proc.stdout.close()
        if fired:
            raise DockerError(f"{args[0]} {args[1]} {fired[0]}", "".join(chunks))
        output = "".join(chunks)
        if check and code != 0:
            raise DockerError(f"{args[0]} {args[1]} failed (exit {code})", output)
        return output

    # --- git ---------------------------------------------------------------------------------

    def git_clone(self, url: str, branch: str, dest: str, *, token: str | None, on_line: LineFn | None = None) -> None:
        self._run(
            ["git", "clone", "--depth", "1", "--branch", branch, "--", url, dest],
            env=_git_env(token),
            timeout=GIT_TIMEOUT,
            on_line=on_line,
        )

    def git_checkout(self, dest: str, sha: str, *, token: str | None, on_line: LineFn | None = None) -> None:
        if not _SHA.fullmatch(sha):  # never an option (`--upload-pack=...`) or a range in git's argv
            raise DockerError(f"Invalid commit sha {sha[:50]!r}")
        env = _git_env(token)
        self._run(
            ["git", "fetch", "--depth", "1", "origin", sha], cwd=dest, env=env, timeout=GIT_TIMEOUT, on_line=on_line
        )
        self._run(["git", "checkout", "-q", "--detach", sha], cwd=dest, env=env, on_line=on_line)

    def git_head(self, dest: str) -> tuple[str, str]:
        """(sha, first line of the commit message) of HEAD."""
        out = self._run(["git", "log", "-1", "--format=%H%n%s"], cwd=dest, env=_git_env(None))
        sha, _, subject = out.strip().partition("\n")
        return sha, subject.strip()

    # --- images & containers -----------------------------------------------------------------

    def build(self, context: str, dockerfile: str, tag: str, *, on_line: LineFn | None = None) -> None:
        self._run(
            ["docker", "build", "--progress=plain", "--pull", "-t", tag, "-f", dockerfile, context],
            env={**os.environ, "DOCKER_BUILDKIT": "1"},
            timeout=BUILD_TIMEOUT,
            on_line=on_line,
        )

    def export_dir(self, image: str, path: str, dest: str) -> None:
        """Copies `path` out of `image` into the new directory `dest` (docs/CLOUD.md: a static site's
        build output). Symlinks are copied as links; callers must not follow them."""
        name = f"deployer-export-{uuid.uuid4().hex[:12]}"
        self._run(["docker", "create", "--pull", "never", "--name", name, image])
        try:
            self._run(["docker", "cp", f"{name}:{path}/.", dest], timeout=600)
        finally:
            self._run(["docker", "rm", "-f", name], check=False)

    def push(
        self, local_tag: str, remote: str, *, registry: str, username: str, password: str, config_dir: str, on_line=None
    ) -> None:
        """Tags and pushes an image to a cloud registry (docs/CLOUD.md). The registry password goes to
        `docker login --password-stdin`; the login lands in the throw-away `config_dir` (DOCKER_CONFIG),
        never in the worker's own ~/.docker. Both tags are removed locally afterwards."""
        env = {**os.environ, "DOCKER_CONFIG": config_dir}
        self._run(
            ["docker", "login", "--username", username, "--password-stdin", registry], env=env, stdin_text=password
        )
        self._run(["docker", "tag", local_tag, remote], env=env)
        try:
            self._run(["docker", "push", remote], env=env, timeout=BUILD_TIMEOUT, on_line=on_line)
        finally:
            self._run(["docker", "logout", registry], env=env, check=False)
            self._run(["docker", "rmi", "-f", remote, local_tag], env=env, check=False)

    def run_container(self, name: str, image: str, *, labels: dict[str, str], env: dict[str, str]) -> None:
        """Starts a detached app container. Env values are passed through the process environment
        (`-e KEY` without a value) so they never appear in argv; `reserved_env` names are dropped."""
        s = get_settings()
        args = [
            "docker",
            "run",
            "-d",
            # A-139: images are only ever built here; a removed one must not fall back to Docker Hub.
            "--pull",
            "never",
            "--name",
            name,
            "--network",
            s.app_network,
            "--restart",
            "unless-stopped",
            "--memory",
            s.app_mem_limit,
            "--cpus",
            "1",
            "--pids-limit",
            "256",
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--cap-add",
            "SETUID",
            "--cap-add",
            "SETGID",
            "--cap-add",
            "NET_BIND_SERVICE",
        ]
        for key, value in labels.items():
            args += ["--label", f"{key}={value}"]
        dropped = [k for k in env if reserved_env(k)]
        if dropped:
            log.warning("not passing reserved variables %s to %s", ", ".join(dropped), name)
        env = {k: v for k, v in env.items() if k not in dropped}
        for key in env:
            args += ["-e", key]
        args.append(image)
        self._run(args, env={**os.environ, **env})

    def network_connect(self, network: str, container: str) -> None:
        """Joins a running container to a second network (apps with database access)."""
        self._run(["docker", "network", "connect", network, container])

    def move_network(self, label: str, old: str, new: str) -> list[str]:
        """Moves every container labelled `label` from network `old` to `new` (A-019: app containers
        started before the apps-only network existed sit next to the API). Does nothing when `new`
        doesn't exist, so an older compose file keeps its routing."""
        try:
            self._run(["docker", "network", "inspect", new])
        except DockerError:
            return []

        def on(network: str) -> list[str]:
            args = ["docker", "ps", "-a", "--filter", f"network={network}", "--filter", f"label={label}"]
            return self._run([*args, "--format", "{{.Names}}"]).split()

        already = set(on(new))
        moved = []
        for name in on(old):
            if name not in already:
                try:
                    self._run(["docker", "network", "connect", new, name])
                except DockerError:  # leave it where Caddy can still reach it rather than cut it off
                    log.warning("could not connect %s to %s", name, new)
                    continue
            self._run(["docker", "network", "disconnect", old, name], check=False)
            moved.append(name)
        return moved

    def remove_container(self, name: str) -> None:
        self._run(["docker", "rm", "-f", name], check=False)

    def list_containers(self) -> list[dict[str, str]]:
        """`[{name, app, deployment}]` of every container labelled `deployer.app` (running or not)."""
        out = self._run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "label=deployer.app",
                "--format",
                '{{.Names}}\t{{.Label "deployer.app"}}\t{{.Label "deployer.deployment"}}',
            ]
        )
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0]:
                rows.append({"name": parts[0], "app": parts[1], "deployment": parts[2]})
        return rows

    def remove_image(self, tag: str) -> None:
        self._run(["docker", "rmi", "-f", tag], check=False)

    def list_images(self, repository: str) -> list[str]:
        """Tags of `repository` (e.g. `deployer-app/<app_id>`)."""
        out = self._run(["docker", "images", "--filter", f"reference={repository}", "--format", "{{.Tag}}"])
        return [t for t in out.split() if t and t != "<none>"]

    def wait_tcp(self, host: str, port: int, timeout: float) -> bool:
        """True once `host:port` accepts a TCP connection (the worker shares the app network)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=2):
                    return True
            except OSError:
                time.sleep(1)
        return False

    def logs(self, container: str, *, since: str | None, tail: int) -> list[str]:
        args = ["docker", "logs", "--tail", str(tail)]
        if since:
            args += ["--since", since]
        out = self._run([*args, container], check=False)
        return out.splitlines()

    # --- caddy -------------------------------------------------------------------------------

    def caddy_container(self) -> str | None:
        out = self._run(
            ["docker", "ps", "--filter", "label=com.docker.compose.service=caddy", "--format", "{{.Names}}"]
        )
        names = out.split()
        return names[0] if names else None

    def caddy_reload(self) -> None:
        name = self.caddy_container()
        if name is None:
            raise DockerError("The caddy container is not running")
        self._run(["docker", "exec", name, "caddy", "reload", "--config", "/etc/caddy/Caddyfile"])

    # --- monitoring (docs/MONITORING.md) -------------------------------------------------------

    def stats(self, compose_project: str) -> list[dict]:
        """Status + resource use of the compose project's containers and deployed app containers:
        `[{name, service, app_id, status, health, restarts, started_at, cpu_percent, memory_bytes,
        memory_limit_bytes}]` (resource fields None for containers that aren't running)."""
        out = self._run(
            [
                "docker",
                "ps",
                "-a",
                "--format",
                '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.service"}}'
                '\t{{.Label "deployer.app"}}',
            ],
            timeout=30,
        )
        rows: dict[str, dict] = {}
        for line in out.splitlines():
            name, project, service, app_id = ([*line.split("\t"), "", "", ""])[:4]
            if name and (project == compose_project or app_id):
                rows[name] = {"name": name, "service": service or None, "app_id": app_id or None}
        if not rows:
            return []
        fmt = (
            "{{.Name}}\t{{.State.Status}}\t{{if .State.Health}}{{.State.Health.Status}}{{end}}"
            "\t{{.RestartCount}}\t{{.State.StartedAt}}"
        )
        for line in self._run(["docker", "inspect", "--format", fmt, *rows], timeout=30, check=False).splitlines():
            name, status, health, restarts, started = ([*line.split("\t"), "", "", "", ""])[:5]
            row = rows.get(name.lstrip("/"))
            if row is not None:
                row.update(
                    status=status or None,
                    health=health or None,
                    restarts=int(restarts) if restarts.isdigit() else None,
                    started_at=started or None,
                )
        running = [n for n, r in rows.items() if r.get("status") == "running"]
        if running:
            out = self._run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", *running], timeout=30, check=False
            )
            for line in out.splitlines():
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                row = rows.get(item.get("Name", "")) if isinstance(item, dict) else None
                if row is None:
                    continue
                used, _, limit = str(item.get("MemUsage", "")).partition("/")
                row.update(
                    cpu_percent=_percent(item.get("CPUPerc")),
                    memory_bytes=parse_size(used),
                    memory_limit_bytes=parse_size(limit),
                )
        for row in rows.values():
            for key in (
                "status",
                "health",
                "restarts",
                "started_at",
                "cpu_percent",
                "memory_bytes",
                "memory_limit_bytes",
            ):
                row.setdefault(key, None)
        return sorted(rows.values(), key=lambda r: r["name"])


_SIZE_UNITS = {"b": 1, "kb": 1000, "mb": 1000**2, "gb": 1000**3, "tb": 1000**4}
_SIZE_UNITS.update({"kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4})


def parse_size(text: str) -> int | None:
    """`docker stats` sizes ("12.5MiB", "1.94GiB", "0B") to bytes."""
    match = re.fullmatch(r"\s*([\d.]+)\s*([a-zA-Z]+)\s*", text or "")
    factor = _SIZE_UNITS.get(match.group(2).lower()) if match else None
    try:
        return int(float(match.group(1)) * factor) if factor else None
    except ValueError:
        return None


def _percent(text) -> float | None:
    try:
        return round(float(str(text).strip().rstrip("%")), 1)
    except ValueError:
        return None
