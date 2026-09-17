# Deployer — Architecture

Deployer is an open-source, self-hosted backend + deployment platform (think Supabase + Vercel)
designed to run on an ordinary — even old — Windows PC. Every installation is fully independent:
it ships with **no** API keys, OAuth apps or accounts belonging to the Deployer authors. The person
who installs it creates their own (optional) Google/GitHub OAuth apps through the setup wizard, and
every password/secret is generated locally at install time.

## Guiding rules

1. **Self-contained.** Nothing phones home. No author-owned credentials anywhere in code or images.
2. **Free by default.** The installer prefers the open-source Docker Engine inside a dedicated WSL2
   distro. Docker Desktop is offered as an alternative; if a user needs a paid Docker subscription
   they sign in to Docker themselves.
3. **One control plane.** Dashboard, GitHub webhooks and AI agents (MCP) all call the same HTTP API,
   which enforces the same auth, roles and audit logging. Nobody touches MariaDB/MongoDB/Redis directly.
4. **Portable.** A single encrypted JSON export (settings + users + projects + **data**) restores a
   whole installation, or selected projects, on another device.

## Components

```text
Browser / phone / AI agent
        │ HTTP(S)
        ▼
  caddy  (host port DEPLOYER_HTTP_PORT, default 8080; internal :8081 for the tunnel)
   ├── /v1/*  → api        (FastAPI, Python 3.12)
   └── /*     → dashboard  (React + Vite SPA served by nginx)
                 │
   backend network (internal: true)
   ├── mariadb:11   platform metadata DB `deployer` + managed SQL databases `p_<ref>` (binlog on)
   ├── mongo:5.0    managed NoSQL databases `p_<ref>` (single-node replica set for the oplog)
   ├── redis:7      OAuth state, rate limits, job queue, device RPC routing
   └── worker       jobs + scheduler: backups, log archiving, pruning, verification; on a host
                    device also the outbound connection to the main Deployer

  tunnel (optional, public network only) — cloudflared connector for Cloudflare remote access
```

| Path | Contents |
|---|---|
| `api/` | FastAPI control plane (`app/`), Alembic migrations, tests, Dockerfile |
| `dashboard/` | React + TypeScript + Vite SPA, Dockerfile (nginx) |
| `deploy/` | `docker-compose.yml`, `docker-compose.dev.yml` (API hot reload for checkouts), `Caddyfile`, `.env.example`, `mongodb/` (replica-set entrypoint), `tunnel/` (cloudflared sidecar image) |
| `installer/` | `install.ps1` (Windows bootstrap), `deployer.ps1` (manage CLI), WSL engine scripts, `windows/` (`DeployerSetup.exe`: setup wizard + Deployer Control, C# WinForms on .NET Framework 4.8) |
| `docs/` | This file, `API.md` (HTTP contract), `CONVENTIONS.md` (schema conventions), `DEVICES.md` (host devices), `BACKUPS.md` (backups & recovery), `REMOTE_ACCESS.md` (Cloudflare domains) |

## Data model (platform DB, MariaDB `deployer`)

All primary keys are UUID strings (`CHAR(36)`) so exports can be imported without ID collisions.
Source of truth: `api/app/models.py`.

| Table | Purpose |
|---|---|
| `instance_settings` | key/value settings (public URL, OAuth client IDs, encrypted client secrets, signup policy) |
| `users` | accounts; `password_hash` nullable (OAuth-only users); first user is `is_instance_owner` |
| `user_identities` | linked Google/GitHub identities (`provider`, `provider_user_id`) |
| `refresh_tokens` | hashed rotating refresh tokens, grouped by `family_id` for reuse detection |
| `projects` | a project groups data sources, members, API keys, (later) deployments |
| `project_members` | `owner` / `admin` / `developer` / `viewer` |
| `project_invites` | hashed single-use invite tokens (optional email lock) |
| `data_sources` | SQL and/or NoSQL databases attached to a project — `managed` (on this host) or `external` (e.g. Atlas, remote MySQL/Postgres); connection config encrypted |
| `schema_links` | user-declared relationships, incl. **cross-database** links (SQL column ↔ Mongo field) |
| `api_keys` | hashed per-project keys (`anon` / `service`) |
| `audit_logs` | security-relevant events |

## Security model

- Passwords: argon2id. Access tokens: HS256 JWT, 15 min, sent as `Authorization: Bearer`.
- Refresh tokens: 256-bit random, stored as SHA-256 hash, rotated on every use, HttpOnly cookie
  `deployer_rt` (`Path=/v1/auth`, `SameSite=Lax`, `Secure` when public URL is https). Reusing a
  rotated token revokes the whole family.
- Secrets at rest (OAuth client secrets, external DB passwords): AES-256-GCM with `MASTER_KEY`
  from `.env` (`app/crypto.py`).
- OAuth: authorization-code flow with `state` + PKCE, state kept in Redis for 10 minutes.
- **Account linking is never automatic.** Signing in with a provider whose email matches an existing
  account is refused with `account_exists_link_required`; the user signs in the usual way and links
  from *Settings → Account*. An identity can belong to only one user. A user cannot remove their last
  login method.
- Login rate limit: 10 attempts / 15 min per IP+email (Redis).
- Managed databases get their own DB user restricted to that database only.

## Export / import format

A single `.json` file:

```json
{
  "format": "deployer-export",
  "version": 1,
  "scope": "instance | projects",
  "created_at": "2026-09-16T10:00:00Z",
  "app_version": "0.1.0",
  "encryption": { "cipher": "AES-256-GCM", "kdf": "scrypt", "n": 32768, "r": 8, "p": 1,
                  "salt": "<b64>", "nonce": "<b64>" },
  "payload": "<b64 of AES-GCM(gzip(plaintext JSON))>"
}
```

The payload always contains settings/users/projects/members/pending invites/api-key hashes/data
sources (with connection secrets)/schema links, **plus the full contents of every managed database**:
SQL tables as DDL + rows, Mongo collections as options + indexes + documents (canonical Extended
JSON). External databases are reconnected, not copied. A passphrase (min 12 chars) is required
because the file contains password hashes and secrets.

- `scope: instance` — made by the instance owner; imported by the setup wizard on a fresh install
  ("Restore from export") and restores everything, including all users.
- `scope: projects` — made by any user for projects they own; imported by any user on another
  installation, which recreates those projects (and their data) owned by the importer.

After restoring on a new device the wizard shows the new OAuth callback URLs to paste into the
user's Google/GitHub OAuth apps if the public URL changed.

## Roadmap (phases)

1. Foundation — compose stack, installer, setup wizard, auth (password/Google/GitHub + linking),
   projects, members & invites, data sources (SQL + NoSQL), schema viewer + DDL export, data
   browser, export/import. **Done.**
2. Operations — `DeployerSetup.exe` (setup wizard + Deployer Control), host devices
   ([DEVICES.md](DEVICES.md)), backups/versions/point-in-time recovery ([BACKUPS.md](BACKUPS.md)),
   Cloudflare remote access & custom domains ([REMOTE_ACCESS.md](REMOTE_ACCESS.md)). **← current**
3. Public data API — project-scoped REST endpoints authenticated by API keys.
4. GitHub push-to-deploy — webhooks, Redis build queue, sandboxed build worker (host devices gain an
   app-hosting role).
5. Google Cloud automation — per-install service account.
6. MCP server for AI agents.
7. Monitoring and hardening.
