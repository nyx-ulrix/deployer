# How the main code paths work

This page follows eight things Deployer does, step by step, as the code does them. Each section has
one or more diagrams (GitHub draws them from the Mermaid text) and a line naming the files they were
drawn from, so you can check a diagram against the code or update it after a change.

A few words used throughout:

- **API**: the FastAPI server in `api/app` (the dashboard, GitHub webhooks and AI agents all call it).
- **Worker**: the same code started as `python -m app.worker`. It runs background **jobs** (rows in the
  `jobs` table; Redis only carries "wake up, job X is ready") and a **scheduler** that one worker at a
  time leads, every 15 seconds.
- **Platform database**: Deployer's own MariaDB database (users, projects, jobs, ...). Your projects'
  databases are separate.
- **Caddy**: the web server in front of everything; it forwards requests to the API, the dashboard and
  your deployed apps.

For the bigger picture start with [ARCHITECTURE.md](ARCHITECTURE.md); for every endpoint see
[API.md](API.md).

## 1. Signing in

### With an email and password

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as API
    participant R as Redis
    participant D as Platform DB
    B->>A: email + password
    A->>R: count attempt (per IP, per IP+email, per email)
    alt over a limit
        A-->>B: 429 rate_limited with retry_after
    end
    A->>D: find user by lower-cased email
    A->>A: argon2 verify (dummy hash if no such user, at most 2 at once)
    alt wrong password, no user or disabled
        A->>D: audit auth.login_failed
        A-->>B: 401 invalid_credentials
    else correct
        A->>A: re-hash if argon2 settings changed
        A->>R: clear the IP+email and email counters
        A->>D: new refresh token row (only its SHA-256, new family)
        A-->>B: access token (JWT, 15 min) + refresh cookie (HttpOnly, 30 days)
    end
```

From `api/app/routers/auth.py`, `services/rate_limit.py`, `services/passwords.py` and `services/tokens.py`.

Every attempt is counted in Redis in three buckets: one per network address (30 per 15 minutes), one
per address and email (10 per 15 minutes) and one per email from anywhere (50 per hour). The password
is checked with argon2, which is slow on purpose; an unknown email is checked against a dummy hash so
both answers take the same time. A success gives the browser a short-lived access token to send with
each request and a long-lived refresh cookie that JavaScript cannot read. If Redis is down the limits
are skipped rather than locking everyone out.

### Keeping the session alive (refresh rotation)

```mermaid
flowchart TD
    A["Access token expired: dashboard asks to refresh"] --> B["Look up the cookie's SHA-256"]
    B --> C{"Token found?"}
    C -->|"no"| X["401, cookie cleared"]
    C -->|"yes"| D{"Already used or revoked?"}
    D -->|"no"| E{"Expired, or account disabled?"}
    E -->|"yes"| X
    E -->|"no"| F["Issue new token in the same family<br/>mark the old one replaced"]
    F --> G["New cookie + new access token"]
    D -->|"yes"| H{"Rotated less than 30 s ago<br/>and family still live?"}
    H -->|"yes: two tabs refreshed together"| I["Give this tab a sibling token"]
    I --> G
    H -->|"no: a stolen token was replayed"| J["Revoke the whole family"]
    J --> X
```

From `api/app/services/tokens.py` (`rotate_refresh_token`) and `dashboard/src/api/client.ts`.

Each refresh token works once: using it hands out a new one and retires the old. If a retired token
shows up again, someone may have copied it, so every token of that sign-in (the "family") is revoked
and the person must sign in again. The one exception is two browser tabs refreshing in the same
moment, which a 30-second grace window allows. Signing out revokes the family; changing your password
revokes every other sign-in.

### With Google or GitHub

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as API
    participant R as Redis
    participant P as Google or GitHub
    B->>A: start sign-in (optional invite token)
    A->>R: save state record for 10 min (PKCE verifier, hash of a browser nonce, invite)
    A-->>B: redirect to provider + nonce cookie (HttpOnly, 10 min)
    B->>P: user approves
    P-->>B: redirect back with code + state
    B->>A: callback (code, state, nonce cookie)
    A->>R: read and delete the state record (one use)
    alt state unknown or cookie does not match
        A-->>B: back to login with oauth_state_invalid
    end
    A->>P: exchange code + PKCE verifier for a token
    A->>P: fetch profile, require a verified email
    alt identity already linked
        A->>A: sign in that user
    else email belongs to an existing account
        A-->>B: login error account_exists_link_required
    else new person
        A->>A: need a valid invite for this email, or open sign-up
        A->>A: create user + identity, accept invite (joins the project)
    end
    A-->>B: redirect to the dashboard + refresh cookie
```

From `api/app/routers/auth.py` (`oauth_start`, `oauth_callback`) and `api/app/services/oauth.py`.

The state record proves the callback answers a sign-in this Deployer started, PKCE proves the code was
not intercepted, and the nonce cookie ties the flow to the browser that started it, so a link crafted
by someone else cannot sign you into their account. Deployer never merges accounts by itself: if the
email already has a password account, you must sign in and link Google or GitHub from your settings.
An invite only works for the email it was sent to.

## 2. A data API request with an API key

```mermaid
flowchart TD
    A["App sends a request with Authorization: Bearer dpl_..."] --> B{"Route accepts keys?<br/>rows, documents, rtdb, query, schema, MCP"}
    B -->|"no"| Z1["401 api_key_not_allowed"]
    B -->|"yes"| C["Data routes only: CORS answers any origin, no cookies"]
    C --> D["Find the key by its SHA-256"]
    D --> E{"Known, this project, not revoked?"}
    E -->|"no"| Z2["401, or 404 for another project"]
    E -->|"yes"| F{"Under the per-key limit?<br/>default 600 per minute"}
    F -->|"no"| Z3["429 rate_limited"]
    F -->|"yes"| G["Act as the key's creator, or the owner if they left"]
    G --> H{"Role of the key"}
    H -->|"anon"| I["Acts as viewer: reads only"]
    H -->|"service"| J["Acts as developer: reads and writes"]
    I --> K{"Route needs developer?"}
    K -->|"yes"| Z4["403 This anon key is read-only"]
    K -->|"no"| L["Run on the data source"]
    J --> L
    L --> M["MariaDB, Postgres, MongoDB, Firestore ...<br/>or the device that hosts it"]
```

From `api/app/main.py` (`KEY_ROUTES`, `KeyRoutesCORS`), `api/app/deps.py` (`require_role`,
`load_api_key_access`, `check_api_key_rate`), `api/app/routers/data.py` and `api/app/routers/mcp.py`.

Project API keys start with `dpl_`; only a hash is stored, so the key itself is never kept on the PC.
An anon key (safe to put in a website) can only read rows and documents; a service key can also
write. Browsers may call these routes from any website, but never with cookies, so a key cannot be
used to ride on someone's dashboard session. Each key has its own request limit per minute, and keys
of a disabled owner stop working. Anon keys cannot use the query console at all (section 3).

## 3. Running a query in the console or notebook

### SQL

```mermaid
flowchart TD
    A["Query from the console, notebook or a service key"] --> B{"Anon key?"}
    B -->|"yes"| Z1["403: queries need a service key"]
    B -->|"no"| C["Split the script into statements"]
    C --> D{"Viewer?"}
    D -->|"yes"| E{"Each statement starts with SELECT, WITH, SHOW ...<br/>and has no write word or risky function?"}
    E -->|"no"| Z2["403 read_only_role"]
    E -->|"yes"| F["Connect from the source's pool"]
    D -->|"no"| F
    F --> G["Set the database's own statement timeout"]
    G --> H{"Viewer?"}
    H -->|"yes"| I["Switch the session to READ ONLY<br/>refuse with 503 if that fails"]
    H -->|"no"| J["Run statements one by one"]
    I --> J
    J --> K["Watchdog cancels a statement that outlives the timeout"]
    K --> L["Stop at the first error, keep max_rows rows"]
    L --> M["Throw the connection away"]
    M --> N["Query log: text with passwords masked<br/>audit: counts only"]
```

From `api/app/routers/query.py` (`run_query`), `api/app/services/query_console.py` (`run_sql`,
`sql_read_only_refusal`, `_Watchdog`) and `api/app/services/query_log.py` (`record_run`, `redact`).

A viewer's SQL is checked twice: first by reading the words (every statement must start like a read
and contain no writing keyword), then by the database itself, which is told to refuse writes for this
session. A timer cancels any statement that runs longer than the chosen timeout, even if the
database's own timeout did not apply. Afterwards the connection is discarded so settings changed by
the script cannot leak into the next request. Every run, including refusals, lands in the query log
with passwords in the text replaced by `***`.

### MongoDB

```mermaid
sequenceDiagram
    participant A as API
    participant S as query-shell sidecar
    participant M as mongosh process
    participant DB as MongoDB
    A->>A: refuse Node.js names (require, process, eval ...) for every role
    A->>A: viewers: refuse write and admin names
    A->>S: run (uri, database, code, marker, row limit, timeout)
    alt all 4 slots busy
        S-->>A: 429 too_many_queries
    end
    S->>S: take a free slot uid, private temp folder
    S->>M: start mongosh as that uid, secrets only in its environment
    M->>DB: connect with the source's own user, run the code
    M-->>S: printed text + one marker line with the result
    S->>S: kill at the timeout or 8 MiB of output
    S->>S: kill every process of the slot uid, delete its files
    alt a process will not die
        S->>S: retire the slot for good
    else clean
        S->>S: put the slot back
    end
    S-->>A: stdout, stderr, timed_out
    A->>A: mask passwords, parse the marker line
```

From `api/app/services/query_console.py` (`run_mongosh`, `_call_shell`) and `api/app/shell_runner.py`
(`Runner.run`, `_clean_up_slot`).

MongoDB shell code is real JavaScript, so it never runs inside the API, which holds Deployer's secrets.
It runs in a separate small container with no secrets, under one of four throw-away user ids, so one
query cannot spy on the next. After each run everything that user id started is killed and its files
removed; if that fails the slot is never used again. The word checks are a first filter only: for
viewers the real limit is the MongoDB user the source connects with.

## 4. Push-to-deploy

### From a push to a queued job

```mermaid
sequenceDiagram
    participant G as GitHub
    participant A as API
    participant D as Platform DB
    participant R as Redis
    G->>A: push event to the app's webhook (body at most 5 MB)
    A->>A: HMAC-SHA256 of the body with the app's secret
    alt signature wrong
        A-->>G: 401 bad_signature
    end
    A->>R: at most 6 signed deliveries per minute per app
    A->>D: project owner still active?
    alt not a push, other branch, or app builds on GitHub Actions
        A-->>G: ignored
    end
    alt a deployment of this app is still queued
        A->>D: give it the newer commit
    else
        A->>D: new deployment (queued)
        A->>D: new app.deploy job, unless one for this app is active
    end
    A->>R: push the new job's id on jobs:queue
    A-->>G: 202 deployment_id
```

From `api/app/routers/apps.py` (`github_webhook`, `_github_delivery`) and
`api/app/services/deployments.py` (`verify_signature`, `handle_push`, `start_deployment`).

GitHub signs every delivery with a secret only it and Deployer know; anything else is turned away
before it can use up the app's delivery limit. Only one deploy per app runs at a time: a push that
arrives while another deploy is waiting simply updates the waiting one to the newest commit.

### The worker's deploy job

```mermaid
flowchart TD
    A["Worker takes the job from jobs:queue<br/>claims it only if still queued"] --> B{"Rollback or new environment?"}
    B -->|"yes"| C["Reuse the old image"]
    B -->|"no"| D["git clone --depth 1, check out the commit"]
    D --> E["docker build with a generated Dockerfile<br/>static, node or python preset, or the repo's own"]
    E --> F{"Target"}
    C --> F
    F -->|"cloud"| G["Publish on AWS or Firebase: section 7"]
    F -->|"this PC"| H["Start a new container with the app's variables<br/>and database variables if allowed"]
    H --> I{"Accepts connections on its port within 60 s?"}
    I -->|"no"| J["Show its last log lines, remove it<br/>mark failed, old version keeps serving"]
    I -->|"yes"| K["Write the app's Caddy file and reload Caddy"]
    K --> L["New deployment live, previous one superseded"]
    L --> M["Remove the previous container"]
    M --> N["Keep images of the 5 newest successful deploys, delete older"]
    J --> O["Start the next waiting deployment of this app"]
    N --> O
```

From `api/app/services/deployments.py` (`_job_deploy`, `generate_dockerfile`, `build_image`,
`route_app`, `render_caddyfile`, `_prune_images`, `rollback`), `api/app/services/jobs.py` (`claim`) and
`api/app/worker.py` (`runner_loop`).

The new version is started next to the old one and only gets traffic once it answers on its port; then
Caddy's per-app file (`caddy_apps/<app id>.caddy`) is pointed at it, so visitors switch over without a
gap. A failed build or health check leaves the previous version serving. The images of the last five
successful deploys are kept, which is what "Rollback" re-uses: a rollback is a new deployment that
skips the clone and build. Tokens and secret variables are removed from the build log before it is saved.

### Crash recovery

```mermaid
flowchart TD
    A["Scheduler leader, every 15 s"] --> B["Running jobs with no heartbeat for 60 s: failed"]
    B --> C["Queued jobs older than 1 min: put back on jobs:queue"]
    C --> D{"Active deployment whose job is gone or finished?"}
    D -->|"yes"| E["Close it as failed or cancelled"]
    D -->|"no"| F["Leave it"]
    E --> G["Start the app's next waiting deployment"]
    F --> H["Remove containers and Caddy files of deleted apps"]
    G --> H
```

From `api/app/worker.py` (`scheduler_tick`, `main`), `api/app/services/jobs.py` (`recover_stale`,
`redispatch_queued`) and `api/app/services/deployments.py` (`scheduler_tick`, `_sweep_queued`,
`_remove_orphans`).

A running job refreshes a "still alive" key in Redis every 15 seconds. If the worker crashes or the
PC restarts mid-deploy, that key expires, the job is marked failed and its deployment is closed, so
the app is not stuck "building" forever and its next deploy can start. The worker also does this check
once when it starts.

## 5. Backups and point-in-time recovery

### What the scheduler starts

```mermaid
flowchart TD
    A["Scheduler leader, every 15 s"] --> B["For each managed MariaDB or MongoDB database"]
    B --> C{"Snapshot due by its schedule?<br/>hourly, every 6 h or daily"}
    C -->|"yes"| D["backup.snapshot job"]
    B --> E{"Point-in-time on and logs due?<br/>MariaDB 5 min, MongoDB 1 min"}
    E -->|"yes"| F["backup.archive_logs job"]
    B --> G{"Newest backup not checked for 7 days?"}
    G -->|"yes"| H["backup.verify job"]
    A --> I["Hourly: backup.prune<br/>daily: platform snapshot"]
    D --> J["Dump: mariadb-dump or mongodump<br/>record the exact log position and row counts"]
    J --> K["Compress, encrypt with AES-256-GCM, store"]
    F --> L["Copy new binlog files or oplog entries<br/>since the last saved position"]
    L --> K
    H --> M["Load the dump into a scratch database<br/>compare row counts with the ones recorded"]
```

From `api/app/services/backups.py` (`scheduler_tick`, `start_snapshot`, `perform_snapshot`,
`archive_source_logs`, `perform_verify`), `api/app/services/backup_engine.py` and
`api/app/services/backup_crypto.py`.

A snapshot is a full copy of one database, taken at a known spot in the database's change log. Between
snapshots, the change log itself (MariaDB's binlog, MongoDB's oplog) is copied every few minutes, so any
moment can be rebuilt later. Everything is encrypted with a key derived from the install's
`MASTER_KEY`. Once a week the newest backup is test-restored into a scratch database and its row counts
compared, so a broken backup is found before you need it.

### Restoring

```mermaid
flowchart TD
    A["Restore request: a backup, or a point in time"] --> B{"Point inside the recovery window?"}
    B -->|"no"| Z["422 outside_recovery_window"]
    B -->|"yes"| C["Pick the newest snapshot before that time<br/>plus the log segments after it"]
    C --> D{"Mode"}
    D -->|"new database"| E["Create a new database and data source"]
    D -->|"in place, owner only"| F["Take a safety snapshot first"]
    E --> G["Load the snapshot into a temporary database"]
    F --> G
    G --> H["Replay the logs up to the chosen second"]
    H --> I["Move the tables or collections into the target"]
    I --> J["Mark the source ok, start a fresh snapshot"]
    G -.->|"any failure"| K["New database dropped again<br/>in place: target untouched"]
```

From `api/app/services/backups.py` (`recovery_window`, `plan_restore`, `start_restore`,
`perform_restore`, `_discard_new_source`) and `api/app/services/backup_engine.py`.

The usual restore makes a new database next to the old one, so nothing you have is overwritten. An
in-place restore is for owners only and always takes a safety snapshot first. Either way the data is
rebuilt in a temporary database and only moved into place once that worked.

## 6. A co-hosting sync round

```mermaid
flowchart TD
    A["Every 2 s, scheduler leader only:<br/>each syncing copy, 4 at a time"] --> B["Take the copy's Redis lock"]
    B --> C{"Device may still hold this project?"}
    C -->|"no"| P["Pause the copy, send nothing"]
    C -->|"yes"| D{"Device online?"}
    D -->|"no"| Q["Skip, the lag grows"]
    D -->|"yes"| E["Read changes since each side's position<br/>MariaDB binlog by GTID, MongoDB change stream"]
    E --> F["Batch: at most 1000 changes or 4 MB<br/>skip the sync's own writes, tables without a key"]
    F --> G["Send main server changes to the device"]
    G --> H["Save the main server's position"]
    H --> I["Send device changes to the main server"]
    I --> J["Save the device's position"]
    G --> K{"Target still holds the version the change started from?"}
    I --> K
    K -->|"yes"| L["Apply it, remember the new version"]
    K -->|"no"| M["Open a conflict: base, main and device values<br/>this row stops syncing, others continue"]
    J --> N{"Error?"}
    N -->|"connection trouble"| O["Retry in 10 s"]
    N -->|"other"| R["Status error, back off 4 s doubling to 5 min"]
```

From `api/app/services/source_sync.py` (`sync_loop`, `run_due`, `_run_one`, `sync_round`, `_Round`,
`apply_changes`, `read_sql_changes`) and `api/app/services/cohosting.py` (`cohost_problem`).

A co-host device keeps a live copy of a main-server database, and changes made on either side are
copied to the other every two seconds. A change is applied only if the other side still has the value
it started from; if both sides changed the same row, that row becomes a conflict and waits for a person,
while every other row keeps syncing. Writes made by the sync are marked (MariaDB `server_id`, or a
`sql_log_bin = 0` session on the device; for MongoDB a stored version hash) so they are not copied back
again in an endless loop. If the device's owner loses the right to hold the project, the copy is paused
and gets nothing more.

### Resolving a conflict

```mermaid
sequenceDiagram
    participant U as Admin
    participant A as API
    participant M as Main server DB
    participant V as Device DB
    U->>A: keep main, keep device, or a custom value
    A->>A: device still allowed and online?
    A->>A: take the copy's sync lock (wait up to 30 s)
    A->>A: run one sync round first
    alt the row changed again meanwhile
        A-->>U: 409 conflict_changed, review again
    end
    A->>M: forced write of the chosen value
    A->>V: forced write of the chosen value
    alt device refused or did not answer
        A->>M: put the old main value back if nothing newer
        A-->>U: 409 write_rejected
    else both applied
        A->>A: remember the version, conflict resolved
    end
```

From `api/app/services/cohosting.py` (`resolve`, `write_both`, `_undo_primary`, `_drain`).

The chosen value is written to the main server first and then the device, while the regular sync is
held off by the same lock. If the device does not take it, the main server's change is undone, so the
two copies never silently disagree; when that cannot be guaranteed a new conflict is opened instead.

## 7. Deploying to the cloud

### Choosing a target and publishing

```mermaid
flowchart TD
    A["Admin picks where the app runs"] --> B{"Cloud target?"}
    B -->|"This PC"| L["Local deploy: section 4"]
    B -->|"AWS or Firebase"| C{"confirm_billing sent?"}
    C -->|"no"| Z["422 billing_not_confirmed with the cost note"]
    C -->|"yes"| D["Check the connection, static preset for static targets"]
    D --> E["Deploy job: clone and build on this PC as usual"]
    E --> F{"Target"}
    F -->|"aws_static"| G["Copy files out of the image<br/>upload to S3 under d/deployment id<br/>point CloudFront there, invalidate"]
    F -->|"aws_app"| H["Push image to ECR<br/>create or update App Runner, wait"]
    F -->|"firebase_hosting"| I["Upload changed files to a Hosting version<br/>7-day preview, then release"]
    F -->|"firebase_app"| J["Push to Artifact Registry<br/>create or update Cloud Run, wait<br/>Hosting rewrite to it"]
    G --> K["Deployment live, keep 5 newest cloud artifacts"]
    H --> K
    I --> K
    J --> K
```

From `api/app/routers/apps.py` (`_check_target`, `_check_billing`, `_switch_target`), `api/app/services/cloud.py` (`TARGETS`) and `api/app/services/cloud_deploy.py`
(`go_live`, `Publish.aws_static`, `aws_app`, `firebase_hosting`, `firebase_app`, `prune`).

Running an app on AWS or Firebase costs money on your own cloud account, so the API refuses until the
request says the charges are accepted (the dashboard shows the cost first). The app is still built on
this PC; only the finished files or image are sent to the cloud. Each cloud resource's id is saved the
moment it is created, so a retry never makes a second one and deleting the app knows what to remove.
Cloud apps get no address pointing back at this PC, because they must keep working while it is off.

### Building on GitHub Actions instead

```mermaid
sequenceDiagram
    participant A as Deployer
    participant C as Cloud account
    participant G as GitHub
    participant W as Workflow run
    A->>C: trust GitHub sign-in for this repo and branch only
    A->>G: commit a workflow file under .github/workflows
    G->>W: a push starts the workflow
    W->>C: sign in with a short-lived GitHub OIDC token
    W->>C: build and publish the new version
    W->>A: report the result, signed with an OIDC token for this app
    A->>A: check issuer, audience, repo, branch, workflow file
    A->>A: record the run as a deployment, prune old artifacts
    Note over A,G: PC was off during the run?
    A->>G: every 5 min, list recent runs of the workflow
    A->>A: record runs not yet seen, newest success goes live
```

From `api/app/services/github_actions.py` (`_setup`, `render_workflow`, `record_report`, `_verify`,
`reconcile`, `_reconcile_app`) and `api/app/routers/apps.py` (`_actions_report`).

With this option GitHub's computers build every push, so the app deploys even when the PC is off.
No cloud key is stored in the repository: the workflow proves who it is with a token GitHub issues
for that one run, which the cloud account has been told to trust for that repository and branch only.
When the PC comes back it asks GitHub for the runs it missed and adds them to the history, so rollback
still works.

## 8. Installing, updating and staying up

### `deployer update`

```mermaid
flowchart TD
    A["deployer update, as administrator"] --> B["Offer a backup first:<br/>.env, mariadb-dump, mongodump"]
    B --> C["Download the new version"]
    C --> D{"MongoDB data on 8.0 but new version runs 5.0?"}
    D -->|"yes"| Z["Stop, nothing changed"]
    D -->|"no"| E["Copy the new files, keep .env, lock folder permissions"]
    E --> F["Pull images, or build them if not published"]
    F --> G["MongoDB upgrade chain in one-off containers<br/>5.0 to 6.0 to 7.0 to 8.0, resumable"]
    G --> H["docker compose up"]
    H --> I["migrate container runs database migrations<br/>API starts only after it exits"]
    I --> J{"Healthy within 7 to 10 min?"}
    J -->|"no"| Y["Show diagnostics and the way back"]
    J -->|"yes"| K["Save the version, re-register the sign-in task"]
    K --> L["Remove unused images"]
```

From `installer/deployer.ps1` (`Invoke-Update`, `Invoke-Backup`), `installer/lib/common.ps1`
(`Assert-DeployerMongoRef`, `Invoke-DeployerImages`, `Update-DeployerMongo`, `Wait-DeployerHealth`),
`deploy/docker-compose.yml` (`migrate`) and `api/docker-entrypoint.sh`.

An update replaces the program files but never `.env`, which holds the install's keys and passwords.
MongoDB can only open data from its own or the previous major version, so older data is upgraded one
version at a time before the new MongoDB starts; an interrupted upgrade continues where it stopped.
Database changes are applied by a one-shot `migrate` container before the API starts, so a slow
migration on an old PC cannot make the API look broken. If the update fails, the message names the
backup and the version to go back to.

### The sign-in task and keep-alive

```mermaid
flowchart TD
    A["Sign-in task: at sign-in, then every 5 min<br/>a repeat is ignored while it runs"] --> B{"Stop marker newer than this sign-in?"}
    B -->|"yes"| Z["Stay stopped"]
    B -->|"no"| C["Start the Docker engine in WSL"]
    C --> D["Start the keep-alive, compose up, wait for health"]
    D --> E{"Started?"}
    E -->|"no"| F["Log one line"]
    E -->|"yes"| G["Hold the keep-alive: sleep infinity in the WSL distro"]
    G --> H["Keep-alive ended: sleep, wsl shutdown, WSL update"]
    F --> S["Wait: 15 s, doubling up to 5 min<br/>back to 15 s after a keep-alive that held 60 s"]
    H --> S
    S --> I{"Stop marker present?"}
    I -->|"yes"| Z
    I -->|"no"| C
```

From `installer/deployer.ps1` (`Invoke-Start`, `Start-Stack`, `Invoke-Stop`) and
`installer/lib/common.ps1` (`Register-DeployerTask`, `Invoke-DeployerKeepAliveLoop`,
`Start-DeployerKeepAlive`, `Get-DeployerSignInTime`).

Windows shuts down an idle WSL distro, which would take the whole site with it, so a tiny process that
sleeps forever is kept running inside it. The sign-in task watches that process: whenever it ends
(sleep, hibernate, WSL updating itself) the stack is started again, with growing pauses while WSL is
unavailable (this loop is for the default WSL engine; with Docker Desktop the task only starts the
stack once). `deployer stop` writes a stop marker first, which is the only way out of this loop; the
task also re-runs every five minutes as a watchdog in case the loop itself died, but respects a stop
made during the current sign-in.
