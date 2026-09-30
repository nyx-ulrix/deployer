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
                     caddy :8081 host blocks (Cloudflare hostnames)  ──────▶ container on the `apps` network
```

- The **worker** service mounts the Docker socket and runs as root (`user: "0:0"`) so it can build
  images and run containers; the API stays unprivileged. The worker already runs backups; this widens
  its trust, documented in SECURITY.md. Build tools in the image: `git`, `docker-ce-cli`,
  `docker-buildx-plugin` (Docker apt repo, key fingerprint checked like MariaDB's).
- App containers are named `deployer-app-<slug>-<8 chars of deployment id>`, labelled
  `deployer.app=<app_id>` and `deployer.deployment=<deployment_id>`, attached to the compose `apps`
  network (setting `app_network`, `deployer_apps`: only `caddy` and the worker share it, so an app
  can't reach the API, dashboard or tunnel directly; on startup the worker moves containers started
  by older versions off `deployer_public`), `--restart unless-stopped`, `--memory <APP_MEM_LIMIT, default 512m>`, `--cpus 1`,
  `--pids-limit 256`, no privileges, no volumes. Images are tagged
  `deployer-app/<app_id>:<deployment_id>`; the images of the last 5 live/superseded deployments
  per app are kept (the rollback targets), older ones removed. A failed or cancelled deployment's own
  image is removed when it ends (a failed rollback keeps the image it reused).
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
  /etc/caddy/Caddyfile` (the container name comes from `docker ps --filter label=com.docker.compose.service=caddy`;
  the Caddyfile's admin API listens on a Unix socket inside the Caddy container for this, never on TCP).
  The worker also keeps a `_empty.caddy` placeholder in the directory so the import always matches.
  Ports are allocated per app from the range (`apps.port`, unique); an app keeps its port for life.
  LAN access to app ports needs the same port forwarding as 8080 (`deployer lan on` forwards the
  range too — installer follow-up).
- **Zero-downtime swap**: the new container starts, the worker waits for a TCP accept on its port
  (up to 60 s), rewrites the Caddy file to the new container, reloads, then stops and removes the
  previous container. A failed start leaves the previous deployment live.
  A timed-out wait says the app must listen on `0.0.0.0` and on `$PORT` (not for the `static`
  preset, whose nginx is Deployer's own). A clone that fails on a missing branch or an unreadable
  (private, mistyped) repository puts a plain next step above git's own lines in the error.
- **Cloudflare hostnames** for apps reuse the `domains` table (`domains.app_id` nullable FK,
  `domains.target_type` = `app`): adding one resolves the zone from the hostname (longest matching
  zone of the linked account, else 404 `zone_not_found`), creates the DNS CNAME and adds the
  hostname to the tunnel ingress (→ `http://caddy:8081`), exactly like dashboard hostnames
  (REMOTE_ACCESS.md). The API has no Docker access, so it then enqueues `app.route` (only when the
  app has a live deployment) and the worker rewrites the Caddy file with the host block above.

## Hosting targets (docs/CLOUD.md)

Where an app runs is its `target`: `local` (default, everything in this document) or a cloud target on
the user's own AWS / Firebase account, which keeps serving when this PC is off:

| `target` | Serves | Preset |
|---|---|---|
| `local` | container on this PC behind Caddy | any |
| `aws_static` | S3 (private) + CloudFront | `static` |
| `aws_app` | ECR image on App Runner | any |
| `firebase_hosting` | Firebase Hosting | `static` |
| `firebase_app` | Artifact Registry image on Cloud Run, behind Firebase Hosting | any |

Cloud targets are built on this PC exactly like `local` apps (same presets, same build log), then
published by `cloud_deploy.go_live` instead of `docker run` + Caddy. They never get `DEPLOYER_URL`,
`DEPLOYER_API_KEY` or `DEPLOYER_DB_*` (so `api_key_id`, `database_access` and `cohost` are refused for
them), only the app's own variables. Only project admins pick a target and its cloud connection
(`cloud_connection_id`); moving or deleting a cloud app tears down what Deployer created there (job
`app.cloud_teardown`). Custom domains of cloud apps go to the cloud target (with DNS records created in
Cloudflare when linked) instead of the tunnel. Details, API and permissions: [CLOUD.md](CLOUD.md).

## Database access

Off by default. An app normally reaches its project's data only through the data API
(`DEPLOYER_API_KEY`): app containers sit on the compose `apps` network, while `mariadb` and
`mongodb` live on `backend` (`internal: true`). Apps that talk to their managed databases directly
(e.g. Flask + PyMySQL / PyMongo) need `apps.database_access` (migration `0007_app_database_access`).

- **Why opt-in:** the `backend` network also carries Redis (password-protected) and the platform
  MariaDB (the server that holds Deployer's own schema next to the managed databases). Joining it
  only makes those hosts routable; each app still needs a source's own restricted credentials
  (a per-database MariaDB user / Mongo `dbOwner` user), never the root ones.
- **Who:** only project **admins** can switch it on (on create or PATCH; developers get 403
  `forbidden` "Only project admins can give an app database access"). Developers may still edit an
  app that has it on (re-sending `true` is fine) and may switch it off. Every change is audited as
  `app.database_access` with `enabled`.
- **Worker:** on every deploy and rollback of such an app, after `docker run` on the `apps` network,
  `docker network connect <APP_DB_NETWORK> <container>` (setting `app_db_network`, compose worker env
  `APP_DB_NETWORK=deployer_backend`). The log says "Connected to the project's databases network" and
  lists the injected variable **names**; passwords and URLs are redacted from the log.
- **Injected environment** (the app's own variables with the same name win), for each non-deleted
  managed source of the project on the main server, `NAME` = source name upper-cased with every
  non-alphanumeric turned into `_` (so renaming a source renames its variables from the next deploy):
  - SQL: `DEPLOYER_DB_<NAME>_HOST`, `_PORT`, `_USER`, `_PASSWORD`, `_DATABASE`, `_URL`
    (`mysql://<user>:<password>@mariadb:3306/<db>` with user and password URL-encoded; placeholders
    in angle brackets here so the secret scanner doesn't read the example as a credential);
  - MongoDB: `DEPLOYER_DB_<NAME>_URL` (`mongodb://<user>:<password>@mongodb:27017/<db>?authSource=<db>&directConnection=true`)
    and `_DATABASE`.

  Host/port come from the stored connection config, i.e. the in-network names the API itself uses.
  Sources on host devices are skipped with a log line ("… is on a host device and is not reachable
  from apps"); external sources are not injected (add their credentials under Environment).
- An existing app with its own variable names (e.g. `HH_SQL_HOST`) can set them under Environment
  with host `mariadb` / port `3306` and `mongodb:27017`, plus the source's credentials from
  `GET /data-sources/{sid}/connection`.
- **Connection cap:** each managed MariaDB user may hold at most `MANAGED_DB_MAX_USER_CONNECTIONS`
  (default 20) connections at once, shared by the app (old and new container overlap during a deploy)
  and Deployer's own data API. Keep the app's pool small (about 5); past the cap MariaDB refuses new
  connections with "User ... has exceeded the 'max_user_connections' resource".

## Co-hosted apps (docs/COHOSTING.md "Websites on both PCs")

`apps.cohost` (admin-only, default false): every deployment that goes live also runs on the project's
co-host devices (job `app.replicate` per device, RPC `apps.deploy` on the device's own worker), and the
app's hostnames move to the separate **apps tunnel** so Cloudflare fails over between PCs. Only one
app per installation can be co-hosted for now (409 `cohost_limit`; COHOSTING.md "Honest limits").
`apps.cohost_share_repo_access` (admin-only, default false) sends the clone token to those devices;
without it a private repository can't be built there. Devices never receive `DEPLOYER_API_KEY` or the
main server's database credentials; with database access they inject `DEPLOYER_DB_*` for their own
local copies. Migration `0010_cohost_apps` adds both columns and `app_replicas` (one row per device).

## Connect a Git repository

The New app dialog starts with **Choose a repository**; everything it fills in stays editable.

1. **Connect GitHub once** (per Deployer user). `POST /v1/integrations/github/connect` returns GitHub's
   authorize URL for the instance's existing GitHub sign-in OAuth app (Instance settings → Sign-in
   apps; no extra app to register) with scopes `repo admin:repo_hook read:user`, using the same state +
   PKCE + browser-nonce machinery and callback (`/v1/auth/oauth/github/callback`) as sign-in, with
   the state's intent `github_connect`. That callback **never signs anyone in or creates a user**: it
   also requires the browser's refresh-token cookie to belong to the user who started the flow
   (`error=github_connect_user_mismatch` otherwise), stores the token with `encrypt_secret` in
   `github_connections` (one per user; never logged or returned) and redirects to the dashboard's
   `/integrations/github/done?ok=1` (or `?error=<code>`), which returns to where the user was.
   `GET /v1/integrations/github` → `{connected, login, scopes, configured}`; disconnect in Account
   settings (`DELETE /v1/integrations/github` → `{ok, apps_using_connection, message}`); GitHub's own
   revoke is at github.com/settings/applications.
2. **Pick a repository** from `GET /v1/integrations/github/repos?q=&page=` (GitHub `/user/repos`,
   affiliation owner + collaborator + organization member, most recently pushed first, 100 per page;
   `q` searches name/description over up to 5 pages; 409 `github_not_connected` without a connection
   or when GitHub rejects the token), or paste any https URL.
3. **Detect**: `POST /apps/detect {repo_url, branch?}` reads the repository through the GitHub API
   (the caller's connection when there is one, otherwise anonymously, so public repositories work
   without connecting): the tree at the branch plus a few small files. It returns a draft that is
   never stored. The rules live in `api/app/services/repo_detect.py` (pure, unit-tested):

   | Found | Suggests |
   |---|---|
   | `Dockerfile` | `dockerfile`, `container_port` from `EXPOSE` (8080 + warning without one) |
   | `package.json` with `next` + `output: 'export'` / `next export` | `static`, output `out` |
   | ... `vite` / `@vitejs/*`, `react-scripts`, `astro`, `@sveltejs/kit` + `adapter-static` (and no `express`/`fastify`/`koa`/`hono`) | `static`, output `dist`, `build`, `dist`, `build` |
   | ... a `start` script or `express`/`fastify`/`next`/`nuxt` | `node`: `npm ci` (`npm install` without a lockfile), `npm run build` when there is a build script, `npm start` (else `npx next start`, Nuxt's `.output/server/index.mjs`, `node <main>`) |
   | `requirements.txt` / `pyproject.toml` with `flask` | `python`, `python -m flask --app <module> run --host 0.0.0.0 --port 8000`; module from `app.py` / `wsgi.py` / `app/__init__.py` (`create_app` or `app =`) |
   | ... `fastapi` | `uvicorn <module>:app --host 0.0.0.0 --port 8000` (`main.py`, `app.py`, `app/main.py`; warns when uvicorn isn't a dependency) |
   | ... `django` / `manage.py` | `python manage.py runserver 0.0.0.0:8000` + a warning that it's a development server |
   | `index.html` without `package.json` | `static`, no build, output `.` |

   pyproject-only Python apps get `pip install --no-cache-dir .` as the install command. Monorepos:
   when the root matches nothing but exactly one first-level directory does, `root_dir` is set to it
   (several: a warning naming them). `env_keys` come from `.env.example` / `.env.sample` /
   `.env.template` (names only, never values); `database_access_suggested` when Python deps include
   `pymysql`/`mysqlclient`/`psycopg`/`pymongo`/`sqlalchemy` or Node deps `mysql2`/`pg`/`mongodb`/
   `mongoose`/`prisma`. Not found / no access: 422 `repo_not_accessible` ("connect GitHub for private
   repositories"); unknown branch: 422 `branch_not_found`. Non-GitHub URLs are not cloned by the API
   (it has no git sandbox): an empty draft with a warning.
4. **Create & deploy** with `use_github_connection: true` (instead of `repo_token`; GitHub URLs only;
   409 `github_not_connected` without a connection). The app stores `github_connection_user_id`
   (the creator); every deploy clones with that user's current token, resolved at deploy time. If the
   connection was removed the deployment fails with "The GitHub connection of <email> was removed;
   reconnect GitHub or add a token in the app's settings". The token is only ever used for github.com
   URLs, and when someone other than the creator changes the app's repository the connection is
   detached (they must supply a token). An explicit `repo_token` wins over the connection. A stored
   `repo_token` is dropped when the repository URL moves to another host without a new token in the
   same request (git would otherwise hand it to that host).
5. **Webhook**: right after create (and on `POST /apps/{id}/webhook/rotate`) Deployer creates or
   updates the repository's `push` webhook (`POST`/`PATCH /repos/{o}/{r}/hooks`, JSON, the app's
   secret) and stores its id in `apps.github_hook_id`; deleting the app removes it, best effort.
   Changing the repository (once the PATCH has passed validation) removes the old repository's hook
   and adds one on the new repository when the connection's owner made the change; anyone else gets
   the warning to add it by hand. Every change of the public URL (`PUT /instance/settings`,
   `POST /instance/remote-access/public-url`) re-points the hooks of all connected apps, so an app
   created before remote access was set up starts deploying on push once it is. When the public URL
   is `localhost` or a private address the hook is skipped and the response carries the warning
   "GitHub can't reach http://localhost:8080 — set up a public URL (Settings → Domains) to deploy on
   push"; a GitHub error becomes a warning too. The app is created either way and the manual webhook
   instructions in Settings still apply.

Migration `0009_github_connections`: `github_connections (id, user_id unique FK CASCADE,
github_login, github_user_id, token_encrypted, scopes, created_at, updated_at)`, plus
`apps.github_connection_user_id` (FK users, SET NULL) and `apps.github_hook_id`.

## Presets

| `preset` | Build | Run | Port |
|---|---|---|---|
| `static` | `install_command` (default `npm ci` if package.json, `npm install` when there is no package-lock.json), `build_command` (default `npm run build` if package.json has one), output `output_dir` (default: first of `dist`, `build`, `out`, `public`, `.`; falling back to `.` logs a warning that the whole repository is published). Dotfiles and dot-folders (`.git`, `.env`, ...) are removed from the output, except `.well-known`, so they are never served or uploaded to AWS/Firebase | `nginx:1.27-alpine` serving the output with `try_files $uri $uri/ /index.html` | 80 |
| `node` | `node:22-alpine`, `install_command` (default `npm ci`, or `npm install` when there is no package-lock.json), optional `build_command` | `start_command` (default `npm start`), `PORT=3000` | 3000 |
| `python` | `python:3.12-slim`, `pip install -r requirements.txt` | `start_command` (required, e.g. `uvicorn main:app --host 0.0.0.0 --port 8000`) | 8000 |
| `dockerfile` | the repo's `Dockerfile` (`root_dir` relative) | the image's CMD | `container_port` (required) |

The worker writes a generated Dockerfile for the first three presets next to the checkout and
builds with `docker build --progress=plain --pull` (BuildKit), so the build itself is sandboxed in
BuildKit; the user's build commands run inside the build image, never on the host.
Every git/docker command has a hard deadline (clone/fetch 10 min, build/push 45 min, most others
2 min) enforced by a watchdog that kills the process group even when it prints nothing, so a
stalled clone or a build command that never exits (e.g. `npm start`) fails the deploy instead of
holding a worker runner. The same watchdog checks the job's cancel flag every 2 s, so **Cancel**
also stops a running clone, build or push.

Environment: `apps.env_encrypted` (JSON object, `encrypt_json`), values shown masked in the
dashboard and revealable by admins. Always injected: `PORT`, `DEPLOYER_URL` (public URL + `/v1`),
`DEPLOYER_PROJECT_ID`; when `apps.api_key_id` is set, `DEPLOYER_API_KEY` (decrypted from
`api_keys.secret_encrypted`; a key without a stored secret cannot be attached).

## Data model (migration `0006_apps_deployments`)

| Table | Columns |
|---|---|
| `apps` | `id`, `project_id` FK CASCADE idx, `name` 120, `slug` 63 (unique per project, DNS-safe), `repo_url` 500 (https only), `branch` 120 (default `main`), `root_dir` 200 (default `.`), `preset` (`static|node|python|dockerfile`), `install_command`, `build_command`, `start_command`, `output_dir`, `container_port` int nullable, `env_encrypted` Text, `repo_token_encrypted` Text nullable (GitHub token for private repos; never logged), `webhook_secret_encrypted` Text, `api_key_id` FK api_keys SET NULL, `port` int unique (8100–8199), `live_deployment_id` String(36) nullable, `created_by_id`, `created_at`, `updated_at`; `database_access` Boolean NOT NULL default false (migration `0007`, see "Database access") |
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
  `Starting`, `Routing`, `Cleaning up`. Cancel between steps via `ctx.check_cancelled()`, and inside a running git/docker command via the `_run` watchdog. One active
  deploy per app (`jobs.active_job(key=app_id)`), a second request while one runs is queued behind
  it (status `queued`).
- `app.remove` (`{app_id, slug}`): stop/remove containers and images, delete the Caddy file, reload —
  enqueued by `DELETE /apps/{id}`, which first removes the app's domains (DNS + ingress, synchronously
  like `DELETE /instance/remote-access/cloudflare/hostnames/{id}`), cancels active deployments and
  deletes the row (deployments and domains cascade).
- `app.route` (`{app_id}`): rewrite the app's Caddy file for its live deployment (or remove it) and
  reload — enqueued when an app hostname is added or removed (co-hosted apps also re-send their routes
  to the co-host devices).
- `app.replicate` (`{app_id, device_id}`, co-hosted apps): builds and runs the live deployment on one
  co-host device (docs/COHOSTING.md); enqueued when a deployment goes live and by the scheduler sweep.
- Scheduler: every tick, containers labelled `deployer.app` whose app or deployment no longer exists
  (or is not `deploying`/`live`) are removed, Caddy files of deleted apps are deleted, `queued`
  deployments without a job get one when no deploy of their app is active, and `queued`/`building`/
  `deploying` deployments whose job ended or vanished without closing them (a worker crash, reboot or
  power cut: `jobs.recover_stale` fails only the job) are closed as `failed`/`cancelled`, their
  half-started container removed and the app's next deployment started. **Cancel** on such a
  deployment closes it at once. Containers
  labelled `deployer.cohost_app` and `cohost-*.caddy` files (copies a co-host device runs for its main
  Deployer) are left alone.

## API (`/v1/projects/{pid}`)

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/apps` | viewer+ | – | `App[]` |
| POST | `/apps/detect` | developer+ | `{repo_url, branch?}` | draft `{name, repo_url, branch, root_dir, preset, install_command, build_command, start_command, output_dir, container_port, env_keys, database_access_suggested, detected: [{what, from}], warnings, private}`, never stored ("Connect a Git repository") |
| POST | `/apps` | developer+ | `{name, repo_url, branch?, root_dir?, preset, install_command?, build_command?, start_command?, output_dir?, container_port?, env?: {k:v}, repo_token?, use_github_connection?, api_key_id?, database_access?, cohost?, cohost_share_repo_access?, target?, cloud_connection_id?}` (a cloud `target` needs admin+, CLOUD.md) | `App & {warnings: string[]}` (201); allocates `port`, generates `webhook_secret`; `database_access: true` needs admin+; `use_github_connection` clones with the creator's GitHub connection and adds the webhook |
| GET | `/apps/{id}` | viewer+ | – | `App` |
| PATCH | `/apps/{id}` | developer+ | partial of the above (`repo_token: null` clears; turning `database_access` on needs admin+, 403 `forbidden`; changing `cohost` / `cohost_share_repo_access` needs admin+) | `App & {teardown_job_id, warnings}` (changes apply on the next deploy; `warnings`: a repository change whose GitHub webhook could not be moved; `cohost` moves the hostnames between tunnels at once and starts the co-host copies of the live deployment) |
| DELETE | `/apps/{id}` | admin+ | – | `{job_id, teardown_job_id, warnings}` (`app.remove`; `app.cloud_teardown` for cloud targets, else null; the app's Cloudflare hostnames are removed best effort: with Cloudflare unreachable or the token revoked the app is still deleted and `warnings` names each DNS record to delete by hand) |
| GET | `/apps/{id}/env` | admin+ | – | `{env: {k:v}}` plain values (audit `app.env.reveal`) |
| GET | `/apps/{id}/webhook` | developer+ | – | `{url, secret}` — url `<public_url>/v1/hooks/github/{app_id}`; audit `app.webhook.reveal` |
| POST | `/apps/{id}/webhook/rotate` | developer+ | – | `{url, secret, hook_active, warnings}` (also updates the GitHub hook of a connected app) |
| POST | `/apps/{id}/deploy` | developer+ | `{branch?}` | `Deployment` (202) |
| GET | `/apps/{id}/deployments?limit=20&before=<deployment id>` | viewer+ | – | `{deployments: Deployment[] (log omitted), has_more}`; next page: `before` = the last row's id |
| GET | `/apps/{id}/deployments/{dep}` | viewer+ | `?log=1` includes the log | `Deployment` |
| POST | `/apps/{id}/deployments/{dep}/cancel` | developer+ | – | `Deployment` |
| POST | `/apps/{id}/deployments/{dep}/rollback` | developer+ | – | `Deployment` (202, new one) |
| GET | `/apps/{id}/logs?tail=200&device_id=` | viewer+ | – | `{lines: string[], container}` — the last `tail` (≤ 500) lines the worker copied from `docker logs` of the live container into Redis (see below); `container` is the live container name or null. With `device_id`: the co-host copy's logs, read from that device (`apps.logs`; 503 `device_offline`) |
| POST | `/apps/{id}/domains` | admin+ (uses the instance owner's Cloudflare link; 409 `not_linked`) | `{hostname, overwrite?}` | `Domain` (same rules as REMOTE_ACCESS.md, `target_type: app`, `app_id`; zone resolved from the hostname) |
| DELETE | `/apps/{id}/domains/{domain_id}` | admin+ | – | `{ok}` (cloud targets: `{ok, warnings}`) |
| POST | `/apps/{id}/domains/{domain_id}/check` | admin+ | – | `{job_id}` - cloud targets: look for the DNS records / validation again (CLOUD.md "Custom domains") |

Webhook (no auth header): `POST /v1/hooks/github/{app_id}` with GitHub's `X-Hub-Signature-256`
(HMAC-SHA256 of the raw body with the app's secret, constant-time compare; 401 `bad_signature`
otherwise), `X-GitHub-Event: ping` → 200 `{ok}`; `push` for `refs/heads/<branch>` → 202
`{deployment_id}` (`trigger=webhook`, `commit_sha`, first line of the head commit message); other
branches/events → 200 `{ignored: true}`. Coalescing: a push while a deployment is still `queued`
for the same app replaces its commit instead of adding another. Rate limit 6/min per app (every
delivery counts, including rejected signatures; 429 `rate_limited`). Unknown app → 404. When the
instance owner has disabled the project owner's account → 403 `account_disabled`. Bodies over
5 MB → 413 `payload_too_large`; an `after` that is not a 40-hex sha deploys the branch head instead.

Runtime logs: the API has no Docker access. `GET /apps/{id}/logs` enqueues nothing; instead the
worker keeps the last 500 lines of each live container in Redis (`apps:logs:<app_id>`, a capped
list refreshed by a `docker logs --since` poll every 10 s in the scheduler) and the API reads that.

Build log: while a deployment runs, the worker appends new lines to Redis (`deploy-log:<deployment_id>`)
every 2 s and `GET .../deployments/{dep}?log=1` serves that copy. The `deployments.log` row is saved
only at each step, every 15 s and when the job ends (then the Redis copy is deleted): every UPDATE
rewrites the whole log (up to 1 MB) into MariaDB's ROW binlog, so saving it every 2 s bloated it.

```ts
type App = { id; project_id; name; slug; repo_url; branch; root_dir; preset; install_command; build_command;
  start_command; output_dir; container_port: number|null; env_keys: string[]; has_repo_token: boolean;
  api_key_id: string|null; database_access: boolean;
  cohost: boolean; cohost_share_repo_access: boolean;                  // docs/COHOSTING.md
  replicas: {device_id; device_name; online: boolean; status: "pending"|"building"|"live"|"failed"|"stopped";
             deployment_id; error; last_seen_at}[];
  github: {connected_by_email: string; hook_active: boolean} | null;  // "Connect a Git repository"
  port: number; local_url: string|null; urls: string[]; live_deployment: Deployment|null;
  target: "local"|"aws_static"|"aws_app"|"firebase_hosting"|"firebase_app"; cloud_connection_id: string|null;
  cloud: {provider; connection_name; url: string|null; resources: string[]} | null;   // docs/CLOUD.md
  domains: Domain[]; created_at; updated_at };
type Deployment = { id; app_id; status; trigger; commit_sha; commit_message; branch; image_tag; created_at;
  started_at; finished_at; error; rollback_of; log?: string; job_id; target_url: string|null };
```

`local_url` is `http://localhost:<port>`, or the public URL's host with the port when that host is a
LAN IP or local name (a public/Cloudflare host is never used: the tunnel doesn't carry app ports). The
dashboard labels it "On this PC". `urls` adds `https://<hostname>` per active app domain.

Export/import: `apps` (with `env` decrypted, `repo_token` decrypted, `webhook_secret`
decrypted — re-encrypted on import; `port` and `live_deployment_id` omitted) and `domains` with
`target_type: app`; deployments are not exported. The importing instance allocates fresh ports and
does not deploy automatically. An instance import keeps app ids and their hostnames (same
Cloudflare link); a projects import gives apps new ids (`api_key_id` remapped to the imported key) and
skips app hostnames, because their DNS records and tunnel ingress belong to the source instance —
add the hostname again on the new one.

## Dashboard — project tab **Deploys**

- Apps list (name, preset, branch, live status dot, local URL, last deploy relative time) → app page.
- **New app** dialog, step 1 *Choose a repository*: the connected GitHub account's repositories
  (search, private badge, default branch, last push) or *Connect GitHub* (explains the access it asks
  for), plus "paste a repository URL" and "configure by hand". Step 2: the detected settings
  ("Detected: Flask app (requirements.txt, app/__init__.py)", warnings) in the usual fields (name,
  repository URL + branch, preset with per-preset fields, root directory), environment variables
  pre-seeded with the `.env.example` keys (empty values highlighted "fill in"), database access
  pre-ticked when suggested (admins; others see the suggestion), attach an API key, **Create & deploy**.
  Repositories picked through the connection have no token field; *Use a token instead* switches to the
  manual path ("private repository" + step-by-step fine-grained token instructions).
- Account settings: *Repository access*, "GitHub: connected as <login>" + **Disconnect**.
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
Connect a Git repository: `tests/test_repo_detect.py` (every rule, a HawkerHub-shaped Flask fixture,
monorepos, env keys) and `tests/test_github_integration.py` (connect flow and same-user check,
repo listing, detect, create with a connection: clone token, webhook create/rotate/delete, localhost
warning, removed connection, migration) against a fake GitHub; dashboard repo filter, draft mapping
and env seeding in `deploys.test.ts`.
