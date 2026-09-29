# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub: go to the repository's **Security** tab and choose
**Report a vulnerability** (GitHub private vulnerability reporting / security advisories). Include
the affected version, steps to reproduce and the impact you expect.

You should get an acknowledgement within a few days. We will work with you on a fix and credit you
in the advisory unless you prefer to stay anonymous.

## Supported versions

Security fixes are made for the latest release. Update with `deployer update`.

## Scope notes

- Each Deployer installation is self-hosted and independent; the project operates no servers and
  holds no user data or credentials.
- The default listener is plain HTTP intended for `localhost` or a trusted private network. Exposing
  it directly to the internet without a TLS tunnel or reverse proxy is not a supported configuration.
- **Worker trust** (push-to-deploy, [docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md)): the `worker` service
  mounts `/var/run/docker.sock` and runs as root so it can build app images and start app containers.
  Anyone who can run code in the worker is root on the Docker engine (and on the WSL2 VM). The API
  container has no socket and stays unprivileged; only project developers can create apps, and their
  build commands run inside BuildKit / the app container, never in the worker process. Deployed app
  containers get no volumes, no extra capabilities, `no-new-privileges`, memory / CPU / pid limits and
  are reachable only through Caddy's per-app port and the app's hostnames. They run on their own
  `apps` network, shared only with Caddy and the worker, so they cannot call the API directly (only
  through Caddy, like any other client). They can still reach Caddy's internal `:8081` listener,
  which takes the client IP from `Cf-Connecting-Ip`, so an app can make its requests appear to come
  from any IP there: IP-based limits and the IPs in the audit log are not proof of origin.
- **App database access** ([docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md) "Database access"): by default
  app containers cannot reach the internal `backend` network. A project admin can opt an app in; the
  worker then connects its container to `backend`, which also carries Redis (password-protected),
  the platform MariaDB and the API itself (so such an app can also call the API directly). The app receives only its project's managed sources' own restricted
  credentials (per-database users, never root), passed through the process environment, never argv
  or the deployment log. Treat enabling it as trusting that app's code with network reach to those
  services; developers can switch it off but not on.
- **Co-hosting** ([docs/COHOSTING.md](docs/COHOSTING.md)): a project admin can let a developer+ member
  keep a live two-way copy of the project's managed databases on a host device that member owns. The
  device receives only the rows/documents of the databases it hosts for that project (over the
  existing device channel) - never the main server's secrets, the source's own credentials (the device
  creates its own database user), API key secrets, OAuth or Cloudflare settings. Its `sync.*` RPCs are
  refused for any database not in its hosted-credentials list, and the main server validates every
  table/column name a device sends against `information_schema` before building SQL (values are
  always bound). Treat enabling co-hosting as handing that member a full copy of the data, and its
  writes as trusted like any developer's; switching the flag off, demoting or removing the member
  pauses their copies. Sync errors are redacted before they are stored or logged.
- **Co-hosted apps** ([docs/COHOSTING.md](docs/COHOSTING.md) "Websites on both PCs"): when a project
  admin ticks *Co-host this app*, each co-host device builds and runs the app's live commit with its
  own worker (which is root on that PC's Docker engine, like the main server's). The device receives
  the generated Dockerfile, the app's own environment variables (never `DEPLOYER_API_KEY`, never
  `DEPLOYER_DB_*`, and no variable whose value contains a password or URI of the project's databases on
  the main server; the device injects `DEPLOYER_DB_*` for its own local copies with its own
  credentials), the app's hostnames, and the connector token of the separate *apps* tunnel (which
  routes only co-hosted app hostnames; the dashboard tunnel token and the Cloudflare API token never
  leave the main server). Anything else a user typed into the app's variables is readable by whoever
  controls that PC. The repository token (or the creator's GitHub connection token) is sent only when an
  admin ticks *Let co-hosts clone this private repository*; a token sent to a device is readable by
  that PC's owner, so prefer a read-only fine-grained per-repository token for co-hosted apps. The
  device refuses app environments carrying `DEPLOYER_API_KEY`/`DEPLOYER_DB_*` and injects only
  databases in its hosted-credentials list. A co-host PC serves the app's visitors: its owner can see
  and alter that traffic.
- **Query console** ([docs/QUERY_CONSOLE.md](docs/QUERY_CONSOLE.md)): MongoDB shell code from project
  developers and `service` keys runs in a real `mongosh` (full Node.js) inside the API container, as
  the API's uid. Mitigations: the shell gets a minimal environment and no secrets on argv; code naming
  `require`, `process`, `constructor`, `load`, ... is refused for every role (a textual filter, so
  best effort); and the API process (and the worker, which runs device-hosted queries) removes its
  secrets from its environment after loading them and marks itself non-dumpable
  (`prctl(PR_SET_DUMPABLE, 0)`), so `/proc/1/environ` and `/proc/1/mem` are unreadable to the shell.
  A script that gets past the filter can still read the files that uid can (`/backups`, `/tunnel`),
  reach the internal networks, and see concurrent shells' environments; for a device-hosted source
  the shell runs in that device's worker, which holds the Docker socket (root on that PC). Treat developer access to a
  MongoDB source (and `service` keys) as trusted until the planned fix lands: running mongosh in a
  separate container with no secrets and no volumes.
- **GitHub repository access** ([docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md) "Connect a Git repository"):
  connecting GitHub grants the instance's GitHub OAuth app the `repo` and `admin:repo_hook` scopes,
  which GitHub does not narrow further: read/write access to every repository the user can reach, and
  their webhooks. Deployer stores the token encrypted (`MASTER_KEY`, AES-256-GCM), never logs or returns
  it, redacts it from build logs, and uses it only to list/read that user's repositories, to clone the
  apps that user created with the connection (github.com URLs only; if another member re-points such an
  app at a different repository the connection is detached) and to create/update/remove those apps'
  push webhooks. The connect callback never signs anyone in and only stores a token for the signed-in
  user who started the flow. Disconnecting (Account settings) deletes the token; revoke the grant at
  github.com/settings/applications as well. Prefer a fine-grained, read-only per-repository token
  (the manual path) when that broad scope is not acceptable.
- **Cloud accounts** ([docs/CLOUD.md](docs/CLOUD.md)): the instance owner stores an AWS access key
  (optionally assuming a role) or a Google service-account key per connection, encrypted with
  `MASTER_KEY` (AES-256-GCM), validated on save and never returned by any endpoint, log, audit entry or
  MCP tool (lists show the account id / project and the key's last 4 characters only). Scope it: a
  dedicated IAM user with the policy shown in the dashboard (every resource named `deployer-*`, one
  IAM role it may create and pass) or a dedicated service account with the listed roles; a connection
  can be limited to one project. Project admins choose which connection an app uses, so they can
  create billable resources in that account; developers and API keys cannot. In the worker the keys
  live only in memory for a job: registry passwords/tokens reach `docker login` on stdin with a
  throw-away `DOCKER_CONFIG`, never argv; the Google token endpoint is fixed (a key file's `token_uri`
  is ignored), Google URLs are built from validated ids, and the Hosting upload URL must be Google's.
  Cloud apps receive only their own environment variables - no API key, no data API URL, no database
  credentials of this PC. Build output uploaded to S3 / Hosting skips symlinks, so a build cannot
  publish the worker's own files. Removing a connection deletes the stored key; delete the key
  in AWS / Google too when you no longer need it.
- **Rate limits:** sign-in 10 attempts / 15 min per IP+email and 50 failed attempts / hour per email
  from any IP (so rotating or forging IPs doesn't buy more guesses; the flip side is that someone
  guessing can lock an account for up to an hour - `deployer reset-password` clears it), plus 30
  password sign-ins + sign-ups / 15 min per IP; project API keys 600 requests / min per
  key (instance setting `api_key_rate_limit`); MCP 60 tool calls / min per key; GitHub webhooks per
  app. Over a limit: `429 rate_limited` with a `Retry-After` header.
- **Alert webhook** ([docs/MONITORING.md](docs/MONITORING.md)): https only, stored encrypted, no
  redirects followed, never logged; payloads carry alert names, severities and counts only.
- **Deploy input rules** (review of 2026-09-28, [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md)):
  `root_dir` and a repository `Dockerfile` must resolve (symlinks followed) inside the checkout; only
  hex commit shas ever reach git; a stored repository token is dropped when the app's repository moves
  to another host without a new token; webhook bodies are capped at 5 MB and MCP bodies at 1 MB before
  anything is buffered; MCP app tools (settings, build and runtime logs) need a `service` key, never an
  `anon` key.
