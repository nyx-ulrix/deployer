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
| `deployer app create <project> --repo <url>` | A new app; settings are detected from the repository (`--name`, `--branch`, `--root-dir`, `--port`, `--preset`, `--install`, `--build`, `--start` override them; `--api-key <name>` attaches a project API key). With GitHub connected (Account settings) pushes deploy it |
| `deployer app logs <app> [--tail N]` | The app's recent runtime logs |
| `deployer domain add <app> <host> [--overwrite]` | Serve the app at `https://<host>` through the Cloudflare tunnel; `--overwrite` replaces an existing DNS record (it lists it first). `domain remove <app> <host>` |
| `deployer env list <app> [--show]` | Variable names (`--show` prints the values too, audited as a reveal) |
| `deployer env set <app> NAME` | Prints a link where you type the value on any device; it goes straight into the app ([Input requests](#input-requests)). `--prompt` asks here with hidden input instead. A value piped or redirected in (`echo … \| deployer env set …`, `< file`) is used as is: a file is read, a pipe gets 5 seconds for its first line (else the link is printed); `--stdin` waits for a slow producer as long as it takes (`op read … \| deployer env set app NAME --stdin`) |
| `deployer env set <app> NAME --generate [--bytes 32]` | A random value like `openssl rand -hex 32`, never printed |
| `deployer env unset <app> NAME...` | Removes variables |
| `deployer google-oauth <app>... [--path /auth/callback]` | Google sign-in for apps: prints what to enter in Google's console, then one link where you paste `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, saved on each app (below); `--prompt` asks here; two piped lines (`printf 'ID\nSECRET\n' \| …`) are used as is |
| `deployer ask "<title>" KEY[:secret]... [--app <app>]...` | Asks you to type anything on any device; prints the values as JSON, or with `--app` stores them in the app's Environment and prints only the names ([Input requests](#input-requests)) |
| `deployer deploy <app> [--wait]` | Deploys now; `--wait` streams the build log until it is live or failed |
| `deployer oauth status\|set\|clear google\|github` | Deployer's own *Continue with Google/GitHub* buttons ([below](#instance-settings-without-sudo)) |
| `deployer alerts status\|set\|clear` | The Slack/Discord (or any https) webhook alerts are posted to |
| `deployer cloud list` / `deployer cloud add aws\|firebase <name> [--project <p>]` | Cloud accounts for cloud databases and hosting ([CLOUD.md](CLOUD.md)) |
| `deployer cloudflare link` | A Cloudflare API token and Account ID for addresses on your own domain ([REMOTE_ACCESS.md](REMOTE_ACCESS.md)) |

`<app>` is the app's name, slug or id, or `project/app` when two projects have one with that name.
Variables apply at the app's next deploy (`deployer deploy <app>`); apps on App Runner or Cloud Run are
republished with them at once.

Avoid putting secret values on the command line (`env set <app> NAME value` works, but the value lands
in your shell history); leave the value out and type it on the page the link opens.

### Google sign-in for your apps

Google offers no API for creating OAuth web clients, so this one step happens in Google's console, from
any device. `deployer google-oauth kanban printer-editor` prints the redirect URIs from the apps'
hostnames (`https://<hostname>/auth/callback`; change the path with `--path` or list URIs with
`--redirect`), then one link to a form with the Client ID (checked against
`^[0-9]+-[a-z0-9]+\.apps\.googleusercontent\.com$`, with an **Open Google console** button) and the
secret. The form repeats the redirect URIs, so the whole step can happen on a phone; both values are
stored on every app named. `--prompt` asks for them in the terminal instead (the secret hidden), and
piped in, the first two lines are the ID and the secret. One client can serve several apps as long as
each app's redirect URI is listed on it.

### Input requests

A command on a server without a screen sometimes needs you to type something: a secret for an app's
Environment, an OAuth client id, a code from a sign-in page. Instead of a terminal prompt it creates an
**input request** and prints a link:

```
Open this link on your phone or computer to fill it in:

    https://deployer.example.com/input/0b9c…

Waiting for it (Ctrl+C to cancel; the link expires in 30 minutes)...
```

Open it on any device, sign in if asked and fill the small form; the terminal continues by itself. The
page says who asked: *Asked by command line '<token name>' (dpt_ab12…)* or *Asked from a dashboard
session*, and always shows the fixed notice *Deployer never asks for your account password or a sign-in
approval code on this page.* Destinations are shown as *<project> / <app>*.
`deployer env set` and `deployer google-oauth` do this by default, and `deployer ask` does it for
anything:

```bash
deployer ask "Stripe keys" STRIPE_KEY:secret STRIPE_ACCOUNT --app shop    # into shop's Environment
code=$(deployer ask "Verification code" CODE --link https://example.com/device | jq -r .CODE)
```

- Each `KEY` is a field (`KEY:secret` hides it, `:optional`, `:multiline`; join them with commas).
  `--description` adds text above the fields, `--link URL` an **Open** button next to the first one.
- Without `--app`, the values are printed as JSON on stdout (the link and messages go to stderr), so a
  script or agent can read them. With `--app` (repeatable) they are saved in those apps' Environment
  exactly like `env set` and never come back to the terminal; it prints only the names.
- Only the account that created a request can open and fill it, and only from a dashboard session: a
  `dpt_` token can create and wait for a request but never fill one. Only the credential that created it
  can wait for (poll) or cancel it: a request made by a `dpt_` token answers only that token (any other
  token or session gets 404); one made from the dashboard answers any session of that user. Revoking a
  token cancels its open requests and drops any values it had not collected yet.
- A request expires after 30 minutes. Values submitted without `--app` that the command line does not
  collect within 10 minutes are dropped and the request reports `expired`.
- Ctrl+C, SIGTERM or SIGHUP (an agent's tool timeout, a closed SSH session), or any error while waiting
  cancels the request. If the form was already submitted with `--app`, the values are in the apps'
  Environment and stay there; the command line says so. While the server is unreachable (a restart, a
  reconnecting tunnel) it prints `Connection to Deployer lost, retrying...` once and keeps waiting until
  the link expires; it gives up at once on 401, 403 or 404.
- If an app the request saves to is deleted, or you lose developer access to it, the form can no longer
  be submitted (409 `input_apps_unavailable`); the command line stops with an error and cancels it.
- With `--app` and every field left empty, nothing is written: *Nothing was entered; nothing was changed.*
- After a submit with `--app` (or `env set`, `google-oauth`) the values apply at each app's next deploy;
  apps on App Runner or Cloud Run are republished with them at once.

### Instance settings without sudo

The instance owner can set up the keys a headless server would otherwise need typed into its terminal
(or the dashboard) through the same [input requests](#input-requests): each command prints what to do in
the provider's console and a link where you paste the result on any device. The values go straight to
Deployer's API and are never printed. `--prompt` asks in the terminal instead.

| Command | What you paste |
| --- | --- |
| `deployer oauth set github` | Client ID and secret of a GitHub OAuth app; the link opens GitHub's form already filled in (name, homepage, callback URL) |
| `deployer oauth set google` | Client ID and secret of a Google *Web application* client; the page lists the redirect URI to add |
| `deployer alerts set` | A Slack incoming-webhook URL, or a Discord webhook URL with `/slack` added |
| `deployer cloud add aws <name>` | Access key ID, secret access key, region (and optionally a role to assume) |
| `deployer cloud add firebase <name>` | The service account's JSON key file, pasted whole |
| `deployer cloudflare link` | An API token (Cloudflare Tunnel Edit, DNS Edit, Zone Read) and the Account ID |

Run without sudo, `deployer oauth` uses your sign-in like the other commands here; `sudo deployer oauth`
still works on the server itself without one. Accounts other than the instance owner get *Only the
instance owner can do that*.

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
| POST | `/v1/auth/cli/inputs` | bearer or session (30 per user per hour) | `{title, description?, fields, app_ids?}` | 201 `{id, url, expires_in: 1800, interval: 3}`; with `app_ids` you need developer on every app's project (else 404) |
| POST | `/v1/auth/cli/inputs/{id}/poll` | the creating credential ([Input requests](#input-requests)) | – | `{status: "pending"\|"cancelled"\|"expired"\|"consumed", interval}`, plus `unavailable_apps` (> 0: an app was deleted or is no longer writable); once filled without `app_ids`: `{status: "submitted", values}` exactly once (then consumed and wiped); with `app_ids`: `{status: "submitted", keys, apps: [{id, name}]}`, never the values |
| POST | `/v1/auth/cli/inputs/{id}/cancel` | the creating credential | – | `{ok, status}` with the status after the call: cancels a `pending` request and a `submitted` one without `app_ids` (its values are wiped); one with `app_ids` that is already submitted stays `submitted` (the values are in the apps' Environment) |
| GET | `/v1/inputs/{id}` | session, creator only | – | `CliInput` `{id, title, description, fields, apps: [{id, name, project_name}], requested_by: {kind: "cli"\|"session", name, prefix}, unavailable_apps, status, expires_at, created_at}` (never values; `name`/`prefix` are the token's, null for a session) |
| POST | `/v1/inputs/{id}/submit` | session, creator only | `{values: {key: value}}` | `{ok, keys}` (`keys: []` and nothing written when every value is empty); 409 `input_not_pending`, 409 `input_apps_unavailable`; 422 with `details.field` for a missing required field, an unknown key, a multi-line value in a single-line field or a value over 8 KB; 422 without `details.field` when all values together exceed 48 KB or an app's Environment would exceed its 64 KB limit |

- A token is `dpt_` + 43 random characters. Only its SHA-256 is stored (`cli_tokens`); between approval
  and the poll that collects it, the raw token waits encrypted with `MASTER_KEY` in `cli_logins` and is
  deleted on delivery. Login requests are pruned a day after they expire.
- `Authorization: Bearer dpt_...` acts as the token's user on every endpoint a signed-in session can
  call, with that user's roles, until it is revoked or the account is disabled. `last_used_at` is
  written at most once a minute.
- **Session only:** approving, denying or looking up a login code, changing the password, linking or
  unlinking Google/GitHub, and opening or submitting an input form (`GET /v1/inputs/{id}`,
  `POST /v1/inputs/{id}/submit`) refuse a token (403), so a leaked token can't mint more tokens, lock the
  owner out or fill its own forms. Project API keys (`dpl_`) remain limited to the data, query, schema and MCP endpoints.
- `PATCH /v1/projects/{pid}/apps/{id}` accepts `env_set: {k: v}` and `env_unset: [k]` (not together with
  `env`), so changing one variable never sends or reveals the others ([DEPLOYMENTS.md](DEPLOYMENTS.md)).
- An input request (`cli_inputs`) has up to 10 fields `{key, label, secret?, help?, placeholder?,
  pattern?, optional?, multiline?, link?, link_label?}`; `key` matches `^[A-Za-z_][A-Za-z0-9_]{0,127}$`
  (the whole key, like env names). `pattern` is a hint for the browser only: the server checks at create
  that it compiles (else 422) but never runs it on submitted values, and the page checks the whole value
  against it (a pattern the browser can't compile is skipped). Values are single-line unless
  `multiline`, trimmed, at most 8 KB each and 48 KB together. Without `app_ids` the values wait
  encrypted with `MASTER_KEY` until the one poll that collects them, at most 10 minutes (the scheduler
  then wipes them and the request reports `expired`); with `app_ids` they are merged into each app's
  Environment like `env_set` and never stored in `cli_inputs`. Each row records who created it (the
  token's id, name and prefix, or a dashboard session). Rows are pruned a day after they expire. The
  form is `/input/<id>` in the dashboard.
- Audit actions: `cli.login_create`, `cli.login_approve`, `cli.login_deny`, `cli.token_create` (`--local`),
  `cli.token_revoke`, `cli.input_create` (title, keys) and `cli.input_submit` (keys, app ids), never values.
- Phishing: someone could start `deployer login` themselves and send you their link. The approval page
  shows the requesting computer and asks you to confirm the code matches your own terminal; approve only
  codes you started.
- Phishing with input requests: anyone holding one of your `dpt_` tokens (a leaked token, a misled AI
  agent) can create a form with any title and labels on your real Deployer address, and gets back
  whatever you type. Check *Asked by command line '…'* on the page against a command you started, and
  never type your account password or a login approval code into an input form: Deployer never asks for
  them there (the page says so). If you didn't start it, leave it and revoke that token under
  **Account settings → Command-line sign-ins**; that also cancels its open requests.

The client is `installer/deployer_cli.py` (standard library only); `deployer.sh` hands it `login`,
`logout`, `whoami`, `tokens`, `projects`, `apps`, `app`, `deploy`, `domain`, `env`, `google-oauth`, `ask`,
`alerts`, `cloud` and `cloudflare` (and `oauth`, when run without sudo and signed in) before its sudo re-run. The Windows `deployer.ps1` does not have these commands yet; run the Python file
directly there.
