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
   environment variables plus, with database access, its databases **in the same cloud account** (no
   `DEPLOYER_URL` / `DEPLOYER_API_KEY`, nothing on the PC). Its database can live there too (RDS /
   DynamoDB in AWS, Firestore / Realtime Database in Firebase), so the whole site runs with the PC off,
   like Vercel + Supabase. With **GitHub Actions builds** pushes even *deploy* with the PC off: GitHub
   builds each push and uploads it to the cloud (`docs/CLOUD.md` "C3").
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

When the site needs a database, ask where it should live in the same message (or right after), in plain
words, ordered the same way (a cloud app needs a cloud database in **its** account to keep working with
the PC off; MCP `cloud_database_options` has the texts and costs):

> Where should the site's database live?
> 1. **In your AWS account** (recommended with AWS App Runner) - RDS (MySQL / MariaDB / PostgreSQL, about
>    US$15-20/month for the smallest) or DynamoDB (NoSQL, pay per read / write, often cents); stays up when
>    the PC is off; AWS bills you
> 2. **In your Firebase project** (recommended with Firebase) - Cloud Firestore (documents, the usual
>    choice) or the Realtime Database (one JSON tree, instant updates); stays up when the PC is off; free
>    quota, then Google bills you
> 3. **On this PC** - MariaDB or MongoDB, free, backed up by Deployer; stops when the PC is off
> 4. **On another server you already have** - Deployer only connects to it
>
> Creating a cloud database costs money on your account, so I'll only do it after you say yes.

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
   IP, never `localhost`; `host.docker.internal` only with Docker Desktop; only the instance owner may
   use Docker names or `172.16-31.x` addresses). Managed ones are backed up automatically
   (docs/BACKUPS.md). The dialog asks *Where should it live?*: **On this PC**, **On another PC or
   server**, **In your AWS account** (SQL: RDS / Aurora; NoSQL: DynamoDB tables - create new or
   connect existing ones; it stays up when the PC is off - use it for apps on AWS App Runner) or **In
   your Firebase project** (NoSQL: connect the project's Cloud Firestore database - `(default)` or a named
   one, created in the Firebase console first - or its Realtime Database, whose default one Deployer can
   create; stays up when the PC is off - use it for Firebase full apps).
   Explain those four to the user in plain words (MCP `cloud_database_options` has the texts and costs;
   DynamoDB = items found by a key you choose, no server, the app uses the AWS SDK, not SQL; Firestore =
   documents in collections, a document can hold its own collections, the app uses the Firebase / Google
   Cloud SDK; Realtime Database = one big JSON tree read and written by path that pushes every change to
   open apps instantly, simple queries on one child - good for chat or presence, while Firestore is the
   usual choice for a new app). Connecting Firestore creates nothing (free); Google bills its reads and
   writes beyond a daily free quota. Creating the default Realtime Database
   (`create_cloud_database` with `engine: "firebase_rtdb"`, `location`) is free by itself but Google then
   bills storage and downloads beyond the free quota, so it also needs the user's yes and
   `confirm_billing: true`. Creating an AWS database is **billed to the user's AWS
   account** (roughly US$15-20/month for the smallest RDS; a DynamoDB table is billed per read, write
   and GB, often cents): get an explicit yes before `create_cloud_database` /
   `POST /v1/projects/{id}/cloud/databases` with `confirm_billing: true` (docs/CLOUD.md "C2-1", "C2-2").
   DynamoDB on-demand backups (`create_cloud_backup`), point-in-time recovery
   (`set_point_in_time_recovery`) and restores (`restore_cloud_backup`, always into a new table and data
   source - the original is never changed) are billable too - same rule.
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

Tools: `list_data_sources`, `get_schema`, `list_rows`, `list_documents`, `list_subcollections`,
`rtdb_read`, `list_cloud_backups` (any key) plus `run_query`, `insert_/update_/delete_row`,
`insert_/update_/delete_document`, `rtdb_write`, `export_documents`, `list_apps`, `get_app`, `deploy_app`,
`deployment_status`, `app_logs`, `list_github_runs`, `list_cloud_targets`, `cloud_database_options` (service
key). The cloud account tools - `list_cloud_connections`, `list_cloud_databases`, `create_cloud_database`,
`create_cloud_backup`, `set_point_in_time_recovery`, `restore_cloud_backup`, `set_build_location` and
`set_app_target` (all billable: only with the user's yes
and `confirm_billing: true`; `set_app_target` also needs `confirm_teardown: true` to delete an app's resources
on its old cloud target) and `connect_cloud_database` - need a project **admin** like their REST routes: a
service key doesn't see them, so ask the user to add the database or pick the target in the dashboard (*Add database → In your AWS account / In your Firebase
project*), then work on its data with the service key. `delete_cloud_database` (service key or admin) deletes a
cloud database: **always ask the user first** - call it with `confirm_delete: false`, show them what
`details.removes` / `keeps` say (a database Deployer created goes from AWS after a final snapshot / backup that
stays, billed for storage; a connected one is only forgotten), and only after a clear yes call it again with
`confirm_name` (the exact name) and `confirm_delete: true`. App tools report each app's `target` and cloud URL;
the data tools work on cloud databases exactly like on the PC's (RDS / Aurora are SQL sources).
DynamoDB tables use the document tools (`collection` = table, page with `cursor`) and `run_query` takes
one JSON request (`{"operation": "Query", "TableName": ..., ...}`; docs/QUERY_CONSOLE.md). Firestore
databases use them too (`collection` = a path such as `users` or `users/u1/orders`, `_id` = the document
id, page with `cursor`; `list_subcollections` finds a document's collections, `export_documents` dumps
them as JSON) and `run_query` takes `{"from": "orders", "where": [{"field": "status", "op": "==",
"value": "open"}], "limit": 20}`. A Realtime Database is a JSON tree, not collections: `rtdb_read` (`path`,
`shallow: true` to list keys, Firebase's `orderBy` / `startAt` / `endAt` / `equalTo` / `limitToFirst`) and
`rtdb_write` (`set`, `update`, `push`, `delete` at a `path`), or `run_query` with `{"path": "users",
"orderBy": "age", "startAt": 18, "limitToFirst": 20}`; ordering by a child needs an `.indexOn` rule. Ask the user for an `anon` key
unless they want the agent to change data or deploy; a `service` key can change production data.
Limits: 200 rows / 256 KB per result, 60 tool calls a minute. Details: `docs/MCP.md`.

## Feature status (check before promising anything)

Deployer changes quickly. Before telling the user a feature exists, confirm it on their instance
(`GET <url>/v1/health` gives the release version, e.g. `1.2.0`; `0.1.0` means a build from source,
so check the dashboard tab or endpoint named below).

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
| **AWS databases** (RDS / Aurora MySQL, MariaDB, PostgreSQL): create a small one or connect an existing one; App Runner apps with database access get `DEPLOYER_DB_<NAME>_*` pointing at it; stays up with the PC off | Available when `GET /v1/projects/{id}/cloud/databases/options` exists; not yet exercised against a live AWS account | Databases → *Add database* → *In your AWS account* (admin); `docs/CLOUD.md` "C2-1" |
| **DynamoDB** (NoSQL in AWS): create an on-demand table or connect existing ones, browse / edit items, JSON queries, on-demand backups; App Runner apps get the table names and an IAM role for them | Available when `GET /v1/projects/{id}/cloud/databases/options` returns `dynamodb`; not yet exercised against a live AWS account | Databases → *Add database* → NoSQL → *In your AWS account* (admin); `docs/CLOUD.md` "C2-2" |
| **Cloud Firestore** (NoSQL in Firebase): connect the project's Firestore database, browse / edit documents and subcollections, JSON queries, schema, JSON export; Firebase full apps with database access get `DEPLOYER_DB_<NAME>_PROJECT` / `_DATABASE` (their service account needs the Cloud Datastore User role) | Available when `GET /v1/projects/{id}/cloud/databases/options` returns `firestore`; not yet exercised against a live Google account | Databases → *Add database* → NoSQL → *In your Firebase project* (admin); `docs/CLOUD.md` "C2-3" |
| **Firebase Realtime Database** (NoSQL JSON tree in Firebase): connect the project's Realtime Database or create its default one (billable once used), browse the tree branch by branch, edit / add / delete by path, Firebase's path queries, JSON export; Firebase full apps with database access get `DEPLOYER_DB_<NAME>_URL` / `_PROJECT` (their service account needs the Firebase Realtime Database Admin role) | Available when `GET /v1/projects/{id}/cloud/databases/options` returns `rtdb`; not yet exercised against a live Google account | Databases → *Add database* → NoSQL → *In your Firebase project* → *Realtime Database* (admin); `docs/CLOUD.md` "C2-4" |
| Cloud databases in MCP, export / import and project delete: the data tools work on RDS, DynamoDB, Firestore and the Realtime Database; creating / connecting one needs a project admin (not a service key); exports carry their settings (encrypted) but not their data; deleting a project asks whether to delete or keep what Deployer created in the cloud account | Available when MCP `tools/list` with a service key no longer offers `create_cloud_database` (older instances offered it to service keys); never test it by deleting a project | Project → Settings → *Delete project*; `docs/CLOUD.md` "C2-5" |
| **GitHub Actions builds** for cloud apps: a workflow in the app's GitHub repository builds every push and deploys it straight to AWS / Firebase with an OIDC sign-in (no stored keys), so pushes deploy with the PC off; runs report back as deployments; rollbacks still need the PC | Available when `get_app` returns `build` (and MCP offers `set_build_location` to admins); not yet run on GitHub's runners against live accounts | app → Settings → *Where it builds* (admin); `docs/CLOUD.md` "C3" |
| Apps placed on a host device instead of the main PC | **Not built** - an app always runs on the main Deployer PC; with *Co-host this app* (phase 2 above) it **also** runs on the project's co-host PCs | - |

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
   A project **admin** attaches the project API key with `api_key_id` so the container gets `DEPLOYER_API_KEY`,
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

Limits to tell the user: one PC (plus the co-host PCs below, when co-hosted), 512 MB RAM per app by default, no persistent volumes (use the
project's databases), builds run through Docker on that PC and take a few minutes the first time.

### Cloud targets (AWS / Firebase through Deployer)

The same app, served from the user's own cloud account so it **keeps running when the PC is off**
(check Feature status first):

1. **Account**: the instance **owner** connects it under *Settings → Cloud accounts* (guided: an IAM
   user with the policy shown there, or a Firebase service account with the listed roles; Deployer
   validates it). Never ask for AWS keys or a service-account file in chat - the user pastes them there.
2. **Target**: a project **admin** picks it under the app's *Where should this run?* (New app or app
   Settings, with a tick confirming the cloud account pays), MCP `set_app_target`, or `target` +
   `cloud_connection_id` + `confirm_billing: true` on `POST/PATCH .../apps` (without it: `422
   billing_not_confirmed`):
   - static sites (preset `static`): `aws_static` (S3 + CloudFront) or `firebase_hosting`;
   - servers (Node / Python / Dockerfile): `aws_app` (App Runner) or `firebase_app` (Cloud Run behind
     Firebase Hosting; needs the Blaze plan).
   Each costs money on the user's account (the chooser explains the cost drivers) - confirm with the user.
3. **Environment**: cloud apps get **only their own variables** - no `DEPLOYER_URL`,
   `DEPLOYER_API_KEY` or this PC's databases, because the PC may be off. A cloud app that needs data
   uses a database in the cloud: on **App Runner** (`aws_app`) add one under *Add database → In your
   AWS account* and tick *Connect to this project's AWS databases* in the app (admin; `database_access:
   true`) - it then gets `DEPLOYER_DB_<NAME>_*` pointing at AWS and reaches the database through a
   private VPC connector. Its `_URL` encrypts without checking the server; to verify it, download the
   CA bundle at `DEPLOYER_DB_<NAME>_SSL_CA_URL` in the Dockerfile and pass it to the driver
   (`sslmode=verify-full&sslrootcert=<file>` / MySQL `ssl.ca`; `docs/CLOUD.md` "C2-1" "Apps"). Tell the user: such an app's other outgoing internet calls need a NAT gateway
   in their VPC (about US$32/month). A DynamoDB database needs none of that: the app gets
   `DEPLOYER_DB_<NAME>_TABLE` / `_TABLES` / `_REGION` and runs as an AWS role allowed only those tables, so
   the AWS SDK works without keys. On **Cloud Run** (`firebase_app`) connect the Firebase project's
   Firestore database or Realtime Database under *Add database → In your Firebase project* and tick
   *Connect to this project's Firebase databases* (admin): the app gets `DEPLOYER_DB_<NAME>_PROJECT` /
   `_DATABASE` (Realtime Database: also `_URL`, the Admin SDK's `databaseURL`) and signs in as its own
   service account - tell the user to give that account (`<project number>-compute@developer.
   gserviceaccount.com`, named in the build log) the **Cloud Datastore User** role (Firestore) or the
   **Firebase Realtime Database Admin** role (Realtime Database) in Google Cloud → IAM, unless it already
   has Editor.
4. **Deploy** as above (*Deploy now*, `deploy_app`, push webhook). The build log shows the cloud steps
   (upload, rollout status); `deployment_status` returns `target_url`. First CloudFront rollouts take
   ~15 minutes to answer.
5. **Where it builds** (optional, after that first deploy): by default this PC builds every push, so pushes
   wait while it is off. To deploy pushes with the PC off, a project admin picks **GitHub Actions** under the
   app's Settings → *Where it builds* (or MCP `set_build_location` with `location: "github"`, or
   `PUT .../apps/{app_id}/build`). Explain it in plain words first and get a yes: Deployer adds a workflow
   file to their GitHub repository (a commit on the app's branch) and a sign-in for it in their cloud account
   (an IAM role, or a Google workload identity provider, that only that repository's branch can use - no keys
   are stored in GitHub; on Firebase the workflow signs in as Deployer's service account, so anyone who can
   push to that branch gets Deployer's access to the Firebase project - say so); GitHub then builds every push and deploys it to the cloud; GitHub may bill build
   minutes (free for public repositories, 2,000 minutes a month free for private ones), so send
   `confirm_billing: true` only after they agree. It needs the admin's GitHub connection with the workflow
   permission (`github_scope_missing`: they reconnect GitHub in the dashboard). Then `deploy_app` runs the
   workflow (answer `{github_actions: true}`), `list_github_runs` shows the runs (also those while the PC
   was off), runs report back as deployments when the PC is on, rollbacks still run on the PC, and changed
   environment variables reach the app with the next rollback (GitHub never sees them). `location: "pc"`
   removes the workflow and the sign-in again.
6. **Domain**: `POST .../apps/{app_id}/domains {hostname}` (admin, after the first deploy): with
   Cloudflare linked the DNS records are created automatically; otherwise the app's Domains card lists
   the records for the user to add, then *Check again*.
7. **Moving or deleting** the app removes what Deployer created in the cloud account (the dashboard
   lists it first; failures are reported by the teardown job). **Deleting the whole project** asks the
   user to choose: delete what Deployer created in the cloud (databases keep a final snapshot) or keep it
   running and billed in their account (`cloud=delete` / `cloud=keep`). Never pick for them.

### Co-host PCs (the same app on other PCs, with failover)

Check Feature status (co-hosting phase 2) first. Deploy on this Deployer instance as above, then a
project **admin** ticks *Co-host this app* (App → Settings; `cohost: true` on `PATCH .../apps/{app_id}`).
Every co-host PC of the project (a member with the Co-host flag whose PC is shared with the project and,
for apps with database access, holds live copies of its databases) builds and runs the same commit, and
the app's hostnames fail over between PCs. Only one app per Deployer can be co-hosted for now
(409 `cohost_limit`: turn it off on the other app first). A private repository also needs *Let co-hosts
clone this private repository* (`cohost_share_repo_access`; the token becomes readable on those PCs).
Details: `docs/COHOSTING.md`.

## Step 2b - Frontend / serverless on an external platform

Only after the user answered the platform question:

| Platform | What to do | Deployer bits to set |
|---|---|---|
| Vercel | `vercel` / `vercel --prod`, or connect the Git repo | env vars `DEPLOYER_URL`, `DEPLOYER_API_KEY` |
| Netlify | `netlify deploy --prod`, or Git integration | same, in *Site settings → Environment* |
| Cloudflare Pages | `wrangler pages deploy <dir>` or Git integration | same; the Deployer tunnel can share the zone |
| GitHub Pages | workflow that builds and publishes `dist/` | no server side: no key at all unless every table in the project is public (an `anon` key reads all data); otherwise pick a platform with functions |

After deploying: open the site, run one real request against the data API from it, and check the
project's query log / audit (Deployer dashboard) shows the call. Then tell the user the URL, the
platform used, and where the key lives.

## People, sign-in and co-hosting

- **Adding people:** project → **Members → Invite** (single-use link, optionally locked to an
  email, with a role: viewer = read-only, developer = edit data/schema and deploy, admin =
  members/keys/settings). The link is built from the public URL, so while that is
  `http://localhost:8080` it only opens on the Deployer PC (the dialog warns): set up remote access
  first to invite someone on another device. Public signup should stay **off** on an internet-facing instance.
  By default only the instance owner can create projects (a member gets 403 and must ask the owner;
  instances that had other users before this setting existed keep creation open);
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
