# Deployer

**Deployer is an open-source, self-hosted backend and deployment platform - think Supabase + Vercel -
that runs on an ordinary (even old) Windows PC.** Install it with one command, open the setup wizard,
and you get a dashboard where you and your collaborators manage projects with SQL and NoSQL databases.

Every installation is fully independent. Deployer ships with **no** API keys, OAuth apps or accounts
from its authors: every password and key is generated on your computer during installation, and
Google/GitHub sign-in uses OAuth apps that *you* create (optional).

## Features

- **Accounts** - email + password, **Google** and **GitHub** sign-in, and **account linking**
  (link Google/GitHub to an existing account from *Settings -> Account*; never linked automatically).
- **Collaboration** - invite people to projects with roles (`owner`, `admin`, `developer`, `viewer`),
  single-use invite links (optionally locked to an email), audit log.
- **SQL + NoSQL per project** - managed MariaDB and MongoDB databases on this PC, each with its own
  restricted database user, or attach **external** databases (MySQL, PostgreSQL, MariaDB, MongoDB Atlas...).
- **Schema viewer** - ER diagrams (crow's-foot notation) across SQL and NoSQL, convention checks,
  cross-database links, and **DDL export** (`.sql`, `mongosh` script, or a bundle).
- **Data browser** for tables and collections.
- **Full export / import** - one encrypted JSON file with settings, users, projects **and all data**;
  restore a whole installation or selected projects on another device.
- **Runs anywhere Windows does** - Docker Engine in WSL2 by default, sized for 4 GB RAM machines.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/API.md](docs/API.md) for details.

## Requirements

| | |
|---|---|
| Windows | 64-bit Windows 10 version 2004 (build 19041) or newer, or Windows 11 |
| CPU | Hardware virtualization enabled in BIOS/UEFI (Intel VT-x / AMD SVM) |
| Memory | 4 GB RAM minimum, 8 GB recommended |
| Disk | 10 GB free |
| MongoDB | Managed MongoDB 5.0 needs a CPU with **AVX** (most CPUs since ~2011). Without AVX the installer turns managed MongoDB off; projects can still use an external MongoDB such as a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster. |

## Install

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.ps1 | iex
```

The installer asks for administrator rights, checks your PC, sets up a container runtime, generates
secrets, starts Deployer, registers it to start when you sign in, and opens the setup wizard at
`http://localhost:8080/setup`.

With options (all optional):

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.ps1))) `
    -Runtime wsl-engine -Port 8080 -InstallDir "$env:ProgramData\Deployer" -Ref v0.1.0
```

| Option | Meaning |
|---|---|
| `-Runtime auto\|wsl-engine\|docker-desktop\|existing` | How containers run (see below). Default `auto`. |
| `-Port 8080` | Local port for the dashboard and API. |
| `-InstallDir` | Default `%ProgramData%\Deployer`. |
| `-Repo owner/name` | Install from a fork. |
| `-Ref` | Release tag or branch. Default: latest release, else `main`. |
| `-FromSource` | Build images locally instead of downloading them. |
| `-NonInteractive` | No prompts. Add `-EnableLan` / `-PreventSleep` to opt in to those. |

If Windows must restart to finish enabling WSL, the installer resumes automatically after you sign in.
Running it again later upgrades an existing installation and keeps your `.env` and data.

### Container runtime choices

1. **Docker Engine in WSL2 (default, free).** The open-source Docker Engine (`docker-ce`,
   Apache-2.0) is installed from `download.docker.com` inside a dedicated WSL2 distro named
   `deployer` (Ubuntu 24.04, checksum-verified). Nothing else on your PC is changed.
2. **Docker Desktop.** Installed with `winget` if missing. Docker Desktop is free for personal use,
   education, non-commercial open source and small businesses (fewer than 250 employees and less
   than USD 10 million revenue); **larger organisations need a paid Docker subscription**. If you
   need one, sign in to Docker Desktop yourself - Deployer never asks for Docker credentials.
3. **Existing Docker.** Uses whatever `docker info` already reaches.

`auto` uses an already-running Docker if there is one, otherwise option 1.

## First run: the setup wizard

1. Open `http://localhost:8080/setup` (the installer opens it for you).
2. Create the **instance owner** account - or choose *Restore from export* to bring over a whole
   installation from another device.
3. Optionally configure Google and GitHub sign-in (below) and whether people can sign up without an
   invite.
4. Create projects, add SQL/NoSQL data sources and invite collaborators.

## Google and GitHub sign-in (your own OAuth apps)

Deployer has no shared OAuth apps. Create your own - it takes a few minutes and is free. Use your
public URL (default `http://localhost:8080`, shown in the wizard) as `<PUBLIC_URL>`:

| Provider | Callback / redirect URL |
|---|---|
| Google | `<PUBLIC_URL>/v1/auth/oauth/google/callback` |
| GitHub | `<PUBLIC_URL>/v1/auth/oauth/github/callback` |

**Google**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) -> create or select a project.
2. *APIs & Services -> OAuth consent screen*: choose *External*, fill in the app name and your email,
   add scopes `openid`, `email`, `profile`. While in *Testing* mode, add the Google accounts that
   may sign in as test users.
3. *APIs & Services -> Credentials -> Create credentials -> OAuth client ID* -> *Web application*.
4. Add the Google callback URL above under *Authorized redirect URIs*.
5. Paste the client ID and client secret into the setup wizard (or *Instance settings*).

**GitHub**

1. GitHub -> *Settings -> Developer settings -> OAuth Apps -> New OAuth App*.
2. *Homepage URL*: `<PUBLIC_URL>`. *Authorization callback URL*: the GitHub callback URL above.
3. Register, then *Generate a new client secret*.
4. Paste the client ID and secret into the setup wizard.

If your public URL changes (e.g. after moving to another PC or adding a tunnel), update the callback
URLs in both OAuth apps. Client secrets are stored encrypted with your installation's `MASTER_KEY`.

## Reaching Deployer from other devices

- **This PC only** (default): `http://localhost:8080`.
- **Your home/office network (LAN)**: answer *yes* when the installer asks, or re-run it with
  `-EnableLan`. It adds a Windows Firewall rule for **Private** networks only and, for the WSL
  runtime, either enables WSL *mirrored* networking (Windows 11 22H2+, with a backup of your
  `.wslconfig`) or a `netsh` port forward that `deployer start` refreshes. Then open
  `http://<this-PC's-IP>:8080` on another device, and set `PUBLIC_URL`/the public URL in
  *Instance settings* accordingly.
- **From the internet**: on the roadmap - Tailscale Funnel / Cloudflare Tunnel integration from the
  dashboard. Until then you can run one of those tunnels yourself pointing at `http://localhost:8080`.
  Do not port-forward the plain-HTTP port on your router.

## The `deployer` command

Open a new terminal after installing:

| Command | What it does |
|---|---|
| `deployer status` | Runtime, containers, health |
| `deployer start` / `stop` / `restart [service]` | Control the stack |
| `deployer logs [service] [-Follow]` | Container logs (`api`, `dashboard`, `caddy`, `mariadb`, `mongodb`, `redis`) |
| `deployer update [-Ref v0.2.0]` | Offers a backup, downloads new deploy files (keeps `.env`), pulls images, restarts |
| `deployer backup` | `mariadb-dump` + `mongodump` + a copy of `.env` into `backups\<timestamp>` |
| `deployer open` | Open the dashboard |
| `deployer config` | Show settings (secrets hidden) |
| `deployer compose -- <args>` | Any `docker compose` command, e.g. `deployer compose -- ps -a` |
| `deployer uninstall [-KeepData]` | Remove Deployer (asks you to confirm) |

Autostart is a scheduled task named **Deployer** that runs at sign-in of the account that installed
it. WSL distros belong to a single Windows account, so with the WSL runtime Deployer runs while that
account is signed in (locking the screen is fine; signing out stops it).

Files live in `%ProgramData%\Deployer`: `docker-compose.yml`, `Caddyfile`, `.env` (secrets, readable
only by Administrators, SYSTEM and you), `runtime.json`, `backups\`, `logs\` and, for the WSL
runtime, the distro disk in `wsl\`. **Keep a copy of `.env`** - its `MASTER_KEY` decrypts secrets
stored in the database.

## Development

Prerequisites: Docker with Compose v2, Python 3.12, Node.js 22.

```bash
# Full stack from source (http://localhost:8080)
cp deploy/.env.example deploy/.env      # dev placeholders; never use them for a real install
docker compose -f deploy/docker-compose.yml up --build

# Dashboard with hot reload
cd dashboard
npm ci
npm run dev

# API tests
cd api
python -m venv .venv
. .venv/bin/activate                     # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

To try the Windows installer against your checkout, run it from the repository:
`powershell -ExecutionPolicy Bypass -File installer\install.ps1` (it uses the local files and
`-FromSource` builds the images from them). Releases (`v*` tags) publish
`ghcr.io/<owner>/deployer-api` and `-dashboard` and a `deployer-deploy.zip`. On a fork, make the two
GHCR packages **public** after the first release so installers can pull them anonymously (otherwise
the installer falls back to building from source).

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

1. **Foundation** - compose stack, installer, setup wizard, auth (password/Google/GitHub + linking),
   projects, members & invites, data sources (SQL + NoSQL), schema viewer + DDL export, data browser,
   export/import. *(current)*
2. Public data API - project-scoped REST endpoints authenticated by API keys.
3. Remote access - Tailscale Funnel / Cloudflare Tunnel integration from the dashboard.
4. GitHub push-to-deploy - webhooks, Redis build queue, sandboxed build worker.
5. Google Cloud automation - per-install service account.
6. MCP server for AI agents.
7. Backups, monitoring, hardening.

## Security

Please report vulnerabilities privately - see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) (c) 2026 Deployer contributors.
