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
  cross-database links, and **DDL export** (`.sql`, `mongosh` script, or a bundle; SQL covers tables and indexes, and
  names any views, triggers or routines it skipped).
- **Data browser** for tables and collections.
- **API keys** - give your apps a project-scoped key (`anon` read-only but reads all project data,
  `service` read/write) and use the same rows, documents, query and schema endpoints from curl,
  JavaScript or Python; download a ready-made config JSON per key ([docs/DATA_API.md](docs/DATA_API.md)).
- **AI-agent skill** - [skills/deploy-website/SKILL.md](skills/deploy-website/SKILL.md) teaches agents
  such as Claude Code how to back a site with Deployer; it always asks which platform to deploy to,
  ordered by your past deployments. Install commands are on each project's Overview tab.
- **MCP server for AI agents** - connect Claude Code or any MCP client to a project with an API key:
  it can read the schema, rows and documents, run queries, and (with a `service` key) change data and
  deploy apps. Copy-ready config under API keys → *Show usage* → *AI agents (MCP)* ([docs/MCP.md](docs/MCP.md)).
- **Query console** - SQL and MongoDB shell (`mongosh`) in the browser, per database, with the
  project's roles (viewers are limited to read-only queries) ([docs/QUERY_CONSOLE.md](docs/QUERY_CONSOLE.md)).
- **Full export / import** - one encrypted JSON file with settings, users, projects **and the data
  in your databases**; restore a whole installation or selected projects on another device. Not
  carried: MariaDB views, triggers, routines and events (the import summary lists any left out),
  backup / point-in-time history, deployment history and the audit log.
- **Backups and point-in-time recovery** - every managed database gets automatic encrypted versions;
  restore to a version or to any point in time, with safety snapshots before risky actions
  ([docs/BACKUPS.md](docs/BACKUPS.md)).
- **Host devices** - attach spare PCs running Deployer and place managed databases on them; devices
  connect outbound, so no port forwarding ([docs/DEVICES.md](docs/DEVICES.md)).
- **Remote access with your own domain** - link your Cloudflare account and Deployer creates a tunnel
  and DNS records for `https://deployer.example.com` (or a throwaway quick tunnel for testing)
  ([docs/REMOTE_ACCESS.md](docs/REMOTE_ACCESS.md)).
- **Push-to-deploy** - connect GitHub once, pick a repository and Deployer detects how to build it
  (static site, Node, Python or your own Dockerfile) and adds the webhook; every push builds it on this PC and swaps it in behind Caddy with zero downtime,
  rollbacks, build and runtime logs, and `https://shop.example.com` through the same Cloudflare
  tunnel ([docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md)).
- **Cloud hosting on your own AWS or Firebase account** - pick per app where it runs: this PC, AWS
  (static sites on S3 + CloudFront, full apps on App Runner) or Firebase (Hosting, full apps on Cloud
  Run). Cloud apps keep serving when this PC is off, get custom domains (DNS records created in
  Cloudflare when linked) and are billed by AWS / Google to you; connect an account under
  *Settings → Cloud accounts* ([docs/CLOUD.md](docs/CLOUD.md)).
- **Monitoring and alerts** - CPU, memory, disk, every container and app, API traffic and error
  rate on *Settings → Monitoring*; alerts for low disk, crash-looping containers, failed backups, a
  down tunnel and more, sent to your own webhook (Slack, Discord, ntfy)
  ([docs/MONITORING.md](docs/MONITORING.md)).
- **Runs anywhere Windows does** - Docker Engine in WSL2 by default, sized for 4 GB RAM machines.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/API.md](docs/API.md) for details.

## Documentation

The full index of the specs in `docs/` (ARCHITECTURE and CONTRIBUTING link here instead of keeping their own lists):

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Services, repository layout, platform data model |
| [API.md](docs/API.md) | The HTTP API contract used by the dashboard, webhooks and AI agents |
| [CONVENTIONS.md](docs/CONVENTIONS.md) | Database schema planning conventions |
| [DATA_API.md](docs/DATA_API.md) | The project data API authenticated by API keys |
| [MCP.md](docs/MCP.md) | The MCP server for AI agents |
| [QUERY_CONSOLE.md](docs/QUERY_CONSOLE.md) | The Query Console (Terminal mode) |
| [QUERY_EDITOR.md](docs/QUERY_EDITOR.md) | The Query Notebook, saved queries and the query log |
| [DEVICES.md](docs/DEVICES.md) | Host devices (other PCs that run databases and apps) |
| [COHOSTING.md](docs/COHOSTING.md) | Co-hosting: live two-way database copies and failover websites |
| [BACKUPS.md](docs/BACKUPS.md) | Backups, versions and recovery |
| [REMOTE_ACCESS.md](docs/REMOTE_ACCESS.md) | Cloudflare remote access and custom domains |
| [DEPLOYMENTS.md](docs/DEPLOYMENTS.md) | Push-to-deploy apps |
| [CLOUD.md](docs/CLOUD.md) | Hosting apps and databases on your own AWS / Firebase accounts |
| [MONITORING.md](docs/MONITORING.md) | Metrics and alerts |
| [SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) | Security review findings |
| [AUDIT_REPORT.md](docs/AUDIT_REPORT.md) | Full audit checklist |

## Requirements

| | |
|---|---|
| Windows | 64-bit Windows 10 version 2004 (build 19041) or newer, or Windows 11 |
| CPU | Intel or AMD 64-bit (ARM PCs are not supported yet) with hardware virtualization enabled in BIOS/UEFI (Intel VT-x / AMD SVM) |
| Memory | 4 GB RAM minimum, 8 GB recommended. WSL2 gives Deployer about half the PC's RAM, so a 4 GB PC has about 2 GB: expect 1-2 small apps. |
| Disk | 10 GB free |
| MongoDB | Managed MongoDB 8.0 needs a CPU with **AVX** (most CPUs since ~2011). Without AVX the installer turns managed MongoDB off; projects can still use an external MongoDB such as a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster. |

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
`DeployerSetup.exe` again later opens [Deployer Control](#deployer-control). A newer
`DeployerSetup.exe` first offers *Update Deployer to vX*, which also updates Deployer Control itself;
*Deployer Control -> Settings -> Run setup again* (or `/setup`) repairs an installation. An update or
repair keeps the folder, runtime, port, network access, keep-awake and sign-in choices; change those in
*Deployer Control -> Settings* (the runtime cannot be changed there: see
[Switching runtime](#switching-runtime)). Its Finish page says which version you now run and opens the
dashboard as usual, not the first-run setup.

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
installation keeps the runtime it was installed with; setup and updates never change it (`install.ps1`
with a different `-Runtime` stops and points here).

#### Switching runtime

Your databases live inside the runtime they were created in, so moving to another runtime starts
empty. Carry your data over with an export:

1. In the dashboard, *Settings -> Export & import -> Whole instance -> Export instance*. Keep the file and its
   passphrase somewhere safe - it is the only copy the new runtime can read.
2. Uninstall Deployer (*Uninstall* in Deployer Control, or `deployer uninstall`). Data it
   keeps stays with the old runtime; it does not follow you.
3. Install again, choosing the new runtime.
4. On the first-run page, choose *Restore from export* and give it the file and passphrase.

## First run: the setup wizard

1. Open `http://localhost:8080/setup` (the installer opens it for you).
2. Create the **instance owner** account - or choose *Restore from export* to bring over a whole
   installation from another device.
   On the *Public URL* step, leave the address as it is; *Settings -> Domains & remote access* sets
   it for you later.
3. Optionally configure Google and GitHub sign-in (below) and whether people can sign up without an
   invite. Open sign-up is off by default; keep it off and use invite links unless everyone who can
   reach this address is trusted - anyone who signs up can create projects and run websites on this
   PC (unless *Only I can create projects* is on).
4. Create projects, add SQL/NoSQL data sources and invite collaborators. Invite links use the public
   URL, so while it is `http://localhost:8080` they only open on this PC: set up remote access
   (*Settings -> Domains & remote access*) before inviting someone on another device.
5. By default only you can create projects; invited people work in the projects you share. Change
   that, disable an account, or see every project under *Settings -> Instance*.

## Google and GitHub sign-in (your own OAuth apps)

Deployer has no shared OAuth apps. Create your own - it takes a few minutes and is free. The easiest
way is the **guided setup** in the dashboard (*Instance settings -> Sign in with Google/GitHub ->
Guided setup*, also in the setup wizard): step-by-step cards with deep links into each console, your
exact callback URLs with *Copy* buttons, a GitHub link that opens the new-OAuth-app form pre-filled,
instant checks on what you paste, and a *Test sign-in* link once saved. Google offers no API for
creating OAuth web clients, so the Google part stays a guided manual setup (about 5 minutes).

To do it by hand, use your public URL (default `http://localhost:8080`, shown in the wizard) as
`<PUBLIC_URL>`:

| Provider | Callback / redirect URL |
|---|---|
| Google | `<PUBLIC_URL>/v1/auth/oauth/google/callback` |
| GitHub | `<PUBLIC_URL>/v1/auth/oauth/github/callback` |

With the default public URL these are `http://localhost:8080/v1/auth/oauth/google/callback` and
`http://localhost:8080/v1/auth/oauth/github/callback`. The easiest place to enter the keys is
**Deployer Control -> Settings -> Sign-in apps (Google & GitHub) -> Set up...**: it shows your exact
callback URL with a *Copy* button, links to each console, and has one box for the Client ID and one
for the Client secret. The dashboard's *Instance settings* and `deployer oauth set google|github`
do the same. Paste **one value per box** - Deployer rejects a whole "ID ... SECRET ..." block, labels
or spaces, and a Google Client ID must look like `1234-abc.apps.googleusercontent.com`.
While the public URL is `http://localhost:<port>`, changing the port changes these URLs (a domain or
tunnel address does not): after *Settings -> Port* Deployer Control lists the new ones
(`deployer oauth status` does too) - register them in both OAuth apps or sign-in fails with
`redirect_uri_mismatch`.

**Google**

1. Go to [Google Cloud Console](https://console.cloud.google.com/projectcreate) -> create or select a project.
2. *Google Auth Platform -> Branding*: app name, user support email, developer contact email.
3. *Audience*: choose *External*. In *Testing* only the Google accounts listed as test users can sign
   in; *Publish app* lets any Google account in (no Google review is needed for the basic sign-in
   scopes Deployer uses).
4. *Clients -> Create client* -> *Web application*; add the Google callback URL above under
   *Authorized redirect URIs*. Copy the client secret right away - Google shows it only once.
5. Paste the client ID and client secret into Deployer Control's *Sign-in apps* page (or *Instance settings*).

**GitHub**

1. GitHub -> *Settings -> Developer settings -> OAuth Apps -> New OAuth App*.
2. *Homepage URL*: `<PUBLIC_URL>`. *Authorization callback URL*: the GitHub callback URL above.
3. Register, then *Generate a new client secret*.
4. Paste the client ID and secret into Deployer Control's *Sign-in apps* page (or *Instance settings*).

If your public URL changes (e.g. after moving to another PC or adding a tunnel), update the callback
URLs in both OAuth apps. Client secrets are stored encrypted with your installation's `MASTER_KEY`.

## Reaching Deployer from other devices

- **This PC only** (default): `http://localhost:8080`.
- **Your home/office network (LAN)**: answer *yes* when the installer asks, or re-run it with
  `-EnableLan`. It adds a Windows Firewall rule for **Private** networks only (it warns, naming the
  network, if Windows marks yours Public: switch it under *Settings > Network & internet > Wi-Fi/Ethernet >
  your network > Network profile type > Private network*) and, for the WSL
  runtime, a `netsh` port forward that `deployer start` refreshes. Deployer uses WSL's default
  networking; if `networkingMode=mirrored` is set in your `.wslconfig`, the installer warns you,
  because Docker in WSL cannot publish ports with it. Then open
  `http://<this-PC's-IP>:8080` on another device, and set `PUBLIC_URL`/the public URL in
  *Instance settings* accordingly. The setup Finish page, the Deployer Control home card and
  *Control > Settings* show that address (`deployer status -Json` returns it as `lanUrls`), or a
  Public-network warning with an *Open network settings* button.
- **From the internet**: *Settings → Domains & remote access* links your own (free) Cloudflare account
  and gives you `https://<your-domain>` through a Cloudflare Tunnel - no port forwarding, no
  certificates. A quick `trycloudflare.com` tunnel is available for testing. See
  [docs/REMOTE_ACCESS.md](docs/REMOTE_ACCESS.md). Do not port-forward the plain-HTTP port on your router.

## Deploy an app

1. Project → **Deploys** → *New app* → **Connect GitHub** (once per user; needs the GitHub sign-in
   app from [Google and GitHub sign-in](#google-and-github-sign-in-your-own-oauth-apps)), then pick a
   repository - private ones included. Deployer reads it and fills in the preset (`static`, `node`,
   `python` or `dockerfile`), build commands and the environment variable names from `.env.example`.
2. Check the settings, fill in the environment values, optionally attach one of the project's API
   keys (injected as `DEPLOYER_API_KEY` next to `DEPLOYER_URL` and `DEPLOYER_PROJECT_ID`), and click
   **Create & deploy**. Deployer clones, builds (BuildKit) and starts the app; it is served on
   `http://localhost:<port>` (ports 8100-8199, LAN when enabled) and on any hostname you add under
   the app's **Domains** once Cloudflare is linked.
3. **Push-to-deploy** needs a public address: GitHub cannot deliver webhooks to `localhost` or a
   LAN address. Set one up under *Settings → Domains & remote access* (see
   [Reaching Deployer from other devices](#reaching-deployer-from-other-devices)); Deployer then
   adds the repository's push webhook for you, also for apps created before the public address
   existed. Until then, deploy with **Deploy now** on the app page.

Every push to the configured branch then becomes a deployment; a failed build or start leaves the
previous one running, and older successful deployments can be rolled back to.

Without the GitHub connection (no GitHub sign-in app, or a non-GitHub host), paste the repository
URL instead (+ a fine-grained token with *Contents: read* for private repositories) and, once you
have a public address, add the webhook by hand: copy its URL and secret from the app's **Settings**
into the repository's *Settings → Webhooks* (content type `application/json`, just the push event).
Details: [docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md).

To serve an app from the cloud instead (it keeps running when this PC is off), the instance owner
connects an AWS or Firebase account under *Settings → Cloud accounts*, and a project admin picks the
target under *Where should this run?* in the app's settings ([docs/CLOUD.md](docs/CLOUD.md)).

## Deployer Control

`DeployerSetup.exe` doubles as **Deployer Control**, the app for managing Deployer without a terminal.
Setup copies it to `%ProgramData%\Deployer\DeployerControl.exe` and adds two Start menu entries:
**Deployer** (opens the dashboard in your browser) and **Deployer Control**.

- **Status** - running / starting / stopped, and the health of each service (web server, API,
  dashboard, background jobs, SQL database, NoSQL database, cache, remote access tunnel - shown as
  *Off* until you enable remote access).
- **Open Deployer**, **Start**, **Stop**, **Restart**.
- **Update** - takes a backup, then installs the latest release (`deployer update`); like **Back up now**
  it needs Deployer's database running (so not while stopped), but works while it is *Not responding*. This updates the
  services, not the Deployer Control app: to get a newer Deployer Control, run the newer release's
  `DeployerSetup.exe` and choose *Update Deployer to vX*.
- **Back up now** - database dumps plus a copy of `.env` in the `backups` folder (`deployer backup`).
- **View logs** - live logs for all services or one of them.
- **Copy diagnostics** - puts the status, the last error and recent log lines on the clipboard, ready to
  paste when you ask for help (no need to read the logs yourself).
- **Settings** - port, access from other devices on your network, keep this PC awake while plugged in,
  start at sign-in, and *Run setup again* (repairs shortcuts, the sign-in task and the Apps & Features
  entry; your data is kept). After an **Update** this Deployer Control is older than Deployer, so setup
  asks you to download the matching `DeployerSetup.exe` instead of installing the older version.
- **Host device** - shows whether this PC is attached to another Deployer as a host device and lets you
  detach it (`deployer device status` / `deployer device detach`).
- **Uninstall** - removes Deployer; your databases, `.env` and backups are kept unless you tick
  *Also delete all databases and backups*. Also available from *Settings → Apps* in Windows, even when
  setup stopped partway (ticking the box then also removes the half-created WSL distro and folder).

If you chose *Start Deployer when I sign in*, Deployer Control also sits in the notification area next
to the clock (right-click it for actions) and tells you if Deployer stops unexpectedly.

| Command line | |
|---|---|
| `DeployerSetup.exe` | Setup wizard, or Deployer Control when Deployer is installed (a newer version offers to update it first) |
| `DeployerSetup.exe /setup` | Setup wizard (updates an existing installation) |
| `DeployerSetup.exe /dryrun` | Setup wizard in test mode: runs `install.ps1 -DryRun`, changes nothing |
| `DeployerControl.exe /control` / `/tray` | Deployer Control window / notification-area icon |
| `DeployerControl.exe /uninstall` | Uninstall (always shows its window; for a scripted uninstall run `deployer uninstall -Yes [-KeepData]`) |

## The `deployer` command

Open a new terminal after installing:

| Command | What it does |
|---|---|
| `deployer status` | Runtime, containers, health |
| `deployer start` / `stop` / `restart [service]` | Control the stack |
| `deployer logs [service] [-Follow]` | Container logs (`api`, `worker`, `dashboard`, `caddy`, `mariadb`, `mongodb`, `redis`, `tunnel`) |
| `deployer update [-Ref v0.2.0]` | Offers a backup, downloads new deploy files (keeps `.env`), pulls images, upgrades managed MongoDB data if needed (from a version with MongoDB 5.0, run it twice: [BACKUPS.md](docs/BACKUPS.md#mongodb-versions)), restarts |
| `deployer backup` | `mariadb-dump` + `mongodump` + a copy of `.env` into `backups\<timestamp>` |
| `deployer restore <folder>` | Loads a `deployer backup` folder (or just its `<timestamp>` name) back in, replacing the current databases; asks first and offers a backup of the current data. Only onto the install that made it: refuses other database passwords, and a different `MASTER_KEY` unless `-Force` |
| `deployer open` | Open the dashboard |
| `deployer config` | Show settings (secrets hidden) |
| `deployer compose -- <args>` | Any `docker compose` command, e.g. `deployer compose -- ps -a` |
| `deployer uninstall [-KeepData]` | Remove Deployer (asks you to confirm; restores your sleep settings if keep awake was on) |
| `deployer set-port 8090` | Change the local port (not 8100-8199: those are the deployed apps' ports) |
| `deployer lan on\|off` | Allow / block other devices on your private network |
| `deployer autostart on\|off` | Start Deployer (and the tray icon) when you sign in |
| `deployer keepawake on\|off` | Keep this PC awake while plugged in, even with a laptop lid closed (off restores your previous settings) |
| `deployer status -Json` | Machine-readable status (used by Deployer Control) |
| `deployer device status` | Whether this PC is a host device, its connection and hosted databases |
| `deployer device detach [-Force]` | Forget the main Deployer this PC is attached to (asks you to confirm; `-Force` while it still hosts databases) |
| `deployer oauth status [-Json]` | Google/GitHub sign-in apps: Client IDs, whether a secret is saved, callback URLs |
| `deployer oauth set google\|github` | Save a Client ID and secret (asks for them; the secret is never put on a command line) |
| `deployer oauth clear google\|github` | Remove a sign-in app |
| `deployer reset-password [email]` | Forgot a password? Set a new one for that account (no email = the owner) and sign it out everywhere. Also in *Deployer Control → Settings → Reset a password* |

Autostart is a scheduled task named **Deployer** that runs at sign-in of the account that installed
it. WSL distros belong to a single Windows account, so with the WSL runtime Deployer runs while that
account is signed in (locking the screen is fine; signing out stops it). Docker Desktop is per-account too.
After a restart - including an overnight Windows Update - it stays down until that account signs in
again. For a PC that acts as a server, turn on automatic sign-in for that account or check Deployer
after Windows updates (setup and *Deployer Control* say this too).
While it runs, the task brings Deployer back after sleep or a WSL restart (and, with LAN access on,
points the port forwarding at the WSL address, which changes on every restart). `deployer stop` (or
*Deployer Control → Stop*) keeps it stopped until you start it again or sign in next time.

Files live in `%ProgramData%\Deployer`: `docker-compose.yml`, `Caddyfile`, `mongodb\` and `tunnel\`
(sidecar files), `.env` (secrets, readable only by Administrators, SYSTEM and you), `runtime.json`,
`installer\`, `src\` (image sources when built locally), `backups\`, `logs\` and, for the WSL
runtime, the distro disk in `wsl\` (`backups\`, `logs\` and `wsl\` are private like `.env`; an older
install gets this at the next sign-in after updating, or when you re-run the installer). **Keep a copy of `.env`** - its `MASTER_KEY` decrypts secrets
stored in the database and the encrypted backup versions. To restore the daily platform snapshot
(users, projects, settings), see [docs/BACKUPS.md](docs/BACKUPS.md#restoring-platform-data).

## Troubleshooting

| Problem | What to do |
|---|---|
| *"Windows protected your PC"* when opening `DeployerSetup.exe` | The exe isn't code-signed yet. Click **More info → Run anyway**, or install with PowerShell instead. |
| *Setup is running as another account, not as you* | Your account isn't an administrator, so Windows ran setup as the account whose password you typed, and Deployer would be installed (and only run) for that account. Cancel, make your account an administrator (*Settings → Accounts → Other users*) and run setup again, or sign in as the administrator and install there. |
| *Virtualization is turned off* | Restart, open the BIOS/UEFI setup (usually F2, F10, Del or Esc while the PC starts), enable *Intel Virtualization Technology* (VT-x) or *SVM Mode* (AMD), save and run setup again. |
| *Forgot your password* | On the Deployer PC open *Deployer Control → Settings → Reset a password*, or run `deployer reset-password` (add the email to reset a member instead of the owner). |
| *Port 8080 is used by another program* | Pick another port in setup, or later in *Deployer Control → Settings* (`deployer set-port 8090`). Ports 8100-8199 are kept for deployed apps, so setup also stops if another program listens there and names it. |
| *Your processor can't run MongoDB (no AVX)* | Everything else works. Use an external MongoDB such as a free [MongoDB Atlas](https://www.mongodb.com/atlas) cluster for NoSQL. |
| Setup stopped with an error | Click **Try again** - setup continues where it stopped and never overwrites your `.env`. **Copy details** puts the full log on the clipboard. Logs: `%ProgramData%\Deployer\logs`. |
| *Restart needed* | Restart Windows and sign in again; setup continues on its own (approve the administrator prompt). |
| Images can't be downloaded | Check your internet connection or proxy. On forks, make the GHCR packages public (see Development). |
| A deploy fails with *exit code 137* / *Out of memory* | The build or app ran out of memory. WSL2 gives Deployer about half the PC's RAM; stop other apps or projects, or add RAM (8 GB is recommended). |
| The dashboard says *Deployer is starting...* | Normal for a minute or two after the PC starts; the page reconnects on its own. If it stays, see the next row. |
| Deployer isn't responding | *Deployer Control → Restart*. If it still isn't responding, click *Copy diagnostics* and paste the result when you ask for help (for yourself: *View logs* or `deployer logs api`; `deployer status` shows every container). |
| Deployer Control says *Couldn't check Deployer's services* | The status check itself failed (usually WSL or Docker is broken). Click *Start* or *Restart*; if that fails, *Show details* has the error to share. |
| Docker Desktop was closed, crashed or the PC woke from sleep, and Deployer is down | `deployer start` (or *Deployer Control → Start*) starts Docker Desktop if needed, repairs it when it crashes on its leftover socket files, and brings Deployer back. With *Start Deployer when I sign in* on (`deployer autostart on`) this happens on its own at sign-in. |
| *Docker Desktop cannot start until Windows is restarted* | After sleep/wake Windows sometimes can no longer create Docker Desktop's socket files (*"The file cannot be accessed by the system"*); Docker Desktop then crashes on every start. Restart Windows. To stop it recurring, move to the **Free Docker Engine** (WSL2), which does not use Docker Desktop at all: export everything (dashboard *Settings -> Export & import*), uninstall, install again choosing *Free Docker Engine*, then pick *Restore from export*. |
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
pytest -rs                               # tests/integration is skipped without real servers
```

`tests/integration` (provisioning, backups/PITR, the query console, co-hosting, device hosting,
push-to-deploy) needs real MariaDB 11 / MongoDB 8.0 servers and the tools in the API image; each
file's docstring says how to run it. CI (`.github/workflows/ci.yml`, job "integration") builds the
API image and runs them there, and fails if any is skipped. It also runs the unit suite on MariaDB
(reported only for now: about 40 tests still fail there).
Every push also builds the dashboard and tunnel images.

To try the Windows installer against your checkout, run it from the repository:
`powershell -ExecutionPolicy Bypass -File installer\install.ps1` (it uses the local files and
`-FromSource` builds the images from them). Add `-DryRun` for a read-only walkthrough.

`DeployerSetup.exe` is a WinForms app (C# 5, .NET Framework 4.8) built with the compiler that ships
with Windows - no SDK needed:

```powershell
powershell -ExecutionPolicy Bypass -File installer\windows\build.ps1   # -> dist\DeployerSetup.exe
dist\DeployerSetup.selftest.exe /selftest dist\selftest               # renders every page to PNG, no admin
```

It embeds `installer\install.ps1`, `deployer.ps1` and the git-tracked files in `lib\`, `wsl\` and
`deploy\` (never a local `.env` or `docker-compose.dev.yml`, so build from a git checkout), and runs
`install.ps1 -LocalDeployDir <extracted deploy files>`, following its `##deployer:` progress markers.

Releases (`v*` tags) publish `ghcr.io/<owner>/deployer-api`, `-dashboard` and `-tunnel`, a
`deployer-deploy.zip` and `DeployerSetup.exe` (signed only if the repository has the
`WINDOWS_SIGNING_PFX` / `WINDOWS_SIGNING_PASSWORD` secrets). On a fork, make the three
GHCR packages **public** after the first release so installers can pull them anonymously (otherwise
the installer falls back to building from source).

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

The one roadmap for the project (docs link here rather than keeping their own copy).

1. **Foundation** - compose stack, installer, setup wizard, auth (password/Google/GitHub + linking),
   projects, members & invites, data sources (SQL + NoSQL), schema viewer + DDL export, data browser,
   export/import. *(done)*
2. **Operations** - `DeployerSetup.exe` (setup wizard + Deployer Control), host devices
   ([docs/DEVICES.md](docs/DEVICES.md)), backups / versions / point-in-time recovery
   ([docs/BACKUPS.md](docs/BACKUPS.md)), Cloudflare remote access & custom domains
   ([docs/REMOTE_ACCESS.md](docs/REMOTE_ACCESS.md)). *(done)*
3. **Public data API** - project-scoped REST endpoints authenticated by API keys. *(done: [docs/DATA_API.md](docs/DATA_API.md))*
4. **GitHub push-to-deploy** - apps built from a Git repository by the worker (BuildKit), run as
   containers behind Caddy, GitHub webhooks, rollbacks, app hostnames. *(done: [docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md))*
   Co-hosted apps also run on the project's co-host PCs with failover *(built, not yet exercised with
   two real PCs: [docs/COHOSTING.md](docs/COHOSTING.md))*. Placing an app on a host device instead of
   the main PC: later.
5. **Google/GitHub sign-in setup** - guided setup in the dashboard (Google offers no API to create
   OAuth clients, so it can't be automated). *(done)*
6. **MCP server for AI agents.** *(done: [docs/MCP.md](docs/MCP.md))*
7. **Monitoring and hardening** - host/container/API metrics (24 h in Redis) on *Settings -> Monitoring*,
   alert rules with an https webhook, per-API-key rate limits, a security review of the
   deploy/co-hosting/MCP code. *(done: [docs/MONITORING.md](docs/MONITORING.md),
   [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md))* Not covered: metrics of host devices and
   co-host PCs, email alerts, custom thresholds, a Prometheus endpoint.
8. **Cloud hosting** on the owner's own AWS / Firebase accounts ([docs/CLOUD.md](docs/CLOUD.md)) -
   *(current)*: C1 connections + hosting targets done; C2 cloud databases and C3 GitHub Actions
   builds planned.

## Security

Please report vulnerabilities privately - see [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) (c) 2026 Deployer contributors.
