---
name: deploy-website
description: "Use when the user wants to deploy, publish, host or 'put online' a website or web app, or asks how to use their self-hosted Deployer instance for a site. Walks an agent through Deployer (projects, databases, API keys, remote access) and, before anything is deployed, ALWAYS asks the user which platform to deploy to - with the options ordered by their past deployment activity. Never deploys without that answer."
---

# Deploy a website with Deployer

Deployer is a self-hosted backend platform (MariaDB, MongoDB, Redis, a data API, backups,
host devices, Cloudflare tunnels) that runs on the user's own Windows PC. It is the *backend*
side of a site. Its own push-to-deploy pipeline for the site's frontend/serverless code is
**not built yet** (roadmap phase 4), so today a website is deployed in two halves:

1. the data and API live in Deployer (this skill);
2. the static or serverless part is deployed on a platform **the user chooses** (below).

## Hard rule: always ask which platform

Before you run, write or suggest any deploy command, ask the user which platform to deploy to.
Never assume, never skip the question, and confirm even when your evidence points to a single
platform. Order the options by the user's past activity.

Gather evidence first (read-only, fast):

- config files in the project: `vercel.json` / `.vercel/`, `netlify.toml`, `wrangler.toml`,
  `.github/workflows/*pages*`, `firebase.json`, `render.yaml`, `fly.toml`, `deployer-*.json`;
- git history: `git log --oneline -30` for deploy/publish commits and CI workflow names;
- the user's memory notes and earlier conversation (platforms they used, accounts they have);
- an existing Deployer project / API key for this site (a `deployer-<slug>-<role>.json` config).

Then ask, in this exact shape (adapt the list; keep the first line):

> Which platform should I deploy this site to? Based on what I found, in order:
> 1. **Vercel** - `vercel.json` present and the last 3 deploy commits used it (recommended)
> 2. **Cloudflare Pages** - the domain is already on Cloudflare (Deployer tunnel is linked)
> 3. **Netlify** / **GitHub Pages** / **a Deployer host device** - no past use found
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
   listener to the internet directly.

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

## Step 2 - Frontend / serverless on the chosen platform

Only after the user answered the platform question:

| Platform | What to do | Deployer bits to set |
|---|---|---|
| Vercel | `vercel` / `vercel --prod`, or connect the Git repo | env vars `DEPLOYER_URL`, `DEPLOYER_API_KEY` |
| Netlify | `netlify deploy --prod`, or Git integration | same, in *Site settings → Environment* |
| Cloudflare Pages | `wrangler pages deploy <dir>` or Git integration | same; the Deployer tunnel can share the zone |
| GitHub Pages | workflow that builds and publishes `dist/` | only the `anon` key (static site, public) |
| Deployer host device | **not available yet** (phase 4). Say so; offer the options above. | - |

After deploying: open the site, run one real request against the data API from it, and check the
project's query log / audit (Deployer dashboard) shows the call. Then tell the user the URL, the
platform used, and where the key lives.

## Do / don't

- Do ask the platform question every time, even for a redeploy - the answer may change.
- Do use the `anon` key on the client and the `service` key only on servers/functions.
- Don't create accounts or enter passwords or secrets on the user's behalf; ask them to paste
  keys into the platform's settings themselves when a UI needs it.
- Don't claim Deployer deployed the site; today it hosts the data, the chosen platform hosts the
  site. Update this skill when the Deployer deploy pipeline ships.

## Where things are

- Instance dashboard: `http://localhost:8080` (or the public URL in Settings)
- Docs in the repo: `docs/DATA_API.md`, `docs/REMOTE_ACCESS.md`, `docs/BACKUPS.md`, `docs/API.md`
- Install / update the instance: `DeployerSetup.exe`, or `deployer update` on the PC
