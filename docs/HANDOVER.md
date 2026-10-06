# Handover

The state of Deployer as of 2026-10-06, for whoever picks it up next (a person or an AI agent). It
says what is built, how the owner's install runs, how to change and ship code safely, and what is
still open. The specs in `docs/` stay the source of truth for each feature; this page points at them.

## What Deployer is

A self-hosted Supabase + Vercel for old Windows PCs: projects with managed MariaDB / MongoDB
databases, a data API with API keys, a SQL / Mongo query notebook, backups with point-in-time
recovery, push-to-deploy websites from GitHub, co-hosting on other PCs, remote access through a
Cloudflare tunnel, an MCP server for AI agents, and (optionally) hosting apps and databases on the
owner's own AWS / Firebase accounts so they stay up when the PC is off.

- Repository: <https://github.com/nyx-ulrix/deployer> (public, default branch `main`).
- The owner's live instance: <https://deployer.liewjiaen.com> (Cloudflare tunnel to the owner's PC).
- Stack: FastAPI + SQLAlchemy + Alembic (`api/`), React 19 + TypeScript + TanStack Query + Tailwind
  (`dashboard/`), PowerShell 5.1 installer and C# WinForms "Deployer Control" (`installer/`), docker
  compose on a Docker Engine inside a WSL distro (`deploy/`).

## Where things stand

| | |
|---|---|
| Code on `main` | `03a6f00`, CI and secret scan green |
| Installed on the owner's PC | `03a6f00` files and images (updated 2026-10-06; backup in `C:\ProgramData\Deployer\backups\20261006-203226`). The sign-in task's loop still runs the previous code until the next sign-in: **sign out and back in (or restart) once** |
| Database schema | Alembic head `0014` |
| Releases | none yet: no tag, so `release.yml` has never run and no images exist on GHCR; every install and update builds the images on the PC (`DEPLOYER_VERSION=latest` in `.env`) |

Work finished in the last stretch, newest first:

1. **Keep-alive hardening** (after a real outage on 2026-10-05/06, below): the sign-in task's loop
   retries a failed start or a failed `wsl.exe` launch (15 s, doubling up to 5 minutes) instead of
   exiting, starts the keep-alive before the containers, and the task repeats every 5 minutes as a
   watchdog. On the owner's PC this becomes active at the next sign-in (see the table above).
2. **Cloud phases C1-C3** ([CLOUD.md](CLOUD.md)): hosting on AWS (S3 + CloudFront, App Runner) and
   Firebase (Hosting, Cloud Run); cloud databases (RDS / Aurora, DynamoDB, Firestore, Realtime
   Database) with backups, point-in-time recovery and restores; GitHub Actions builds with OIDC so
   pushes deploy with the PC off; app secrets in Secrets Manager / Secret Manager (opt-in); an IAM
   permissions boundary on every role Deployer creates; the Deployer AWS policy split into
   `DeployerHosting`, `DeployerDatabases` and `DeployerRoles`; an optional NAT gateway for App Runner
   apps linked to RDS. Every billable action is off by default and needs `confirm_billing`.
3. **Fable 5.1 vetting pass** over everything shipped after the audit. Its confirmed findings were
   fixed in the commits named `Fix V-01`, `Fix V-02` and `Fix V-04` to `Fix V-07` (V-03, MCP cloud
   tools skipping their routes' admin rule, was fixed in `8377c26`), and its smaller notes in
   `Fix L-01` to `Fix L-09` (several bundle more than one fix), each with `Follow-up` / `Audit fix`
   commits. There is no written vetting report in the repo; the commit messages are the record.
4. **Full codebase audit** ([AUDIT_REPORT.md](AUDIT_REPORT.md)): 198 findings, all ticked. The few
   that were only partly fixed, and the follow-ups that closed them, are noted under each item.

Every change in those passes was built in its own git worktree, independently audited by a second
model, and pushed only with the full API suite, the dashboard checks and CI green.

## The owner's PC

| What | Where / what |
|---|---|
| Install folder | `C:\ProgramData\Deployer` (deploy files, `src\`, `installer\`, `.env`, `runtime.json`, `logs\deployer.log`, `backups\`) |
| Installed version and settings | `runtime.json` (`ref`, `updatedAt`, `runtime: wsl-engine`, `autostart`, `lan`, `keepAwake`) |
| Command | `C:\ProgramData\Deployer\deployer.cmd` (on the user PATH as `deployer`); asks for admin rights when it needs them |
| Runtime | WSL 2 distro `deployer` running Docker Engine (Deployer does not use Docker Desktop) |
| Services | `api`, `worker`, `migrate` (one-shot, runs Alembic before the API starts), `query-shell` (mongosh sidecar without platform secrets), `dashboard`, `caddy`, `tunnel` (cloudflared), `mariadb` 11, `mongodb` 8.0, `redis`; plus one-off `mongodb-upgrade-*` services that updates use to lift old MongoDB 5.0 data |
| Ports | dashboard on 8080; deployed apps on 8100-8199. LAN access is on (port proxy, Caddy listening on all interfaces) and keep-awake is on |
| Autostart | scheduled task `Deployer` (at sign-in after a 20 s delay, highest privileges, `conhost --headless powershell ... deployer.ps1 start -Background`, repeats every 5 minutes, new instances ignored while one runs) and `Deployer Tray` (Deployer Control) |
| Remote access | Cloudflare tunnel to `deployer.liewjiaen.com`. The public URL and the Google / GitHub sign-in apps live in the database (set with `deployer oauth set` and the dashboard), not in `.env`, so they come back with a MariaDB restore |
| Secrets | `.env` holds `MASTER_KEY`, which decrypts every stored secret: keep a copy somewhere safe. Backups of encrypted settings are useless without it |

### Everyday commands

| Command | Does |
|---|---|
| `deployer status` | runtime, containers and health (`-Json` for scripts) |
| `deployer start` / `deployer stop` | start or stop the stack. A stop writes the `stop-requested` marker in the install folder, which the watchdog respects until the next sign-in |
| `deployer logs [service] [-Follow]` | container logs |
| `deployer update -Ref <full commit sha or tag>` | offer a backup (default yes; `-Yes` takes it without asking), download that version, build the images, migrate, restart. With no `-Ref` it takes the latest GitHub release, else the tip of `main` |
| `deployer backup` | dump MariaDB and MongoDB and copy `.env` to `backups\<timestamp>` |
| `deployer restore <folder>` | reload MariaDB and MongoDB onto this same install (same `MASTER_KEY`); it does not restore `.env`: copy `env.backup` back by hand if needed |
| `deployer autostart on` | (re)register the sign-in task, including the watchdog |
| `deployer oauth status` / `deployer reset-password` | sign-in apps; a forgotten password |

`deployer` with no arguments lists the rest (LAN access, port, keep-awake, host devices, uninstall).

### Updating the owner's PC

1. Make sure CI and the secret scan are green on the commit you want.
2. Run `deployer update -Ref <full sha>` and approve the admin prompt. Pinning the SHA avoids taking a
   commit that is still in CI (with no release, a bare update takes the tip of `main`).
3. Check: `deployer status`; the dashboard on `http://localhost:8080` and the public URL; the
   `migrate` container exited 0; `Get-ScheduledTask Deployer` still has the 5-minute repetition.
4. `deployer update` runs the installed (old) script. Installs at `a37f5b1` or later (the owner's PC
   now) re-register the sign-in task themselves; after an update from an older install, run
   `deployer autostart on` once. Either way, a changed sign-in loop and the 5-minute repeat only take
   effect at the next sign-in.

Rolling back to a version from before the MongoDB 8.0 upgrade is refused (the data cannot go back);
restore a backup into a fresh volume instead ([BACKUPS.md](BACKUPS.md)).

### The 2026-10-05/06 outage, for reference

Launching `wsl.exe` from the elevated sign-in task failed twice with "Access to %1 has been
restricted by your Administrator by policy rule %2" (Win32 error 786), most likely while WSL's Store
package was being serviced (a Windows update to build 26300 had just landed): at 2026-10-05 22:31 and
2026-10-06 09:11. Each time the old loop treated the failure as fatal and exited, so the site stayed
down until the next sign-in (08:03 and 10:27). Separately, the old code started the keep-alive only
after the health check, so WSL could idle the distro out during startup (13:44 that day). Both are
fixed (item 1 above). If the site is down again: `deployer status`, then `logs\deployer.log` (look
for keep-alive lines), then `deployer start`.

## Working on the code

Read [ARCHITECTURE.md](ARCHITECTURE.md) and [CONTRIBUTING.md](../CONTRIBUTING.md) first; the README
lists every spec.

| Part | Checks that must pass before a push |
|---|---|
| `api/` | `ruff format --check`, `ruff check`, `pytest` (about 950 unit tests on SQLite; the 25 in `tests/integration` skip locally unless their servers are configured) |
| `dashboard/` | `npm run lint`, `npm run typecheck`, `npx vitest run`, `npm run build` |
| `installer/` | PowerShell parse + `Invoke-ScriptAnalyzer -Severity Error` + the 14 self-checking scripts in `installer/tests` (plain PowerShell, not Pester: `powershell -NoProfile -ExecutionPolicy Bypass -File installer\tests\<name>.tests.ps1`); `installer/windows/build.ps1` for the C# app |

CI (`.github/workflows/ci.yml`) runs all of that, builds the images, and in the integration job runs
the unit suite again on real MariaDB 11 plus the integration tests against MariaDB, MongoDB 8.0,
Docker and the query-shell sidecar; a skipped integration test fails the job. `secret-scan.yml` runs
gitleaks on every push: never commit real credentials, and build fake ones in tests at runtime (see
`api/tests/test_cloud.py`). `release.yml` runs only on `v*` tags, gates on CI, pushes the api,
dashboard and tunnel images to GHCR, and creates a GitHub release with `DeployerSetup.exe` and
`deployer-deploy.zip` (pre-release tags never become `latest`, as an image tag or as the latest
release).

Rules that tests enforce, so they are easy to trip over:

- **Migrations:** every `create_table` uses `**TABLE_OPTS` (utf8mb4), and the models must match the
  migrations on both SQLite and MariaDB (`api/tests/test_migration_table_options.py`). By
  convention, not tested: the next number after the head, and every step idempotent because MariaDB
  DDL is not transactional (see the comments in migrations `0010` to `0013`).
- **Docs:** every `docs/*.md` is listed in the README index; every endpoint the docs name must exist
  in the router; unused code fails the dead-code test.
- **Cloud:** no real cloud calls in tests (fakes, and `botocore.stub.Stubber` against the installed
  botocore models); each AWS policy stays at least 600 characters under IAM's 6,144 limit, and a new
  statement goes into the policy for its purpose (comments in `api/app/services/cloud.py`).
- **MCP:** every tool needs at least the role of the REST route it wraps.

The owner prefers commit messages without attribution or co-author lines.

### For AI agents

- The `deploy-website` skill (`skills/deploy-website/SKILL.md`) teaches an agent to use Deployer and
  always to ask which platform to deploy to before deploying. A copy lives in
  `C:\Users\malco\.claude\skills\deploy-website\SKILL.md`; refresh it whenever the repo copy changes.
- The MCP server is described in [MCP.md](MCP.md); destructive and billable tools need explicit
  confirmation arguments, and agents must ask the user first.
- The repo is mapped with graphify (`graphify-out/`, git-ignored); run `graphify update .` after
  code changes.

## What is open

### Needs the owner

- Sign out and back in (or restart) once, so the sign-in task runs the new keep-alive loop and the
  5-minute watchdog starts.
- Publish a release: push a `v0.1.0` tag, then make the GHCR packages it creates public, so installs
  pull images instead of building them.
- Google sign-in for other people: publish the Google OAuth app, or add test users.
- Try the cloud features against real accounts: attach the three AWS policies to a dedicated IAM user
  (Settings -> Cloud accounts shows them), connect a Firebase project, then deploy one small site and
  one small database each way. Everything cloud-side has only been tested against fakes.
- Test HawkerHub's "Connect GitHub" flow and co-hosting with a second PC.
- Optional: a code-signing certificate for the installer (`release.yml` signs when the
  `WINDOWS_SIGNING_PFX` / `WINDOWS_SIGNING_PASSWORD` secrets exist).

### Known limits (documented, not bugs)

- App Runner rejects some availability zones and AWS publishes no list of them; a deploy into such a
  zone fails with App Runner's own error naming the zone.
- The NAT gateway's reference count is not a lock: a deploy that lands while the last user's NAT
  teardown runs fails and needs a retry.
- The plain App Runner VPC connector still includes the VPC's public subnets (predates the NAT work).
- The connection test can reach private LAN addresses on purpose (audit item A-114), because external
  databases are normally reached by their LAN IP; only admins can use it.
- One co-hosting row or document larger than a sync message cannot be synced; the copy shows a
  "Re-copy" error instead.
- Each cloud section of [CLOUD.md](CLOUD.md) ends with "Not verified against real clouds": start
  there when testing with real accounts.

### Next steps

Nothing is half-built on any branch: `main` is the only branch. Reasonable next steps are a first
release, real-account testing of the cloud features, and visual checks of the newer dashboard
screens in a browser (they are covered by vitest but were not viewed during the last passes).
