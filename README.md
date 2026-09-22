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
- **API keys** - give your apps a project-scoped key (`anon` read-only, `service` read/write) and use
  the same rows, documents, query and schema endpoints from curl, JavaScript or Python; download a
  ready-made config JSON per key ([docs/DATA_API.md](docs/DATA_API.md)).
- **AI-agent skill** - [skills/deploy-website/SKILL.md](skills/deploy-website/SKILL.md) teaches agents
  such as Claude Code how to back a site with Deployer; it always asks which platform to deploy to,
  ordered by your past deployments. Install commands are on each project's Overview tab.
- **Query console** - SQL and MongoDB shell (`mongosh`) in the browser, per database, with the
  project's roles (viewers are limited to read-only queries) ([docs/QUERY_CONSOLE.md](docs/QUERY_CONSOLE.md)).
- **Full export / import** - one encrypted JSON file with settings, users, projects **and all data**;
  restore a whole installation or selected projects on another device.
- **Backups and point-in-time recovery** - every managed database gets automatic encrypted versions;
  restore to a version or to any point in time, with safety snapshots before risky actions
  ([docs/BACKUPS.md](docs/BACKUPS.md)).
- **Host devices** - attach spare PCs running Deployer and place managed databases on them; devices
  connect outbound, so no port forwarding ([docs/DEVICES.md](docs/DEVICES.md)).
- **Remote access with your own domain** - link your Cloudflare account and Deployer creates a tunnel
  and DNS records for `https://deployer.example.com` (or a throwaway quick tunnel for testing)
  ([docs/REMOTE_ACCESS.md](docs/REMOTE_ACCESS.md)).
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

1. Download **`DeployerSetup.exe`** from the
   [latest release](https://github.com/nyx-ulrix/deployer/releases/latest).
2. Double-click it and follow the steps. It checks your PC, lets you pick how containers run, installs
   everything, and finishes with an **Open Deployer** button.

> **Windows SmartScreen:** until the exe is code-signed, Windows may show *"Windows protected your
> PC"*. Click **More info → Run anyway**. You can compare the file with `DeployerSetup.exe.sha256`
> from the same release, or use the PowerShell install below, which runs the same installer script.

Setup asks for administrator rights (it turns on WSL, adds a sign-in task and, if you choose, a
firewall rule). Nothing is sent to the Deployer authors. If Windows needs to restart to finish turning
on WSL, setup tells you and continues automatically after you sign in again. Running
`DeployerSetup.exe` again later opens [Deployer Control](#deployer-control); run it with `/setup` to
update an existing installation with that version.

### Install with PowerShell (alternative)

Open **PowerShell** and run:

```powershell
irm https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.ps1 | iex
```

The installer asks for administrator rights, checks your PC, sets up a container runtime, generates
secrets, starts Deployer, registers it to start when you sign in, and opens the setup wizard at
`http://localhost:8080/setup`. Add `-DryRun` to see every step it would take without changing anything.

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
| `-NoAutostart` | Don't start Deployer when you sign in. |
| `-DryRun` | Read-only: check the PC and print every step it would run. Needs no administrator rights. |

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

`auto` (and the setup wizard) picks option 1 by default, even when Docker Desktop is installed: the
free engine has no licensing conditions and, unlike Docker Desktop, keeps working after the PC sleeps
and wakes. Choose `docker-desktop` or `existing` explicitly to use those instead. An existing
installation keeps the runtime it was installed with unless you run setup again and pick another.

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
- **From the internet**: *Settings → Domains & remote access* links your own (free) Cloudflare account
  and gives you `https://<your-domain>` through a Cloudflare Tunnel - no port forwarding, no
  certificates. A quick `trycloudflare.com` tunnel is available for testing. See
  [docs/REMOTE_ACCESS.md](docs/REMOTE_ACCESS.md). Do not port-forward the plain-HTTP port on your router.

## Deployer Control

`DeployerSetup.exe` doubles as **Deployer Control**, the app for managing Deployer without a terminal.
Setup copies it to `%ProgramData%\Deployer\DeployerControl.exe` and adds two Start menu entries:
**Deployer** (opens the dashboard in your browser) and **Deployer Control**.

- **Status** - running / starting / stopped, and the health of each service (web server, API,
  dashboard, background jobs, SQL database, NoSQL database, cache, remote access tunnel - shown as
  *Off* until you enable remote access).
- **Open Deployer**, **Start**, **Stop**, **Restart**.
- **Update** - takes a backup, then installs the latest release (`deployer update`).
- **Back up now** - database dumps plus a copy of `.env` in the `backups` folder (`deployer backup`).
- **View logs** - live logs for all services or one of them.
- **Settings** - port, access from other devices on your network, keep this PC awake while plugged in,
  start at sign-in.
- **Host device** - shows whether this PC is attached to another Deployer as a host device and lets you
  detach it (`deployer device status` / `deployer device detach`).
- **Uninstall** - removes Deployer; your databases, `.env` and backups are kept unless you tick
  *Also delete all databases and backups*. Also available from *Settings → Apps* in Windows.

If you chose *Start Deployer when I sign in*, Deployer Control also sits in the notification area next
to the clock (right-click it for actions) and tells you if Deployer stops unexpectedly.

| Command line | |
|---|---|
| `DeployerSetup.exe` | Setup wizard, or Deployer Control when Deployer is installed |
| `DeployerSetup.exe /setup` | Setup wizard (updates an existing installation) |
| `DeployerSetup.exe /dryrun` | Setup wizard in test mode: runs `install.ps1 -DryRun`, changes nothing |
| `DeployerControl.exe /control` / `/tray` | Deployer Control window / notification-area icon |
| `DeployerControl.exe /uninstall` | Uninstall |

## The `deployer` command

Open a new terminal after installing:

| Command | What it does |
|---|---|
| `deployer status` | Runtime, containers, health |
| `deployer start` / `stop` / `restart [service]` | Control the stack |
| `deployer logs [service] [-Follow]` | Container logs (`api`, `worker`, `dashboard`, `caddy`, `mariadb`, `mongodb`, `redis`, `tunnel`) |
| `deployer update [-Ref v0.2.0]` | Offers a backup, downloads new deploy files (keeps `.env`), pulls images, restarts |
| `deployer backup` | `mariadb-dump` + `mongodump` + a copy of `.env` into `backups\<timestamp>` |
| `deployer open` | Open the dashboard |
| `deployer config` | Show settings (secrets hidden) |
| `deployer compose -- <args>` | Any `docker compose` command, e.g. `deployer compose -- ps -a` |
| `deployer uninstall [-KeepData]` | Remove Deployer (asks you to confirm) |
| `deployer set-port 8090` | Change the local port |
| `deployer lan on\|off` | Allow / block other devices on your private network |
| `deployer autostart on\|off` | Start Deployer (and the tray icon) when you sign in |
| `deployer keepawake on\|off` | Keep this PC awake while plugged in (off restores your previous settings) |
| `deployer status -Json` | Machine-readable status (used by Deployer Control) |
| `deployer device status` | Whether this PC is a host device, its connection and hosted databases |
| `deployer device detach [-Force]` | Forget the main Deployer this PC is attached to (asks you to confirm; `-Force` while it still hosts databases) |

Autostart is a scheduled task named **Deployer** that runs at sign-in of the account that installed
it. WSL distros belong to a single Windows account, so with the WSL runtime Deployer runs while that
account is signed in (locking the screen is fine; signing out stops it).

Files live in `%ProgramData%\Deployer`: `docker-compose.yml`, `Caddyfile`, `mongodb\` and `tunnel\`
(sidecar files), `.env` (secrets, readable only by Administrators, SYSTEM and you), `runtime.json`,
`installer\`, `src\` (image sources when built locally), `backups\`, `logs\` and, for the WSL
runtime, the distro disk in `wsl\`. **Keep a copy of `.env`** - its `MASTER_KEY` decrypts secrets
stored in the database and the encrypted backup versions.

## Troubleshooting

| Problem | What to do |
|---|---|
| *"Windows protected your PC"* when opening `DeployerSetup.exe` | The exe isn't code-signed yet. Click **More info → Run anyway**, or install with PowerShell instead. |
| *Virtualization is turned off* | Restart, open the BIOS/UEFI setup (usually F2, F10, Del or Esc while the PC starts), enable *Intel Virtualization Technology* (VT-x) or *SVM Mode* (AMD), save and run setup again. |
| *Port 8080 is used by another program* | Pick another port in setup, or later in *Deployer Control → Settings* (`deployer set-port 8090`). |
| *Your processor can't run MongoDB (no AVX)* | Everything else works. Use an external MongoDB such as a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster for NoSQL. |
| Setup stopped with an error | Click **Try again** - setup continues where it stopped and never overwrites your `.env`. **Copy details** puts the full log on the clipboard. Logs: `%ProgramData%\Deployer\logs`. |
| *Restart needed* | Restart Windows and sign in again; setup continues on its own (approve the administrator prompt). |
| Images can't be downloaded | Check your internet connection or proxy. On forks, make the GHCR packages public (see Development). |
| Deployer isn't responding | *Deployer Control → Restart*, then *View logs* (`deployer logs api`). `deployer status` shows every container. |
| Docker Desktop was closed, crashed or the PC woke from sleep, and Deployer is down | `deployer start` (or *Deployer Control → Start*) starts Docker Desktop if needed, repairs it when it crashes on its leftover socket files, and brings Deployer back. With *Start Deployer when I sign in* on (`deployer autostart on`) this happens on its own at sign-in. |
| *Docker Desktop cannot start until Windows is restarted* | After sleep/wake Windows sometimes can no longer create Docker Desktop's socket files (*"The file cannot be accessed by the system"*); Docker Desktop then crashes on every start. Restart Windows. To stop it recurring, run setup again and choose **Free Docker Engine** (WSL2): it does not use Docker Desktop at all. |
| Docker Desktop asks you to sign in | Only needed if your organisation requires a paid Docker subscription. Otherwise skip it, or reinstall with the free Docker Engine. |

When asking for help, include the output of `deployer status` and the latest `install-*.log` from
`%ProgramData%\Deployer\logs` - they never contain your passwords, but check before sharing.

## Development

Prerequisites: Docker with Compose v2, Python 3.12, Node.js 22.

```bash
# Full stack from source (http://localhost:8080)
cp deploy/.env.example deploy/.env      # dev placeholders; never use them for a real install
docker compose -f deploy/docker-compose.yml up --build

# Same, with the API reloading on every change under api/app (docker-compose.dev.yml bind-mounts it;
# run `docker compose restart worker` after changing job code)
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.dev.yml up --build

# Dashboard with hot reload (proxies /v1 to http://localhost:8080)
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
`-FromSource` builds the images from them). Add `-DryRun` for a read-only walkthrough.

`DeployerSetup.exe` is a WinForms app (C# 5, .NET Framework 4.8) built with the compiler that ships
with Windows - no SDK needed:

```powershell
powershell -ExecutionPolicy Bypass -File installer\windows\build.ps1   # -> dist\DeployerSetup.exe
dist\DeployerSetup.selftest.exe /selftest dist\selftest               # renders every page to PNG, no admin
```

It embeds `installer\install.ps1`, `deployer.ps1`, `lib\`, `wsl\` and the `deploy\` files, and runs
`install.ps1 -LocalDeployDir <extracted deploy files>`, following its `##deployer:` progress markers.

Releases (`v*` tags) publish `ghcr.io/<owner>/deployer-api`, `-dashboard` and `-tunnel`, a
`deployer-deploy.zip` and `DeployerSetup.exe` (signed only if the repository has the
`WINDOWS_SIGNING_PFX` / `WINDOWS_SIGNING_PASSWORD` secrets). On a fork, make the three
GHCR packages **public** after the first release so installers can pull them anonymously (otherwise
the installer falls back to building from source).

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

1. **Foundation** - compose stack, installer, setup wizard, auth (password/Google/GitHub + linking),
   projects, members & invites, data sources (SQL + NoSQL), schema viewer + DDL export, data browser,
   export/import. *(done)*
2. **Operations** - `DeployerSetup.exe` + Deployer Control, host devices, backups / versions /
   point-in-time recovery, Cloudflare remote access & custom domains. *(current)*
3. Public data API - project-scoped REST endpoints authenticated by API keys. *(done: [docs/DATA_API.md](docs/DATA_API.md))*
4. GitHub push-to-deploy - webhooks, Redis build queue, sandboxed build worker.
5. Google Cloud automation - per-install service account.
6. MCP server for AI agents.
7. Monitoring and hardening.

## Security

Please report vulnerabilities privately - see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) (c) 2026 Deployer contributors.
