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
  through Caddy, like any other client). They can reach Caddy's internal `:8081` listener too, but
  it takes the client IP from `Cf-Connecting-Ip` (and the scheme from `X-Forwarded-Proto`) only on
  connections from the `tunnel` network, which only Caddy and the cloudflared sidecar join; the API
  honours `X-Forwarded-For` only from the `caddy` container. On `:8080` every LAN client still shares
  one address, so IP-based limits there are per LAN, not per device.
- **App database access** ([docs/DEPLOYMENTS.md](docs/DEPLOYMENTS.md) "Database access"): by default
  app containers cannot reach any database. A project admin can opt an app in; the worker then
  connects its container to the internal `appdb` network, which carries only the platform MariaDB
  and MongoDB (never the API, Redis or the worker). The app receives only its project's managed sources' own restricted
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
  developers and `service` keys runs in a real `mongosh` (full Node.js), so it runs only in the
  `query-shell` sidecar (`api/app/shell_runner.py`): a container with no Deployer secrets in its
  environment, no volumes, no Docker socket, a read-only filesystem, all capabilities but the five it
  needs to switch uids dropped, CPU/memory/process caps, and networks that reach only the API, the
  worker, MongoDB and external MongoDB servers. The API and worker send it just the source's own
  connection string and the code. Each shell runs under its own slot uid, so concurrent runs (other
  projects) cannot read each other's connection strings, and the uid's processes and files are
  removed after every run. What a script can still do: use the source's own credentials (its
  project's database), reach the internet and this PC (`host.docker.internal`, for external servers),
  and the managed MongoDB and the API's HTTP port on the `query` network (both need credentials). The
  name filter (`require`, `process`, `constructor`, `load`, ... refused for every role) and the API
  and worker sealing themselves (secrets removed from their environment after loading,
  `prctl(PR_SET_DUMPABLE, 0)`) remain as extra layers.
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
  create billable resources in that account; developers cannot. Service API keys can create a database
  in the AWS account through MCP (`create_cloud_database`), only with `confirm_billing: true`. In the worker the keys
  live only in memory for a job: registry passwords/tokens reach `docker login` on stdin with a
  throw-away `DOCKER_CONFIG`, never argv; the Google token endpoint is fixed (a key file's `token_uri`
  is ignored), Google URLs are built from validated ids, and the Hosting upload URL must be Google's.
  Cloud apps receive only their own environment variables - no API key, no data API URL, no database
  credentials of this PC. Build output uploaded to S3 / Hosting skips symlinks, so a build cannot
  publish the worker's own files. Removing a connection deletes the stored key; delete the key
  in AWS / Google too when you no longer need it.
- **Cloud databases** ([docs/CLOUD.md](docs/CLOUD.md) "C2-1"): a database Deployer creates in AWS gets a
  random 32-character master password stored like every data source password (`encrypt_json`), shown
  only through the audited connection details. Its endpoint is public, but its security group (tagged
  `managed-by=deployer`; the IAM policy lets Deployer change only groups with that tag) lets in only
  this PC's current public IP and the App Runner VPC connector's group; MySQL / MariaDB users must use
  TLS (`REQUIRE SSL`), PostgreSQL forces it. Deployer verifies the RDS server certificate and host
  name against AWS's RDS CA bundle shipped in the API image (GovCloud / China endpoints and RDS Proxy
  excepted, see "Networking" there). App Runner apps with database access get the credentials as runtime
  environment, never anything of this PC. Connected (not created) databases are never modified.
  DynamoDB databases ("C2-2") hold no credential of their own: Deployer uses the AWS connection's key
  and a source only reaches the tables it was given (so the project's API keys can't read the
  account's other tables); viewers may only run Query / Scan / GetItem in the console. App Runner apps
  get no key either, but an IAM role (`deployer-app-*`) whose only policy allows item operations on
  exactly the project's tables. The IAM policy may read and write items of any table (connected tables
  keep their own names) but create, change or delete only `deployer-*` tables.
  Firestore databases ("C2-3") also hold no credential of their own: Deployer calls the Firestore REST API
  with the Firebase connection's service-account token (requests only go to `firestore.googleapis.com`,
  every id in a path is percent-encoded and the path checked, so a document id can't redirect a call); the
  service account needs only Cloud Datastore User (documents, not databases or rules). A source reaches one
  database; viewers may only run `query` / `count` / `get` in the console. Deployer never creates, deletes or
  changes a Firestore database or its security rules. Cloud Run apps get no key: they use their own service
  account, to which the owner grants Cloud Datastore User (Deployer cannot grant IAM roles).
  Realtime Databases ("C2-4") hold no credential either: Deployer calls the database's REST API with a token
  for the `firebase.database` scope, sent only to a URL that matches a Firebase database host
  (`<id>.firebaseio.com` / `<id>.<region>.firebasedatabase.app`, taken from Firebase's management API, never
  typed by a user) with percent-encoded keys (no `.`, so a path can't climb out); answers over 32 MB are cut
  off while streaming. That token is admin: the database's security rules don't apply to the dashboard, the
  data API or MCP, so the project's roles are the gate (viewers and anon keys read, developers and service
  keys write; the root can't be replaced or deleted). The role it needs (Firebase Realtime Database Admin)
  also creates instances; Deployer only ever creates the project's default one, after the billing
  confirmation, and never deletes one.
- **Rate limits:** sign-in 10 attempts / 15 min per IP+email and 50 failed attempts / hour per email
  from any IP (so rotating or forging IPs doesn't buy more guesses; the flip side is that someone
  guessing can lock an account for up to an hour - `deployer reset-password` clears it), plus 30
  password sign-ins + sign-ups / 15 min per IP. On the LAN port (`:8080`) every LAN and localhost
  client arrives from the same address (the WSL relay / port-forwarding gateway), so "per IP" there
  means the whole LAN together: one device guessing can make every LAN sign-in wait up to 15 minutes
  (`deployer reset-password` clears that too), and the audit log shows that gateway address instead
  of the device's (tunnel visitors keep their own IP). Project API keys 600 requests / min per
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
