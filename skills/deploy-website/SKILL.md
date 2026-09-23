---
name: deploy-website
description: "Use when the user wants to deploy, publish, host or 'put online' a website or web app, or asks how to use their self-hosted Deployer instance for a site. Walks an agent through Deployer (projects, databases, API keys, remote access, push-to-deploy apps) and, before anything is deployed, ALWAYS asks the user which platform to deploy to - with the options ordered by their past deployment activity. Never deploys without that answer."
---

# Deploy a website with Deployer

Deployer is a self-hosted backend + deployment platform (MariaDB, MongoDB, Redis, a data API,
backups, host devices, Cloudflare tunnels, push-to-deploy) that runs on the user's own Windows PC.
A site can be deployed in two ways:

1. **On the Deployer instance itself** (`docs/DEPLOYMENTS.md`): an *app* built from the site's
   Git repository, run as a container on the PC, served on a local port and, when Cloudflare is
   linked, on the user's own hostname. Good for hobby/LAN/home-server sites and anything that
   should stay on the user's hardware.
2. **On an external platform** (Vercel, Netlify, Cloudflare Pages, GitHub Pages...) with the data
   and API living in Deployer (Step 1 below). Good for global CDN reach and serverless functions.

## Hard rule: always ask which platform

Before you run, write or suggest any deploy command, ask the user which platform to deploy to.
Never assume, never skip the question, and confirm even when your evidence points to a single
platform. Order the options by the user's past activity.

Gather evidence first (read-only, fast):

- config files in the project: `vercel.json` / `.vercel/`, `netlify.toml`, `wrangler.toml`,
  `.github/workflows/*pages*`, `firebase.json`, `render.yaml`, `fly.toml`, `deployer-*.json`;
- git history: `git log --oneline -30` for deploy/publish commits and CI workflow names;
- the user's memory notes and earlier conversation (platforms they used, accounts they have);
- an existing Deployer project / API key / app for this site (a `deployer-<slug>-<role>.json`
  config, or `GET <url>/v1/projects/{id}/apps` listing an app whose `repo_url` is this repo).

Then ask, in this exact shape (adapt the list; keep the first line):

> Which platform should I deploy this site to? Based on what I found, in order:
> 1. **This Deployer instance** - an app for this repo already exists in project "Shop" (recommended)
> 2. **Vercel** - `vercel.json` present and the last 3 deploy commits used it
> 3. **Cloudflare Pages** / **Netlify** / **GitHub Pages** - no past use found
>
> Reply with a number or a name. I won't deploy until you pick one.

Use `AskUserQuestion` when the host offers it, putting the recommended option first. If no
evidence exists, list the platforms alphabetically and say so. Record the answer in memory
(project note: "deploys to <platform>") so next time it is the recommended option - but still ask.

## Step 1 - Backend in Deployer

The dashboard is at the instance's public URL (default `http://localhost:8080`; LAN or
`https://<hostname>` when remote access is set up). All API calls go under `<url>/v1`.

1. **Project**: Projects → *New project* (or `POST /v1/projects {name}` with the user's session).
   One project per site.
2. **Databases**: Databases tab → *Add database*. Managed MariaDB (SQL) and MongoDB (NoSQL) can be
   used together; external databases can be linked too. Managed ones are backed up automatically
   (docs/BACKUPS.md).
3. **Schema and data**: Schema tab (ER diagram, DDL export), Data tab (rows/documents), Query tab
   (notebook or terminal).
4. **API key for the site**: API keys tab → *Create key*.
   - `anon` = read-only, safe for browsers;
   - `service` = read/write, **server-side only** (never ship it to a browser or phone).
   Admins can *Reveal* a key later and *Download config JSON*
   (`deployer-<project>-<role>.json` with `url`, `project_id`, `api_key`, `data_sources`,
   `endpoints`). Full API tutorial: `docs/DATA_API.md`.
5. **Reachability**: a site hosted elsewhere must reach the instance. Localhost is not enough:
   turn on LAN access or, for the internet, link the user's own Cloudflare account under
   Settings → Domains & remote access (docs/REMOTE_ACCESS.md). Never expose the plain `:8080`
   listener to the internet directly. (An app deployed *on* the instance reaches it directly.)

Using the key from the site (example, JavaScript):

```js
const cfg = await import("./deployer-myshop-anon.json", { with: { type: "json" } });
const res = await fetch(`${cfg.deployer.url}/projects/${cfg.deployer.project_id}` +
  `/data-sources/${SOURCE_ID}/tables/products/rows?limit=50`, {
  headers: { Authorization: `Bearer ${cfg.deployer.api_key}` },
});
const { rows } = await res.json();
```

Put the config's `url` and the key in the platform's environment variables (`DEPLOYER_URL`,
`DEPLOYER_API_KEY`); commit only the `anon` key if any, never the `service` key.

## Feature status (check before promising anything)

Deployer changes quickly. Before telling the user a feature exists, confirm it on their instance
(`GET <url>/v1/health` for the version; the dashboard tab or endpoint named below).

| Feature | Status | Where |
|---|---|---|
| Projects, SQL + NoSQL databases, schema, data browser, query notebook/terminal | Available | dashboard tabs |
| Backups + point-in-time restore, export/import | Available | Backups tab, Settings |
| API keys (anon/service), reveal later, config JSON, data API | Available | API keys tab, `docs/DATA_API.md` |
| Remote access with the user's domain (guided Cloudflare setup) | Available | Settings → Domains & remote access |
| Push-to-deploy apps (static / Node / Python / Dockerfile), logs, rollback, app hostnames | Available | project → **Deploys** |
| App access to the project's databases (`database_access`, admin-only) | Available | app settings |
| Step-by-step GitHub token help for private repos | Available | New app → *Private repository* |
| **Connect a Git repository** (connect GitHub once, pick a repo, everything detected and pre-filled, token + webhook automatic) | Available when `GET /v1/integrations/github` exists (older instances: manual form) | Deploys → New app |
| **Co-hosting, phase 1**: live two-way sync of a project's databases to a member's own PC, Git-style conflict resolution, per-row history | Available when `GET /v1/projects/{id}/cohosting/eligibility` exists (not yet exercised with a real second PC) | Members → *Co-host*; Databases → *Copy to my device*, copies, conflicts (`/projects/{id}/databases/{sid}/sync`) |
| **Co-hosting, phase 2**: apps also running on co-host PCs behind one address with automatic failover | **Planned, not built** | - |
| Apps running on host devices | **Not built** (apps run on the main Deployer PC only) | - |

Never describe a "being built" or "planned" feature as available; say what the user can do today
instead (e.g. "paste a token by hand for now").

## Step 2a - Deploy on this Deployer instance

Only after the user picked **this Deployer instance**. The code must be in a Git repository the
instance can clone over HTTPS (GitHub). For a private repository the **user** provides access -
never ask for a token in chat:

- **Preferred - Connect a Git repository** (see Feature status): the user clicks *Connect GitHub*
  once in Deploys → New app (it asks GitHub for repository read access and webhooks), picks the
  repository, and Deployer detects the preset, commands, output folder, port, monorepo folder,
  environment variable names (from `.env.example`) and whether the app needs database access, then
  creates the push webhook itself (needs a public URL). Your job is only to check the detected values
  with the user and fill in environment variable *values* they give you. API: `POST
  /v1/projects/{id}/apps/detect {repo_url}` returns the draft; create with
  `use_github_connection: true`.
- **Fallback - a token:** a fine-grained GitHub token (*Only select repositories* → the repo;
  *Contents: Read-only*). The New app form shows the exact steps under *Use a token instead*; the
  user pastes the token there.

1. Push the code to the repository's branch (default `main`). Commit any missing `package.json`
   build script or `requirements.txt` first; the preset decides the build:

   | Preset | Build | Runs |
   |---|---|---|
   | `static` | `npm ci` + `npm run build` when a package.json exists; output dir auto-detected (`dist`, `build`, `out`, `public`, `.`) | nginx, port 80 |
   | `node` | `npm ci` (+ optional build command) | `npm start` (or `start_command`) with `PORT=3000` |
   | `python` | `pip install -r requirements.txt` | `start_command` (required), `PORT=8000` |
   | `dockerfile` | the repo's Dockerfile (`root_dir` relative) | the image's CMD on `container_port` |

2. Create the app: project → **Deploys** → *New app* in the dashboard, or with the user's session
   `POST /v1/projects/{id}/apps {name, repo_url, branch?, root_dir?, preset, install_command?,
   build_command?, start_command?, output_dir?, container_port?, env?, api_key_id?}`
   (developer role or higher; `repo_token` only through the dashboard field the user fills in).
   Attach the project API key with `api_key_id` so the container gets `DEPLOYER_API_KEY`,
   `DEPLOYER_URL` and `DEPLOYER_PROJECT_ID` automatically; use those names in the code instead of
   hard-coding the config JSON.
   - If the code talks to the project's managed MariaDB / MongoDB **directly** (PyMySQL, PyMongo,
     mysql2, mongoose…), a project **admin** must tick *Connect to this project's databases*
     (`database_access: true`); the container then gets `DEPLOYER_DB_<SOURCE>_URL` (+ `_HOST`,
     `_PORT`, `_USER`, `_PASSWORD`, `_DATABASE` for SQL). Prefer those names; an app with its own
     names can set them under Environment with host `mariadb` / port `3306` or `mongodb:27017`.
3. First deployment: *Deploy now* or `POST /v1/projects/{id}/apps/{app_id}/deploy` → a deployment
   in `queued` → `building` → `deploying` → `live`. Follow the build log with
   `GET .../deployments/{dep_id}?log=1` every few seconds; on `failed`, read `error` + the log tail,
   fix the repo, push, deploy again. A failed deployment never replaces the running one.
4. Push-to-deploy: `GET .../apps/{app_id}/webhook` gives the payload URL and secret; the **user**
   adds them in GitHub (repo → Settings → Webhooks, content type `application/json`, just the
   push event). From then on every push to the branch deploys. (With a connected repository this
   step is automatic.) GitHub can only reach the webhook when the instance has a public URL
   (Cloudflare domain); on `http://localhost` the user deploys with *Deploy now* instead.
5. URLs: `local_url` (`http://localhost:81xx`, LAN when enabled) always works. For the internet,
   the user links Cloudflare (Settings → Domains & remote access), then
   `POST .../apps/{app_id}/domains {hostname}` (admin) creates the DNS record, tunnel ingress and
   Caddy route; the app then lists it under `urls`.
6. Runtime: `GET .../apps/{app_id}/logs?tail=200` (container stdout/stderr, last 500 lines);
   older successful deployments can be re-activated with `POST .../deployments/{dep_id}/rollback`.

Limits to tell the user: one PC, 512 MB RAM per app by default, no persistent volumes (use the
project's databases), builds run through Docker on that PC and take a few minutes the first time.

## Step 2b - Frontend / serverless on an external platform

Only after the user answered the platform question:

| Platform | What to do | Deployer bits to set |
|---|---|---|
| Vercel | `vercel` / `vercel --prod`, or connect the Git repo | env vars `DEPLOYER_URL`, `DEPLOYER_API_KEY` |
| Netlify | `netlify deploy --prod`, or Git integration | same, in *Site settings → Environment* |
| Cloudflare Pages | `wrangler pages deploy <dir>` or Git integration | same; the Deployer tunnel can share the zone |
| GitHub Pages | workflow that builds and publishes `dist/` | only the `anon` key (static site, public) |
| Deployer host device / co-host PC | not available yet (apps run on the main Deployer PC only; co-host failover is planned). Offer "this Deployer instance". | - |

After deploying: open the site, run one real request against the data API from it, and check the
project's query log / audit (Deployer dashboard) shows the call. Then tell the user the URL, the
platform used, and where the key lives.

## People, sign-in and co-hosting

- **Adding people:** project → **Members → Invite** (single-use link, optionally locked to an
  email, with a role: viewer = read-only, developer = edit data/schema and deploy, admin =
  members/keys/settings). Public signup should stay **off** on an internet-facing instance: any
  signed-in user can create a project and deploy code that runs on the owner's PC.
- **Sign-in methods:** email + password always works with an invite. Google/GitHub sign-in need the
  owner's own OAuth apps with the instance's public URL registered as callback
  (`<url>/v1/auth/oauth/{google|github}/callback`); the dashboard (Settings → Instance) and Deployer
  Control (*Sign-in apps*) show those URLs. A Google app in *Testing* mode only admits listed test
  users; publishing it lifts that.
- **Members don't need to install anything** to edit SQL/data: the web dashboard's Query, Data and
  Schema tabs work for any member with the developer role.
- **Co-hosting** (see Feature status): a member with the *Co-host* flag who has their own Deployer
  attached as a host device can keep a live, two-way synced copy of the project's databases on
  their PC. Offer it only when the eligibility endpoint says `offer: true`. Conflicts are never
  resolved automatically: both versions are kept and a person picks or combines them in
  *Databases → Sync*. Co-hosts never see the owner's API keys, OAuth settings or Cloudflare token.

## Do / don't

- Do ask the platform question every time, even for a redeploy - the answer may change.
- Do use the `anon` key on the client and the `service` key only on servers/functions.
- Don't create accounts or enter passwords or secrets on the user's behalf; ask them to paste
  repository tokens, webhook secrets and keys into the platform's settings themselves.
- Don't hand-run `docker` on the user's PC to "help" a deployment; use the app's deploy endpoint
  and its log.

## Where things are

- Instance dashboard: `http://localhost:8080` (or the public URL in Settings)
- Docs in the repo: `docs/DEPLOYMENTS.md`, `docs/DATA_API.md`, `docs/REMOTE_ACCESS.md`,
  `docs/BACKUPS.md`, `docs/API.md`
- Install / update the instance: `DeployerSetup.exe`, or `deployer update` on the PC
