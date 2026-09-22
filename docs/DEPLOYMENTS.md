# Deployments (push-to-deploy) — phase 4

Deployer can build a web app from a Git repository and run it next to the project's databases on
the same PC. This is the "Vercel half": a project gets **apps**; each app has **deployments** built
from a commit; the newest successful deployment is **live** behind Caddy. Nothing from the Deployer
authors is involved: the user's own GitHub repository, their own PC, their own domain.

## What runs where

```text
GitHub push ──webhook──▶ api ──job app.deploy──▶ worker (root, docker CLI + /var/run/docker.sock)
                                                   │ git clone → docker build → docker run
                                                   ▼
                     caddy :8100-8199 (one port per app, LAN/localhost)      deployer-app-<slug>-<dep>
                     caddy :8081 host blocks (Cloudflare hostnames)  ──────▶ container on the `public` network
```

- The **worker** service mounts the Docker socket and runs as root (`user: "0:0"`) so it can build
  images and run containers; the API stays unprivileged. The worker already runs backups; this widens
  its trust, documented in SECURITY.md. Build tools in the image: `git`, `docker-ce-cli`,
  `docker-buildx-plugin` (Docker apt repo, key fingerprint checked like MariaDB's).
- App containers are named `deployer-app-<slug>-<8 chars of deployment id>`, labelled
  `deployer.app=<app_id>` and `deployer.deployment=<deployment_id>`, attached to the compose `public`
  network, `--restart unless-stopped`, `--memory <APP_MEM_LIMIT, default 512m>`, `--cpus 1`,
  `--pids-limit 256`, no privileges, no volumes. Images are tagged
  `deployer-app/<app_id>:<deployment_id>`; the last 5 per app are kept, older ones removed.
- **Routing** is Caddy only; app containers never publish ports. Caddy publishes the range
  `8100-8199` (compose `ports: "8100-8199:8100-8199"`, bound to `${DEPLOYER_BIND:-127.0.0.1}` like
  8080) and imports `/etc/caddy/apps/*.caddy` from the shared `caddy_apps` volume, one file per app:

  ```caddyfile
  # apps/<app_id>.caddy — generated, do not edit
  :8107 {
      reverse_proxy deployer-app-shop-1a2b3c4d:3000
  }
  http://shop.example.com:8081 {
      reverse_proxy deployer-app-shop-1a2b3c4d:3000
  }
  ```

  The worker rewrites the file and runs `docker exec deployer-caddy-1 caddy reload --config
  /etc/caddy/Caddyfile` (the container name comes from `docker ps --filter label=com.docker.compose.service=caddy`).
  Ports are allocated per app from the range (`apps.port`, unique); an app keeps its port for life.
  LAN access to app ports needs the same port forwarding as 8080 (`deployer lan on` forwards the
  range too — installer follow-up).
- **Zero-downtime swap**: the new container starts, the worker waits for a TCP accept on its port
  (up to 60 s), rewrites the Caddy file to the new container, reloads, then stops and removes the
  previous container. A failed start leaves the previous deployment live.
- **Cloudflare hostnames** for apps reuse the `domains` table (`domains.app_id` nullable FK,
  `domains.kind` `dashboard|app`): adding one creates the DNS CNAME and adds the hostname to the
  tunnel ingress (→ `http://caddy:8081`), exactly like dashboard hostnames (REMOTE_ACCESS.md), and the
  Caddy host block above routes it to the app.

## Presets

| `preset` | Build | Run | Port |
|---|---|---|---|
| `static` | `install_command` (default `npm ci` if package.json), `build_command` (default `npm run build` if package.json has one), output `output_dir` (default: first of `dist`, `build`, `out`, `public`, `.`) | `nginx:1.27-alpine` serving the output with `try_files $uri $uri/ /index.html` | 80 |
| `node` | `node:22-alpine`, `install_command` (default `npm ci`), optional `build_command` | `start_command` (default `npm start`), `PORT=3000` | 3000 |
| `python` | `python:3.12-slim`, `pip install -r requirements.txt` | `start_command` (required, e.g. `uvicorn main:app --host 0.0.0.0 --port 8000`) | 8000 |
| `dockerfile` | the repo's `Dockerfile` (`root_dir` relative) | the image's CMD | `container_port` (required) |

The worker writes a generated Dockerfile for the first three presets next to the checkout and
builds with `docker build --progress=plain --pull` (BuildKit), so the build itself is sandboxed in
BuildKit; the user's build commands run inside the build image, never on the host.

Environment: `apps.env_encrypted` (JSON object, `encrypt_json`), values shown masked in the
dashboard and revealable by admins. Always injected: `PORT`, `DEPLOYER_URL` (public URL + `/v1`),
`DEPLOYER_PROJECT_ID`; when `apps.api_key_id` is set, `DEPLOYER_API_KEY` (decrypted from
`api_keys.secret_encrypted`; a key without a stored secret cannot be attached).

## Data model (migration `0006_apps_deployments`)

| Table | Columns |
|---|---|
| `apps` | `id`, `project_id` FK CASCADE idx, `name` 120, `slug` 63 (unique per project, DNS-safe), `repo_url` 500 (https only), `branch` 120 (default `main`), `root_dir` 200 (default `.`), `preset` (`static|node|python|dockerfile`), `install_command`, `build_command`, `start_command`, `output_dir`, `container_port` int nullable, `env_encrypted` Text, `repo_token_encrypted` Text nullable (GitHub token for private repos; never logged), `webhook_secret_encrypted` Text, `api_key_id` FK api_keys SET NULL, `port` int unique (8100–8199), `live_deployment_id` String(36) nullable, `created_by_id`, `created_at`, `updated_at` |
| `deployments` | `id`, `app_id` FK CASCADE idx, `job_id` FK jobs SET NULL, `status` (`queued|building|deploying|live|failed|cancelled|superseded`), `trigger` (`manual|webhook|rollback`), `commit_sha` 40 nullable, `commit_message` 200 nullable, `branch`, `image_tag` 200 nullable, `container_name` 100 nullable, `log` Text (capped 1 MB, tail kept), `error` Text nullable, `created_by_id`, `created_at` idx, `started_at`, `finished_at`, `rollback_of` String(36) nullable |
| `domains` | + `app_id` FK apps CASCADE nullable; the existing `target_type` gains the value `app` |

`live` means "currently routed"; when a newer deployment goes live the previous one becomes
`superseded`. A rollback builds nothing: it re-runs the old `image_tag` as a new deployment with
`trigger=rollback`, `rollback_of=<old id>`.

## Jobs

- `app.deploy` (`runs_on=primary`, params `{deployment_id}`): clone (`git clone --depth 1 --branch
  <branch> <url>` with the token in the URL via a credential helper env, never argv, never the log;
  or `git fetch` of a given sha for webhook deploys), record `commit_sha`/`commit_message`, build,
  run, health wait, route, stop old, prune images. Progress messages: `Cloning`, `Building`,
  `Starting`, `Routing`, `Cleaning up`. Cancel between steps via `ctx.check_cancelled()`. One active
  deploy per app (`jobs.active_job(key=app_id)`), a second request while one runs is queued behind
  it (status `queued`).
- `app.remove` (`{app_id}`): stop/remove containers and images, delete the Caddy file, reload,
  remove the app's domains (DNS + ingress) — enqueued by `DELETE /apps/{id}`.
- Scheduler: every tick, containers labelled `deployer.app` whose app or live deployment no longer
  exists are removed (orphans after a failed remove or an import).

## API (`/v1/projects/{pid}`)

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/apps` | viewer+ | – | `App[]` |
| POST | `/apps` | developer+ | `{name, repo_url, branch?, root_dir?, preset, install_command?, build_command?, start_command?, output_dir?, container_port?, env?: {k:v}, repo_token?, api_key_id?}` | `App` (201); allocates `port`, generates `webhook_secret` |
| GET | `/apps/{id}` | viewer+ | – | `App` |
| PATCH | `/apps/{id}` | developer+ | partial of the above (`repo_token: null` clears) | `App` (changes apply on the next deploy) |
| DELETE | `/apps/{id}` | admin+ | – | `{job_id}` (`app.remove`) |
| GET | `/apps/{id}/env` | admin+ | – | `{env: {k:v}}` plain values (audit `app.env.reveal`) |
| GET | `/apps/{id}/webhook` | developer+ | – | `{url, secret}` — url `<public_url>/v1/hooks/github/{app_id}`; audit `app.webhook.reveal` |
| POST | `/apps/{id}/webhook/rotate` | developer+ | – | `{url, secret}` |
| POST | `/apps/{id}/deploy` | developer+ | `{branch?}` | `Deployment` (202) |
| GET | `/apps/{id}/deployments?limit=20&before=` | viewer+ | – | `{deployments: Deployment[] (log omitted), has_more}` |
| GET | `/apps/{id}/deployments/{dep}` | viewer+ | `?log=1` includes the log | `Deployment` |
| POST | `/apps/{id}/deployments/{dep}/cancel` | developer+ | – | `Deployment` |
| POST | `/apps/{id}/deployments/{dep}/rollback` | developer+ | – | `Deployment` (202, new one) |
| GET | `/apps/{id}/logs?tail=200` | viewer+ | – | `{lines: string[], container}` from `docker logs` of the live container (worker-side via a short job? No: the API calls `docker logs` through the worker RPC — see below) |
| POST | `/apps/{id}/domains` | admin+ (instance owner for DNS) | `{hostname}` | `Domain` (same rules as REMOTE_ACCESS.md, `kind: app`) |
| DELETE | `/apps/{id}/domains/{domain_id}` | admin+ | – | `{ok}` |

Webhook (no auth header): `POST /v1/hooks/github/{app_id}` with GitHub's `X-Hub-Signature-256`
(HMAC-SHA256 of the raw body with the app's secret, constant-time compare; 401 `bad_signature`
otherwise), `X-GitHub-Event: ping` → 200 `{ok}`; `push` for `refs/heads/<branch>` → 202
`{deployment_id}` (`trigger=webhook`, `commit_sha`, first line of the head commit message); other
branches/events → 200 `{ignored: true}`. Coalescing: a push while a deployment is still `queued`
for the same app replaces its commit instead of adding another. Rate limit 6/min per app.

Runtime logs: the API has no Docker access. `GET /apps/{id}/logs` enqueues nothing; instead the
worker keeps the last 500 lines of each live container in Redis (`apps:logs:<app_id>`, a capped
list refreshed by a `docker logs --since` poll every 10 s in the scheduler) and the API reads that.

```ts
type App = { id; project_id; name; slug; repo_url; branch; root_dir; preset; install_command; build_command;
  start_command; output_dir; container_port: number|null; env_keys: string[]; has_repo_token: boolean;
  api_key_id: string|null; port: number; local_url: string; urls: string[]; live_deployment: Deployment|null;
  domains: Domain[]; created_at; updated_at };
type Deployment = { id; app_id; status; trigger; commit_sha; commit_message; branch; image_tag; created_at;
  started_at; finished_at; error; rollback_of; log?: string; job_id };
```

`local_url` is `http://localhost:<port>` (or the public URL's host with the port when the public URL is
not localhost); `urls` adds `https://<hostname>` per active app domain.

Export/import: `apps` (with `env` decrypted, `repo_token` decrypted, `webhook_secret`
decrypted — re-encrypted on import) and `domains` of kind `app`; deployments are not exported. The
importing instance allocates fresh ports and does not deploy automatically.

## Dashboard — project tab **Deploys**

- Apps list (name, preset, branch, live status dot, local URL, last deploy relative time) → app page.
- **New app** dialog: name (slug preview), repository URL + branch, "private repository" toggle with a
  token field (help: fine-grained token, Contents: read), preset picker with per-preset fields and
  sensible defaults, root directory, environment variables editor (key/value rows, paste `.env`),
  attach an API key (list of the project's keys; only revealable ones), *Create* then *Deploy now*.
- App page: header with live badge, URL links, **Deploy now** / **Cancel**; deployments table
  (status, trigger, commit, when, duration; **Rollback** on old successful ones); build log panel that
  follows the running deployment (poll `?log=1` every 2 s while building/deploying, then stop);
  **Runtime logs** panel (tail, refresh); **Settings** (edit everything, env values masked with
  reveal for admins, webhook URL + secret reveal/rotate with GitHub instructions: repo → Settings →
  Webhooks → payload URL, content type `application/json`, secret, "Just the push event"); **Domains**
  (add hostname when Cloudflare is linked, else a link to Settings → Domains); **Delete app** (confirm).
- Overview tab quick link "Deploys"; the `deploy-website` skill gains the option "this Deployer
  instance" as a real target.

## Tests

API: model/migration, slug/port allocation, CRUD + roles, env reveal audit, webhook signature
(good/bad/ping/other branch/coalescing/rate limit), deploy job with a fake Docker runner
(clone/build/run/health/route/stop sequence, failure leaves the old container, cancel, rollback
reuses the image), Caddy file rendering, orphan cleanup, export/import round-trip; an integration
test that builds a one-file static site is skipped unless `DEPLOYER_TEST_DOCKER=1`.
Dashboard: slug preview, env editor parsing (`.env` paste), deployment status mapping, URL builders.
