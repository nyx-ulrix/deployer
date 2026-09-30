---
name: deploy-website
description: "Use when the user wants to deploy, publish, host or 'put online' a website or web app, or asks how to use their self-hosted Deployer instance for a site. Walks an agent through Deployer (projects, databases, API keys, remote access, push-to-deploy apps on the PC or on the user's own AWS / Firebase account) and, before anything is deployed, ALWAYS asks the user which platform to deploy to - with the options ordered by their past deployment activity. Never deploys without that answer."
---

# Deploy a website with Deployer

Deployer is a self-hosted backend + deployment platform (MariaDB, MongoDB, Redis, a data API,
backups, host devices, Cloudflare tunnels, push-to-deploy) that runs on the user's own Windows PC.
A site can be deployed in three ways:

1. **On the Deployer instance itself** (`docs/DEPLOYMENTS.md`): an *app* built from the site's
   Git repository, run as a container on the PC, served on a local port and, when Cloudflare is
   linked, on the user's own hostname. Good for hobby/LAN/home-server sites and anything that
   should stay on the user's hardware. Stops serving when the PC is off.
2. **Through Deployer on the user's own AWS or Firebase account** (`docs/CLOUD.md`): the same app,
   built on the PC, but served from the cloud - AWS S3 + CloudFront or Firebase Hosting for static
   sites, AWS App Runner or Firebase + Cloud Run for full apps (Node, Python, Dockerfile). It **keeps
   serving when the PC is off**, is billed by AWS / Google to the user, and gets only its own
   environment variables (no `DEPLOYER_URL` / `DEPLOYER_API_KEY` / `DEPLOYER_DB_*`).
3. **On an external platform** (Vercel, Netlify, Cloudflare Pages, GitHub Pages...) with the data
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
  config, or `GET <url>/v1/projects/{id}/apps` listing an app whose `repo_url` is this repo - its
  `target` says whether it already runs on the PC or on AWS / Firebase);
- the cloud accounts connected to Deployer: MCP `list_cloud_targets` / `list_cloud_connections`, or
  `GET <url>/v1/projects/{id}/cloud/targets` (`available: true` = an account is connected).

Then ask, in this exact shape (adapt the list; keep the first line):

> Which platform should I deploy this site to? Based on what I found, in order:
> 1. **This Deployer instance** - an app for this repo already exists in project "Shop" (recommended)
> 2. **AWS through Deployer** (S3 + CloudFront for a static site, App Runner for a server) - keeps
>    serving when the PC is off; an AWS account is connected in Deployer
> 3. **Firebase through Deployer** (Hosting for a static site, Cloud Run for a server) - keeps serving
>    when the PC is off; no Firebase account connected yet
> 4. **Vercel** - `vercel.json` present and the last 3 deploy commits used it
> 5. **Cloudflare Pages** / **Netlify** / **GitHub Pages** - no past use found
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
   used together; external databases can be linked too (one on the same PC: host = the PC's network
   IP, never `localhost`; `host.docker.internal` only with Docker Desktop). Managed ones are backed up automatically
   (docs/BACKUPS.md).
3. **Schema and data**: Schema tab (ER diagram, DDL export), Data tab (rows/documents), Query tab
   (notebook or terminal).
4. **API key for the site**: API keys tab → *Create key*.
   - `anon` = read-only, but it reads **all** data in the project (every table and collection,
     including users and password hashes). It is NOT safe to put in a browser, phone app or public
     repo unless everything in the project is public;
   - `service` = read/write, **server-side only** (never ship it to a browser or phone).
   Admins can *Reveal* a key later and *Download config JSON*
   (`deployer-<project>-<role>.json`: one top-level `deployer` object holding `url` (already ends
   in `/v1`), `project_id`, `project`, `role`, `api_key`, `data_sources` (`[{id, name, kind,
   engine}]`) and `endpoints` (path templates)). Full API tutorial: `docs/DATA_API.md`.
5. **Reachability**: a site hosted elsewhere must reach the instance. Localhost is not enough:
   turn on LAN access or, for the internet, link the user's own Cloudflare account under
   Settings → Domains & remote access (docs/REMOTE_ACCESS.md). Never expose the plain `:8080`
   listener to the internet directly. (An app deployed *on* the instance reaches it directly.)

Using the key from the site's server side (a backend, or a serverless / edge function on the
hosting platform; example, JavaScript):

```js
// A dynamic JSON import resolves to a module namespace: the file's content is under `default`.
const { default: { deployer: cfg } } = await import("./deployer-myshop-anon.json", { with: { type: "json" } });
const source = cfg.data_sources.find((s) => s.name === "main"); // the database holding `products`
const res = await fetch(`${cfg.url}/projects/${cfg.project_id}` +
  `/data-sources/${source.id}/tables/products/rows?limit=50`, {
  headers: { Authorization: `Bearer ${cfg.api_key}` },
});
const { rows, total } = await res.json();
```

In production put the config's `url` and the key in the platform's environment variables
(`DEPLOYER_URL`, `DEPLOYER_API_KEY`) and read them only in server-side code; never commit a key
(keep the config file out of git, e.g. in `.gitignore`). The function returns
only the fields the page needs. Ship the `anon` key to the browser only if the user confirms that
every table and collection in the project is public data. The data, query and schema endpoints allow
cross-origin `fetch` (CORS, no cookies); an `https` page needs the instance's `https` remote-access URL.

### Connecting an AI agent (MCP)

If the instance has the MCP server (see Feature status), you can work on the project through tools
instead of raw HTTP: API keys tab → *Show usage* → **AI agents (MCP)** has the command, e.g.

```bash
claude mcp add --transport http deployer <url>/v1/projects/<project_id>/mcp --header "Authorization: Bearer <key>"
```

Tools: `list_data_sources`, `get_schema`, `list_rows`, `list_documents` (any key) plus `run_query`,
`insert_/update_/delete_row`, `insert_/update_/delete_document`, `list_apps`, `get_app`,
`deploy_app`, `deployment_status`, `app_logs`, `list_cloud_connections` and `list_cloud_targets`
(service key only; app tools report each app's `target` and cloud URL). Ask the user for an `anon` key
unless they want the agent to change data or deploy; a `service` key can change production data.
Limits: 200 rows / 256 KB per result, 60 tool calls a minute. Details: `docs/MCP.md`.

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
| **Co-hosting, phase 2**: apps also running on co-host PCs behind one address with automatic failover | Available when `GET /v1/projects/{id}/apps/{app_id}` returns `cohost` (not yet exercised with two real PCs) | App → Settings → *Co-host this app* (admin); per-PC status there; header "Also running on N co-host PCs" |
| MCP server for AI agents (data, queries, schema, apps; anon = read-only tools, no queries) | Available when `POST /v1/projects/{id}/mcp` answers `initialize` | API keys → *Show usage* → *AI agents (MCP)*, `docs/MCP.md` |
| **AWS hosting** through Deployer: static sites on S3 + CloudFront (`aws_static`), full apps on App Runner (`aws_app`), custom domains; keeps serving with the PC off | Available when `GET /v1/projects/{id}/cloud/targets` exists and lists them `available` (an AWS account connected); not yet exercised against a live AWS account | Settings → Cloud accounts (owner); app → *Where should this run?* (admin); `docs/CLOUD.md` |
| **Firebase hosting** through Deployer: Firebase Hosting (`firebase_hosting`), full apps on Cloud Run behind Hosting (`firebase_app`, Blaze plan), custom domains; keeps serving with the PC off | Available when `GET /v1/projects/{id}/cloud/targets` exists and lists them `available` (a Firebase account connected); not yet exercised against a live Google account | same as AWS |
| Cloud databases (RDS, DynamoDB, Firestore, Realtime Database) | **Not built** (planned, `docs/CLOUD.md` C2) - cloud apps use their own database credentials under Environment for now | - |
| Deploys that run without the PC (GitHub Actions builds) | **Not built** (planned, `docs/CLOUD.md` C3) - cloud apps serve with the PC off, but deploying needs it on | - |
| Apps running on host devices | **Not built** (apps run on the main Deployer PC only) | - |

Never describe a "being built" or "planned" feature as available; say what the user can do today
instead (e.g. "paste a token by hand for now").

## Step 2a - Deploy on this Deployer instance

Only after the user picked **this Deployer instance**, **AWS through Deployer** or **Firebase through
Deployer** (the cloud ones: see "Cloud targets" at the end of this step). The code must be in a Git repository the
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
   | `static` | `npm ci` (`npm install` without a lockfile) + `npm run build` when a package.json exists; output dir auto-detected (`dist`, `build`, `out`, `public`, `.`) | nginx, port 80 |
   | `node` | `npm ci`, or `npm install` without a lockfile (+ optional build command) | `npm start` (or `start_command`) with `PORT=3000` |
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
     Keep a MariaDB connection pool small (about 5): each database user is capped at 20 connections
     by default, shared with Deployer's own data API.
3. First deployment: *Deploy now* or `POST /v1/projects/{id}/apps/{app_id}/deploy` → a deployment
   in `queued` → `building` → `deploying` → `live`. Follow the build log with
   `GET .../deployments/{dep_id}?log=1` every few seconds; on `failed`, read `error` + the log tail,
   fix the repo, push, deploy again. A failed deployment never replaces the running one.
4. Push-to-deploy: `GET .../apps/{app_id}/webhook` gives the payload URL and secret; the **user**
   adds them in GitHub (repo → Settings → Webhooks, content type `application/json`, just the
   push event). From then on every push to the branch deploys. (With a connected repository this
   step is automatic.) GitHub can only reach the webhook when the instance has a public URL
   (Cloudflare domain); on `http://localhost` the user deploys with *Deploy now* instead. A connected
   repository's webhook follows the public URL automatically once remote access is set up.
5. URLs: `local_url` (`http://localhost:81xx`, or the LAN address) only works on this PC or its
   network, never from the internet, even after remote access is set up. For the internet,
   the user links Cloudflare (Settings → Domains & remote access), then
   `POST .../apps/{app_id}/domains {hostname}` (admin) creates the DNS record, tunnel ingress and
   Caddy route; the app then lists it under `urls`.
6. Runtime: `GET .../apps/{app_id}/logs?tail=200` (container stdout/stderr, last 500 lines);
   older successful deployments can be re-activated with `POST .../deployments/{dep_id}/rollback`.

Limits to tell the user: one PC, 512 MB RAM per app by default, no persistent volumes (use the
project's databases), builds run through Docker on that PC and take a few minutes the first time.

### Cloud targets (AWS / Firebase through Deployer)

The same app, served from the user's own cloud account so it **keeps running when the PC is off**
(check Feature status first):

1. **Account**: the instance **owner** connects it under *Settings → Cloud accounts* (guided: an IAM
   user with the policy shown there, or a Firebase service account with the listed roles; Deployer
   validates it). Never ask for AWS keys or a service-account file in chat - the user pastes them there.
2. **Target**: a project **admin** picks it under the app's *Where should this run?* (New app or app
   Settings), or `target` + `cloud_connection_id` on `POST/PATCH .../apps`:
   - static sites (preset `static`): `aws_static` (S3 + CloudFront) or `firebase_hosting`;
   - servers (Node / Python / Dockerfile): `aws_app` (App Runner) or `firebase_app` (Cloud Run behind
     Firebase Hosting; needs the Blaze plan).
   Each costs money on the user's account (the chooser explains the cost drivers) - confirm with the user.
3. **Environment**: cloud apps get **only their own variables** - no `DEPLOYER_URL`,
   `DEPLOYER_API_KEY` or `DEPLOYER_DB_*`, because the PC may be off. A cloud app that needs data must use
   a database reachable from the cloud with credentials set under Environment (Deployer's own cloud
   databases are not built yet).
4. **Deploy** as above (*Deploy now*, `deploy_app`, push webhook). The build log shows the cloud steps
   (upload, rollout status); `deployment_status` returns `target_url`. First CloudFront rollouts take
   ~15 minutes to answer.
5. **Domain**: `POST .../apps/{app_id}/domains {hostname}` (admin, after the first deploy): with
   Cloudflare linked the DNS records are created automatically; otherwise the app's Domains card lists
   the records for the user to add, then *Check again*.
6. **Moving or deleting** the app removes what Deployer created in the cloud account (the dashboard
   lists it first; failures are reported by the teardown job).

## Step 2b - Frontend / serverless on an external platform

Only after the user answered the platform question:

| Platform | What to do | Deployer bits to set |
|---|---|---|
| Vercel | `vercel` / `vercel --prod`, or connect the Git repo | env vars `DEPLOYER_URL`, `DEPLOYER_API_KEY` |
| Netlify | `netlify deploy --prod`, or Git integration | same, in *Site settings → Environment* |
| Cloudflare Pages | `wrangler pages deploy <dir>` or Git integration | same; the Deployer tunnel can share the zone |
| GitHub Pages | workflow that builds and publishes `dist/` | no server side: no key at all unless every table in the project is public (an `anon` key reads all data); otherwise pick a platform with functions |
| AWS / Firebase through Deployer | See "Cloud targets" in Step 2a: the owner connects the account, an admin picks the target, then deploy as usual | `target`, `cloud_connection_id` on the app (admin) |
| Deployer host device / co-host PC | Deploy on "this Deployer instance" first, then a project admin ticks *Co-host this app*: every co-host PC of the project (a member with the Co-host flag whose PC is shared with the project and, for apps with database access, holds live copies of its databases) builds and runs the same commit, and the app's hostnames fail over between PCs. Only one app per Deployer can be co-hosted for now (409 `cohost_limit`: turn it off on the other app first). Private repositories also need *Let co-hosts clone this private repository* (the token becomes readable on those PCs). | `cohost`, `cohost_share_repo_access` on the app (admin) |

After deploying: open the site, run one real request against the data API from it, and check the
project's query log / audit (Deployer dashboard) shows the call. Then tell the user the URL, the
platform used, and where the key lives.

## People, sign-in and co-hosting

- **Adding people:** project → **Members → Invite** (single-use link, optionally locked to an
  email, with a role: viewer = read-only, developer = edit data/schema and deploy, admin =
  members/keys/settings). The link is built from the public URL, so while that is
  `http://localhost:8080` it only opens on the Deployer PC (the dialog warns): set up remote access
  first to invite someone on another device. Public signup should stay **off** on an internet-facing instance.
  By default only the instance owner can create projects (a member gets 403 and must ask the owner);
  if the owner turns that off, any signed-in user can create a project and deploy code that runs on
  the owner's PC. The owner can disable an account and see every project under Settings → Instance.
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
  An app with *Co-host this app* also runs on those PCs (against their database copies; writes sync
  back) and its hostnames stay up while any one PC is on.

## Do / don't

- Do ask the platform question every time, even for a redeploy - the answer may change.
- Do keep keys on servers/functions. The `anon` key reads all project data, so put it on the client
  only when the whole project is public; the `service` key never goes on the client.
- Don't create accounts or enter passwords or secrets on the user's behalf; ask them to paste
  repository tokens, webhook secrets and keys into the platform's settings themselves.
- Don't hand-run `docker` on the user's PC to "help" a deployment; use the app's deploy endpoint
  and its log.

## Where things are

- Instance dashboard: `http://localhost:8080` (or the public URL in Settings)
- Docs in the repo: `docs/DEPLOYMENTS.md`, `docs/DATA_API.md`, `docs/REMOTE_ACCESS.md`,
  `docs/BACKUPS.md`, `docs/API.md`
- Install / update the instance: `DeployerSetup.exe`, or `deployer update` on the PC
