"""Fake Docker/git CLI and app factory for the deployment tests (docs/DEPLOYMENTS.md)."""

from __future__ import annotations

import os
import secrets

from app.crypto import encrypt_secret
from app.models import App
from app.services import deployments
from app.services.app_runner import DockerCli, DockerError

FAKE_SHA = "a" * 40


class FakeDockerCli(DockerCli):
    """Records the call sequence; `fail_at = <step>` makes that step raise; `hooks[step]()` runs first."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.fail_at: str | None = None
        self.hooks: dict[str, callable] = {}
        self.containers: dict[str, dict] = {}
        self.images: set[str] = set()
        self.dockerfiles: list[str] = []
        self.log_lines = ["hello from the app"]
        self.head = (FAKE_SHA, "Initial commit")
        self.leak = "nothing"  # text echoed into git output (tests put the token here)

    def _step(self, name: str, *args) -> None:
        self.calls.append((name, *args))
        if name in self.hooks:
            self.hooks[name]()
        if self.fail_at == name:
            raise DockerError(f"{name} failed (exit 1)", f"some output\ncontains {self.leak}\n")

    def steps(self) -> list[str]:
        return [c[0] for c in self.calls]

    # git
    def git_clone(self, url, branch, dest, *, token, on_line=None):
        self._step("clone", url, branch)
        os.makedirs(dest, exist_ok=True)
        if on_line:
            on_line(f"Cloning into '{dest}'... helper saw {token or self.leak}")

    def git_checkout(self, dest, sha, *, token, on_line=None):
        self._step("checkout", sha)
        self.head = (sha, "pushed commit")

    def git_head(self, dest):
        return self.head

    # docker
    def build(self, context, dockerfile, tag, *, on_line=None):
        self._step("build", tag)
        with open(dockerfile, encoding="utf-8") as fh:
            self.dockerfiles.append(fh.read())
        self.images.add(tag)
        if on_line:
            on_line("#1 [internal] load build definition")

    def run_container(self, name, image, *, labels, env):
        self._step("run", name, image)
        self.containers[name] = {"image": image, "labels": labels, "env": env}

    def remove_container(self, name):
        self._step("rm", name)
        self.containers.pop(name, None)

    def list_containers(self):
        return [
            {
                "name": n,
                "app": c["labels"].get("deployer.app", ""),
                "deployment": c["labels"].get("deployer.deployment", ""),
            }
            for n, c in self.containers.items()
        ]

    def remove_image(self, tag):
        self._step("rmi", tag)
        self.images.discard(tag)

    def list_images(self, repository):
        return [t.split(":", 1)[1] for t in self.images if t.startswith(repository + ":")]

    def wait_tcp(self, host, port, timeout):
        self.calls.append(("health", host, port))
        return self.fail_at != "health"

    def logs(self, container, *, since, tail):
        self._step("logs", container, since)
        return list(self.log_lines)

    def caddy_container(self):
        return "deployer-caddy-1"

    def caddy_reload(self):
        self._step("reload")


def make_app(db, project, name="Shop", *, preset="node", env=None, token=None, **fields) -> App:
    app = App(
        project_id=project.id,
        name=name,
        slug=deployments.app_slug(db, project.id, name),
        repo_url="https://github.com/acme/shop",
        preset=preset,
        port=deployments.allocate_port(db),
        **fields,
    )
    deployments.set_env(app, env or {})
    deployments.rotate_webhook_secret(app)
    if token:
        app.repo_token_encrypted = encrypt_secret(token)
    db.add(app)
    db.commit()
    return app


def new_token() -> str:
    return "ghp_" + secrets.token_hex(12)
