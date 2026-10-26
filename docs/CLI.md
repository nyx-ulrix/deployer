# The `deployer` command line (no browser, no sudo)

Everyday work on a Deployer server from a terminal: projects, apps, hostnames, environment variables
and deploys. It is meant for servers without a screen and for AI agents running there. Sign in once by
approving a code from any device's browser; the command line then keeps a personal token, so neither
you nor an agent signs in again.

Server management (`status`, `update`, `logs`, `oauth`, ...) stays in the same `deployer` command and
still runs with sudo; see [SETUP.md](SETUP.md#8-the-deployer-command). The commands below run as your
own user.

## Sign in

```bash
deployer login
```

It prints a link and a code:

```
To sign in, open this link on your phone or computer:

    https://deployer.example.com/cli/approve?code=K7QM-X4RP

and check that it shows this code:  K7QM-X4RP
Waiting for approval (Ctrl+C to cancel; the code expires in 10 minutes)...
```

Open the link on any device, sign in to the dashboard if asked, tick *The code matches the one in my
terminal* and choose **Approve**. The terminal finishes by itself and saves the token to
`~/.config/deployer/cli.json` (mode 600; `DEPLOYER_CONFIG` overrides the path).

- The link uses Deployer's public URL, so it opens from anywhere once remote access is set up
  ([REMOTE_ACCESS.md](REMOTE_ACCESS.md)). Without one it points at `localhost`: tunnel with
  `ssh -L 8080:localhost:8080 you@server` first, or use `--local`.
- `sudo deployer login --local [email]` skips the browser: root on the server creates the token
  directly (whoever is root there could reset the password anyway). The token is saved for the user who
  ran sudo.
- From a laptop: `python3 installer/deployer_cli.py login --url https://deployer.example.com` (Python
  3.9+, nothing to install). Every command takes `--url` and `--json`.
- `deployer whoami` shows the account, `deployer tokens` lists your tokens, `deployer logout` revokes
  this one and deletes the file. Revoke any of them in the dashboard under **Account settings →
  Command-line sign-ins**.

## Commands

| Command | What it does |
|---|---|
| `deployer projects` | Projects you belong to; `projects create <name> [--sql] [--nosql]` adds one |
| `deployer apps [project]` | Apps with their type, status and addresses |
| `deployer app show <app>` | One app: repository, type, addresses, variable names, push-to-deploy |
| `deployer app create <project> --repo <url>` | A new app; settings are detected from the repository (`--name`, `--branch`, `--root-dir`, `--port`, `--preset` override them). With GitHub connected (Account settings) pushes deploy it |
| `deployer app logs <app> [--tail N]` | The app's recent runtime logs |
| `deployer domain add <app> <host> [--overwrite]` | Serve the app at `https://<host>` through the Cloudflare tunnel; `--overwrite` replaces an existing DNS record (it lists it first). `domain remove <app> <host>` |
| `deployer env list <app> [--show]` | Variable names (`--show` prints the values too, audited as a reveal) |
| `deployer env set <app> NAME` | Asks for the value with hidden input; also reads it from a pipe |
| `deployer env set <app> NAME --generate [--bytes 32]` | A random value like `openssl rand -hex 32`, never printed |
| `deployer env unset <app> NAME...` | Removes variables |
| `deployer google-oauth <app>... [--path /auth/callback]` | Google sign-in for apps: prints what to enter in Google's console, then saves `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` on each app (below) |
| `deployer deploy <app> [--wait]` | Deploys now; `--wait` streams the build log until it is live or failed |

`<app>` is the app's name, slug or id, or `project/app` when two projects have one with that name.
Variables apply at the app's next deploy (`deployer deploy <app>`); apps on App Runner or Cloud Run are
republished with them at once.

Avoid putting secret values on the command line (`env set <app> NAME value` works, but the value lands
in your shell history); leave the value out and type it at the hidden prompt.

### Google sign-in for your apps

Google offers no API for creating OAuth web clients, so this one step happens in Google's console, from
any device. `deployer google-oauth kanban printer-editor` prints the redirect URIs from the apps'
hostnames (`https://<hostname>/auth/callback`; change the path with `--path` or list URIs with
`--redirect`), then asks for the Client ID and, hidden, the secret, and stores both on every app named.
One client can serve several apps as long as each app's redirect URI is listed on it.

## How it works

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| POST | `/v1/auth/cli/logins` | – (20 per IP per hour) | `{name?, hostname?, os?}` | `{login_id, poll_secret, user_code, verification_uri, verification_uri_base, expires_in: 600, interval: 3}` |
| POST | `/v1/auth/cli/logins/{login_id}/poll` | `poll_secret` | `{poll_secret}` | `{status: "pending"\|"denied"\|"expired"\|"consumed", interval}` or, once, `{status: "approved", token, email}`; 429 `slow_down` faster than every 2 s |
| GET | `/v1/auth/cli/logins?code=` | session | – | `CliLogin` `{id, user_code, name, hostname, os, status, expires_at, created_at}` |
| POST | `/v1/auth/cli/logins/{login_id}/approve` | session | `{user_code, name?}` | `{login, token: CliToken}`; 404 unless the code matches; 409 `login_not_pending` |
| POST | `/v1/auth/cli/logins/{login_id}/deny` | session | `{user_code}` | `CliLogin` |
| GET | `/v1/auth/cli/tokens` | bearer | – | `CliToken[]` `{id, name, prefix, created_at, last_used_at, current}` (never the token) |
| DELETE | `/v1/auth/cli/tokens/{token_id}` | bearer | – | `{ok}` (your own tokens only) |
| DELETE | `/v1/auth/cli/tokens/current` | the token itself | – | `{ok}` (`deployer logout`) |

- A token is `dpt_` + 43 random characters. Only its SHA-256 is stored (`cli_tokens`); between approval
  and the poll that collects it, the raw token waits encrypted with `MASTER_KEY` in `cli_logins` and is
  deleted on delivery. Login requests are pruned a day after they expire.
- `Authorization: Bearer dpt_...` acts as the token's user on every endpoint a signed-in session can
  call, with that user's roles, until it is revoked or the account is disabled. `last_used_at` is
  written at most once a minute.
- **Session only:** approving, denying or looking up a login code, changing the password and linking or
  unlinking Google/GitHub refuse a token (403), so a leaked token can't mint more tokens or lock the
  owner out. Project API keys (`dpl_`) remain limited to the data, query, schema and MCP endpoints.
- `PATCH /v1/projects/{pid}/apps/{id}` accepts `env_set: {k: v}` and `env_unset: [k]` (not together with
  `env`), so changing one variable never sends or reveals the others ([DEPLOYMENTS.md](DEPLOYMENTS.md)).
- Audit actions: `cli.login_create`, `cli.login_approve`, `cli.login_deny`, `cli.token_create` (`--local`)
  and `cli.token_revoke`.
- Phishing: someone could start `deployer login` themselves and send you their link. The approval page
  shows the requesting computer and asks you to confirm the code matches your own terminal; approve only
  codes you started.

The client is `installer/deployer_cli.py` (standard library only); `deployer.sh` hands it `login`,
`logout`, `whoami`, `tokens`, `projects`, `apps`, `app`, `deploy`, `domain`, `env` and `google-oauth`
before its sudo re-run. The Windows `deployer.ps1` does not have these commands yet; run the Python file
directly there.
