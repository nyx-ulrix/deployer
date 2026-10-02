"""App secrets in AWS Secrets Manager / Google Secret Manager (docs/CLOUD.md "G1").

Off by default. When a project admin switches it on for an App Runner / Cloud Run app (billable, so with
`confirm_billing`), every deploy writes the app's secret values to the cloud account's secret store - one
secret `deployer-<slug>-<id8>-<NAME>` per variable, created once, a new version only when the value changed -
and hands the service a *reference* (App Runner `RuntimeEnvironmentSecrets`, Cloud Run `secretKeyRef`)
instead of the value. The app's own identity may read exactly those secrets: the App Runner instance role gets
`secretsmanager:GetSecretValue` on their ARNs, the Cloud Run service account `roles/secretmanager.secretAccessor`
on each one. Secrets of variables that were removed, and all of them when the option is switched off, are
deleted after the new version is live; the app's teardown (delete, target switch) deletes the rest.

What counts as a secret: every variable of the app's own (Deployer stores them all encrypted and keeps them
out of logs - there is no per-variable flag) and the `DEPLOYER_DB_*` values that carry a database password.
Names, hosts, ports, table names, project ids and empty values stay plain environment. Values are never logged
or returned.
"""

from __future__ import annotations

from app.models import App

STATE_KEY = "secrets"  # apps.cloud_state["secrets"] = {"enabled": bool, "stored": {NAME: ARN | secret id}}
COST = {
    "aws": "AWS Secrets Manager bills about US$0.40 per secret per month (one secret per variable, so for example "
    "5 variables cost about US$2 a month) plus US$0.05 per 10,000 reads; App Runner reads them when an instance "
    "starts.",
    "firebase": "Google Secret Manager: 6 active secret versions a month are free, then about US$0.06 per version "
    "per month (one version per variable, a new one when its value changes) plus US$0.03 per 10,000 reads beyond "
    "10,000 a month.",
}
STORE = {"aws": "AWS Secrets Manager", "firebase": "Google Secret Manager"}
NOTE = (
    "Keeps the app's variables and database passwords in the cloud account's secret store instead of the service's "
    "plain environment; the app reads them through a reference only its own identity may use. Deployer never shows "
    "the stored values again."
)


def state_of(app: App) -> dict:
    return dict((app.cloud_state or {}).get(STATE_KEY) or {})


def enabled(app: App) -> bool:
    return bool(state_of(app).get("enabled"))


def set_enabled(app: App, value: bool) -> None:
    """Keeps `stored` (what is in the store now) so switching off still deletes them on the next deploy."""
    app.cloud_state = {**(app.cloud_state or {}), STATE_KEY: {**state_of(app), "enabled": value}}


def out(app: App, provider: str | None) -> dict:
    """`cloud.secrets` of an app (names only, never values)."""
    s = state_of(app)
    return {
        "enabled": bool(s.get("enabled")),
        "store": STORE.get(provider or ""),
        "note": NOTE,
        "cost": COST.get(provider or ""),
        "stored": sorted(s.get("stored") or {}),
    }


def _stored(state: dict | None) -> dict[str, str]:
    return dict(((state or {}).get(STATE_KEY) or {}).get("stored") or {})


def resources(provider: str, state: dict | None) -> list[str]:
    stored = _stored(state)
    return [f"{STORE[provider]} secrets {', '.join(sorted(stored))}"] if stored else []


def secret_name(app: App, key: str) -> str:
    from app.services.cloud_deploy import resource_name

    return f"{resource_name(app)}-{key}"


def split(app: App, env: dict[str, str], databases: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """(plain environment, the values that go to the store) - see the module docstring."""
    from app.services.deployments import env_of

    own = set(env_of(app))
    passwords = [p for d in databases for p in [d["config"].get("password")] if p]
    # An empty value is no secret, and the stores refuse it (Secrets Manager's SecretString needs 1+ characters).
    secret = {k: v for k, v in env.items() if v and (k in own or any(p in v for p in passwords))}
    return {k: v for k, v in env.items() if k not in secret}, secret


def sync(publish, client, env: dict[str, str], databases: list[dict]) -> tuple[dict[str, str], dict[str, str], dict]:
    """Writes this deploy's secrets to the store (`client.put_secret(name, value) -> reference`) and records the
    references in the app's state as each one exists. Returns (plain environment, {NAME: reference} for the
    service, the stale references to delete once the new version is live). With the option off every stored
    secret is stale, so switching off cleans up on the next deploy."""
    before = _stored(publish.state)
    if not (publish.state.get(STATE_KEY) or {}).get("enabled"):
        return env, {}, before
    plain, secret = split(publish.app, env, databases)
    stored: dict[str, str] = {}
    if secret:
        publish.log.step(f"Storing {len(secret)} secret(s) in {STORE[publish.provider]}: " + ", ".join(sorted(secret)))
    for key in sorted(secret):
        stored[key] = client.put_secret(secret_name(publish.app, key), secret[key])
        _save_stored(publish, {**before, **stored})
    return plain, stored, {k: v for k, v in before.items() if k not in stored}


def cleanup(publish, client, stale: dict[str, str]) -> None:
    """Deletes the secrets the live version no longer references - after the rollout, so a failed one that kept
    the previous version serving still finds them. `client.delete_secret` takes the stored reference."""
    for key in sorted(stale):
        publish.log.write(f"Removing the secret for {key} from {STORE[publish.provider]} (no longer used)")
        client.delete_secret(stale[key])
    if stale:
        _save_stored(publish, {k: v for k, v in _stored(publish.state).items() if k not in stale})


def _save_stored(publish, stored: dict[str, str]) -> None:
    """Records what is in the store. `enabled` is re-read from the row first: an admin may have switched the
    option while this deploy ran, and the job's copy must not write that choice back."""
    with publish.ctx.session_factory() as db:
        row = db.get(App, publish.app.id)
        enabled = bool(((row.cloud_state or {}).get(STATE_KEY) or {}).get("enabled")) if row else False
    publish.save(**{STATE_KEY: {"enabled": enabled, "stored": stored}})


def teardown_steps(client, provider: str, state: dict) -> list[tuple[str, object]]:
    return [
        (f"{STORE[provider]} secret {key}", lambda ref=ref: client.delete_secret(ref))
        for key, ref in sorted(_stored(state).items())
    ]
