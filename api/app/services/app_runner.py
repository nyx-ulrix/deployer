"""The worker's Docker / git interface for app deployments (docs/DEPLOYMENTS.md).

Everything that touches the Docker socket or a Git remote goes through `DockerCli` so the deploy
job can be tested end to end against a fake. Rules:

- subprocess argv only, never a shell; user-supplied strings are arguments, not command text;
- secrets (the repository token) travel in the environment (a git credential helper), never in argv,
  URLs or captured output, which is redacted with `connections.redact` before anyone sees it;
- captured output is capped (`MAX_OUTPUT`) so a chatty build can't exhaust the worker's memory.
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess
import time
from collections.abc import Callable

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_OUTPUT = 256 * 1024
GIT_TIMEOUT = 600
BUILD_TIMEOUT = 45 * 60
DOCKER_TIMEOUT = 120
LineFn = Callable[[str], None]

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
    ) -> str:
        log.debug("exec: %s", " ".join(args[:4]))
        proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            text=True,
            errors="replace",
        )
        chunks: list[str] = []
        size = 0
        deadline = time.monotonic() + timeout
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if on_line is not None:
                    on_line(line.rstrip("\n"))
                if size < MAX_OUTPUT:
                    chunks.append(line)
                    size += len(line)
                if time.monotonic() > deadline:
                    proc.kill()
                    raise DockerError(f"{args[0]} {args[1]} timed out after {int(timeout)} s", "".join(chunks))
            code = proc.wait(timeout=max(1.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            raise DockerError(f"{args[0]} {args[1]} timed out after {int(timeout)} s", "".join(chunks)) from None
        finally:
            proc.stdout.close()
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

    def run_container(self, name: str, image: str, *, labels: dict[str, str], env: dict[str, str]) -> None:
        """Starts a detached app container. Env values are passed through the process environment
        (`-e KEY` without a value) so they never appear in argv."""
        s = get_settings()
        args = [
            "docker",
            "run",
            "-d",
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
        for key in env:
            args += ["-e", key]
        args.append(image)
        self._run(args, env={**os.environ, **env})

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
