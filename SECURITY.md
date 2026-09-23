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
  are reachable only through Caddy's per-app port and the app's hostnames.
- **App database access** ([docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md) "Database access"): by default
  app containers cannot reach the internal `backend` network. A project admin can opt an app in; the
  worker then connects its container to `backend`, which also carries Redis (password-protected) and
  the platform MariaDB. The app receives only its project's managed sources' own restricted
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
