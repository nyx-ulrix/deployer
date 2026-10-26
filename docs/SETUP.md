# Setting up Deployer

From nothing to a dashboard you and your collaborators open from any device, on a Windows PC or a
Linux server (headless is fine). Every step uses your own accounts: Deployer ships with no keys, OAuth
apps or accounts from its authors.

1. [Pick the computer](#1-pick-the-computer)
2. [Install it](#2-install-it): [Windows](#on-windows) or [Linux](#on-linux-headless-servers-too)
3. [Create the owner account](#3-create-the-owner-account)
4. [Open it from any device with your own domain](#4-open-it-from-any-device-with-your-own-domain) (Cloudflare)
5. [Invite people and turn on sign-in apps](#5-invite-people-and-turn-on-sign-in-apps)
6. [Deploy an app, connect an AI agent](#6-deploy-an-app-connect-an-ai-agent)
7. [Keep it safe and up to date](#7-keep-it-safe-and-up-to-date)
8. [The `deployer` command](#8-the-deployer-command)
9. [Troubleshooting](#9-troubleshooting)

## 1. Pick the computer

Deployer runs as a set of Docker containers on one computer that stays on. Everyone else only needs a
browser.

| | Windows PC | Linux server |
|---|---|---|
| System | Windows 10 2004+ or 11, 64-bit, virtualization on in the BIOS | Any x86_64 distribution with systemd. Debian and Ubuntu get Docker installed for you; others need Docker Engine + Compose 2.20 or newer |
| CPU | Intel/AMD 64-bit (no ARM) | Intel/AMD 64-bit (no ARM, e.g. no Raspberry Pi) |
| Memory | 4 GB minimum, 8 GB recommended (WSL 2 gets about half) | 4 GB minimum, 8 GB recommended (all of it is available) |
| Disk | 10 GB free | 10 GB free under `/var/lib` (Docker keeps images and databases there) |
| MongoDB | Managed MongoDB 8.0 needs AVX; without it, use an external MongoDB such as Atlas | same, and a kernel MongoDB 8 starts on: not 6.19 to 7.0.13 ([SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912), e.g. Ubuntu 26.04's 7.0 kernel). The installer checks and turns managed MongoDB off otherwise |
| Runs | while the installing account is signed in | from boot, as a systemd service |
| Managed with | Deployer Control (tray app) or `deployer` in PowerShell | `sudo deployer ...` over SSH |

An old laptop with Ubuntu Server makes a good Linux host; `sudo deployer keepawake on` stops it from
suspending when the lid is closed.

## 2. Install it

### On Windows

Download **`DeployerSetup.exe`** from the
[latest release](https://github.com/nyx-ulrix/deployer/releases/latest) and double-click it. It checks
the PC, installs the free Docker Engine in WSL 2, generates every secret on the PC, starts Deployer and
opens `http://localhost:8080/setup`. PowerShell alternative and every option:
[README "Install"](../README.md#install).

### On Linux (headless servers too)

Over SSH, on the server:

```bash
curl -fsSL https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.sh | sudo bash
```

It installs the latest release into `/opt/deployer` and, step by step, tells you what it is doing:

1. checks the server (x86_64, memory, free disk, AVX for MongoDB, ports 8080 and 8100-8199 free);
2. installs Docker Engine from `download.docker.com` if it is missing (Debian/Ubuntu; it asks first);
3. copies the deploy files, writes `/opt/deployer/.env` with freshly generated secrets (root-only);
4. pulls the images (or builds them on the server when they are not published);
5. starts the stack, waits until `/v1/health` answers;
6. registers `deployer.service`, which starts Deployer at boot and stops it cleanly at shutdown;
7. prints the next steps, including the exact SSH command for step 3 below.

Options go after `bash -s --`:

```bash
curl -fsSL https://raw.githubusercontent.com/nyx-ulrix/deployer/main/installer/install.sh | sudo bash -s -- --port 8090 --yes
```

| Option | Meaning |
|---|---|
| `--port 8090` | Dashboard port (default 8080; not 8100-8199, the deployed apps use those) |
| `--lan` | Let other devices connect directly (binds every interface; see the warning in step 4) |
| `--no-autostart` | No systemd service |
| `--prevent-sleep` | Never suspend (same as `sudo deployer keepawake on`) |
| `--from-source` | Build the images on the server instead of downloading them |
| `--yes` | No questions (Docker gets installed, other devices stay blocked) |
| `--ref v0.1.0` / `--repo owner/name` | A specific release or branch / a fork |
| `--source-dir DIR` / `--install-dir DIR` | Install from a local checkout / somewhere other than `/opt/deployer` |

Running it again upgrades the install and keeps `.env` and the data. From a checkout of this
repository: `sudo bash installer/install.sh`.

Where things live: `/opt/deployer` (`docker-compose.yml`, `.env`, `installer/`, `src/`, `backups/`,
`logs/`), the databases in Docker volumes under `/var/lib/docker`, the service in
`/etc/systemd/system/deployer.service`, the command at `/usr/local/bin/deployer`.

## 3. Create the owner account

Whoever opens the setup wizard first becomes the owner, so do this right after installing.

- **Windows:** the installer opens `http://localhost:8080/setup` for you.
- **Linux:** Deployer answers on the server only (`127.0.0.1`). From your own computer, tunnel to it:

  ```bash
  ssh -L 8080:localhost:8080 you@your-server
  ```

  keep that window open and browse to `http://localhost:8080/setup` on your computer. Apps you deploy
  later answer on ports 8100-8199; add `-L 8100:localhost:8100` (and so on) to reach them the same way.

In the wizard: create the owner (email + password), or choose *Restore from export* to bring over a
whole installation. Leave the *Public URL* step as it is; step 4 sets it for you.

## 4. Open it from any device with your own domain

The goal: `https://deployer.example.com` opens the dashboard on any phone, tablet or PC, with nothing
installed on them. The dashboard and API still run on your Deployer computer; Cloudflare only carries
the traffic through a tunnel that the computer opens outwards, so there is no port forwarding on your
router, no open port on the server and no certificate to manage.

You need a free [Cloudflare](https://dash.cloudflare.com/sign-up) account with your domain added to it
(its nameservers pointing at Cloudflare).

1. In the dashboard: **Settings → Domains & remote access → Cloudflare**. The guided setup walks you
   through it.
2. Create an API token at <https://dash.cloudflare.com/profile/api-tokens> → *Create Custom Token*.
   The page has a link that pre-fills most of it. It needs:

   | Scope | Permission |
   |---|---|
   | Account → Cloudflare Tunnel | Edit |
   | Account → Account Settings | Read |
   | Zone → DNS | Edit |
   | Zone → Zone | Read |

3. Paste the token. Deployer checks it and lists any missing permission by name.
4. Add a hostname, e.g. `deployer.example.com`. Deployer creates the tunnel, its route to the dashboard
   and the DNS record, then switches the public URL to `https://deployer.example.com`.
5. Open that address on another device. `sudo deployer status` (Linux) or Deployer Control (Windows)
   shows whether the public address answers.

Details, the quick `trycloudflare.com` tunnel for testing, and app hostnames:
[REMOTE_ACCESS.md](REMOTE_ACCESS.md).

**Only on your own network instead:** Windows: *Deployer Control → Settings → Let other devices on my
network open Deployer*. Linux: `sudo deployer lan on` (prints the addresses to type). On a Linux server
this binds every network interface, and Docker publishes those ports past ufw/firewalld rules, so on a
server with a public IP it is the whole internet over plain HTTP. Prefer the Cloudflare domain, or
`sudo deployer lan on <the server's LAN IP>` to listen on that one address.

## 5. Invite people and turn on sign-in apps

- **Invite:** a project's **Members** tab → *Invite*. Invite links use the
  public URL, so finish step 4 first. Open sign-up stays off unless you turn it on; anyone who signs
  up can create projects and run websites on your computer.
- **Google / GitHub sign-in (optional):** *Settings → Instance settings → Sign in with Google/GitHub → Guided
  setup* shows your callback URLs and deep links into each console. From the command line:
  `deployer oauth status` lists the callback URLs, `deployer oauth set github` saves the Client ID and
  secret. Register the callback URLs for the public URL from step 4. More in the
  [README](../README.md#google-and-github-sign-in-your-own-oauth-apps).

## 6. Deploy an app, connect an AI agent

- **Apps:** a project → **Deploys** → *New app* → *Connect GitHub* → pick a repository. Pushes deploy
  automatically once the public address from step 4 exists ([DEPLOYMENTS.md](DEPLOYMENTS.md)). Apps
  can also run on your own AWS or Firebase account and keep serving when your computer is off
  ([CLOUD.md](CLOUD.md)).
- **AI agents (MCP):** a project → **API keys** → *Create key* → *Show usage* → *AI agents (MCP)*
  gives a ready `claude mcp add ...` command and a JSON config ([MCP.md](MCP.md)). On a headless
  server, run the agent there, or keep the SSH tunnel from step 3 open: the snippets use
  `http://localhost:8080` and work through it unchanged. With a domain from step 4 they use
  `https://deployer.example.com` and work from anywhere.

## 7. Keep it safe and up to date

- **Keep a copy of `.env`** (Windows `C:\ProgramData\Deployer\.env`, Linux `/opt/deployer/.env`)
  somewhere off the computer: its `MASTER_KEY` decrypts every secret Deployer stores.
- **Backups:** every managed database gets automatic encrypted versions and point-in-time recovery
  ([BACKUPS.md](BACKUPS.md)). `deployer backup` adds full dumps plus a copy of `.env` in `backups/`,
  and prints how to copy them off the computer. To move to another computer, use the encrypted
  export: *Settings → Export & import*.
- **Updates:** `deployer update` offers a backup first, then installs the latest release and keeps
  `.env` and the data (Windows: *Deployer Control → Update*).
- **Alerts:** *Settings → Monitoring* can send low-disk, crash-loop and tunnel-down alerts to your own
  webhook ([MONITORING.md](MONITORING.md)).

## 8. The `deployer` command

Windows: in PowerShell (`deployer.cmd`), flags like `-Yes`. Linux: `sudo deployer ...` (it re-runs
itself with sudo), flags like `--yes` (the Windows spelling works too).

| Command | What it does |
|---|---|
| `deployer guide` | (Linux) the first steps above, filled in with this server's port and SSH command |
| `deployer actions` | (Linux) a numbered list of what to do next, checked against the live install: setup not finished, no remote access or it does not answer, no sign-in apps, open sign-up, listening on every interface, no autostart, a laptop lid that suspends, no recent backup, a newer release, low disk |
| `deployer status` | containers, health per service, whether the public address answers |
| `deployer start` / `stop` / `restart [service]` | control the stack |
| `deployer logs [service] [--follow] [--tail N]` | container logs |
| `deployer update [--ref v0.2.0]` | backup, new files and images, restart |
| `deployer backup` / `restore <folder>` | dumps + `.env` copy / load one back (asks first) |
| `deployer open` | the addresses to open (and, on Linux, the SSH tunnel command) |
| `deployer config` | settings, secrets hidden |
| `deployer set-port <port>` | change the dashboard port |
| `deployer lan on [ip]` / `off` | let other devices connect directly / this computer only |
| `deployer autostart on\|off` | start at sign-in (Windows) / at boot (Linux) |
| `deployer keepawake on\|off` | never sleep (laptops: also with the lid closed) |
| `deployer oauth status\|set\|clear` | Google/GitHub sign-in apps |
| `deployer reset-password [email]` | forgot a password (default: the owner) |
| `deployer device status\|detach` | host device link ([DEVICES.md](DEVICES.md)) |
| `deployer compose -- <args>` | any `docker compose` command |
| `deployer uninstall [--keep-data]` | remove Deployer (asks first) |

Most commands end with a **Next:** block naming the command to run next, and errors say how to fix
them.

**Everyday work without sudo or a browser on the server (Linux):** `deployer login` prints a link and a
code; open it on your phone or laptop, approve, and the terminal keeps a token. Then `deployer apps`,
`deployer app create`, `deployer domain add`, `deployer env set` (hidden input, or `--generate` for a
random secret), `deployer google-oauth` and `deployer deploy`. Everything is in [CLI.md](CLI.md).

## 9. Troubleshooting

| Problem | What to do |
|---|---|
| `https://<your domain>` shows Cloudflare **error 1033 / 530** | The tunnel is not connected: Deployer is stopped, or the computer is off or asleep. `deployer status`; start it with `deployer start`; then `deployer logs tunnel`. |
| Linux: *Port 8080 is already used* | Install with `--port 8090`, or later `sudo deployer set-port 8090`. |
| Linux: *Docker Compose ... is too old* / *compose plugin is missing* | Install Docker from Docker's repository (`docker-compose-plugin`), or Ubuntu's `docker-compose-v2`. |
| Linux: *Docker is not installed* on a non-Debian distribution | Install Docker Engine and its compose plugin ([docs.docker.com](https://docs.docker.com/engine/install/)), then run the installer again. |
| Linux: the dashboard does not open from my laptop | Deployer answers on the server only: use the SSH tunnel from step 3, the Cloudflare domain from step 4, or `sudo deployer lan on`. |
| Linux: it does not come back after a reboot | `systemctl status deployer`; `sudo deployer autostart on`. |
| Forgot the owner password | `deployer reset-password` on the Deployer computer. |
| Linux: *Managed MongoDB is turned off: MongoDB 8 cannot start here* | MongoDB 8 refuses Linux kernels 6.19 to 7.0.13 ([SERVER-121912](https://jira.mongodb.org/browse/SERVER-121912)). Everything else works; use an external MongoDB (e.g. Atlas) meanwhile. After a kernel update to 7.0.14 or newer and a reboot, `sudo deployer update` turns managed MongoDB back on (its data stays in the Docker volume). |
| Anything else | `deployer actions` and `deployer status`, then the [README troubleshooting table](../README.md#troubleshooting). |
