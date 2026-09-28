# Cloud hosting and databases (AWS, Firebase)

Owner's request (2026-09-28): host sites **completely from the cloud**, "just like Vercel and
Supabase and not just static sites", on the user's **own** AWS and Firebase accounts, chosen per app /
per database, with the UI explaining each option - and **everything deployed to the cloud must stay
reachable when the Deployer PC is off.** All of it is also exposed through the MCP server, the docs
and the `deploy-website` skill.

| Phase | What | Status |
|---|---|---|
| **C1** | Cloud connections + hosting targets (this document, "C1 as built") | **Built** (migration `0011_cloud`) |
| C2 | Cloud databases (RDS/Aurora, DynamoDB, Firestore, Realtime Database) | Planned ("C2 - cloud databases") |
| C3 | GitHub Actions builds, so pushes deploy with the PC off | Planned ("C3 - GitHub Actions builds") |

## Principles

- **Bring your own account.** The owner connects AWS (access key of a dedicated IAM user with the
  least-privilege policy the dashboard shows, optionally assuming a role) and/or Firebase / Google Cloud
  (a service-account JSON key). Credentials are stored encrypted like other secrets, validated on save,
  never shown again, removable any time. Nothing from the Deployer authors is involved; AWS / Google
  bill the user directly, and the UI says so before a cloud target is chosen.
- **Runtime never depends on the PC.** Apps on a cloud target serve from AWS / Google and get **only
  their own environment variables**: never `DEPLOYER_URL`, `DEPLOYER_API_KEY` or `DEPLOYER_DB_*` (those
  point at the PC). The dashboard says so next to the target chooser and in the Environment card. The
  dashboard, deploys, rollbacks and settings run on the PC, so *managing* needs the PC on; *serving*
  does not.
- **Same product surface.** Cloud apps are ordinary apps in the Deploys tab: deployments, build log,
  rollback, env vars, custom domains, delete.

## C1 as built

### Cloud connections

Table `cloud_connections (id, provider aws|firebase, name, project_id NULL = every project | one
project, config_encrypted, status ok|error, status_message, created_by_id, created_at, updated_at)`.
`config_encrypted` is `encrypt_json` (MASTER_KEY, AES-256-GCM) of:

- AWS: `{access_key_id, secret_access_key, region, role_arn?, account_id, arn}`. Validation:
  `sts:GetCallerIdentity` (after `sts:AssumeRole` when `role_arn` is set). The key id must look like one
  (`AKIA`/`ASIA` + 16), the secret 40 characters, the region `xx-name-N`.
- Firebase: `{service_account: {type, project_id, private_key_id, private_key, client_email},
  project_id, region (default us-central1)}`. Validation: a JWT-bearer grant signed with the key
  (PyJWT RS256) against the fixed `https://oauth2.googleapis.com/token` - the key file's own
  `token_uri` is dropped, never used - then `GET firebase.googleapis.com/v1beta1/projects/{id}`.

The owner manages them in **Settings → Cloud accounts** (`routers/cloud.py`, `services/cloud.py`),
with step-by-step guides (StepCards): AWS - create an IAM user, create the `DeployerHosting` policy from
the JSON shown (`GET /instance/cloud/requirements`), attach it, create an access key, paste and
validate; Firebase - an explainer of the two Firebase options, create/pick the project (Blaze plan for
full apps), enable the four APIs, create a service account with the listed roles, download a JSON key,
paste and validate. A cost note heads the page.

Required permissions (`cloud.AWS_POLICY`, scoped to `deployer-*` resources where AWS allows it):
STS `GetCallerIdentity`; S3 bucket create/delete/policy/public-access-block and object put/get/delete;
CloudFront distributions, invalidations, origin access controls and functions; ACM request/describe/
delete; ECR login and repository/image operations; App Runner create/update/delete/describe/
list-operations/custom domains; IAM `GetRole`/`CreateRole`/`AttachRolePolicy`/`PassRole` on the one
role `deployer-apprunner-ecr-access`, plus the App Runner service-linked role. Google
(`cloud.GOOGLE_ROLES` / `GOOGLE_APIS`): Firebase Hosting Admin, Firebase Viewer, Cloud Run Admin,
Artifact Registry Administrator, Service Account User; APIs `firebasehosting`, `firebase`, `run`,
`artifactregistry`.

### Targets (`apps.target`)

| Target | For | Deploy sequence (after the usual clone + `docker build` on the PC) | URL | Rollback |
|---|---|---|---|---|
| `local` (default) | anything | container on the PC (DEPLOYMENTS.md) | `local_url`, Cloudflare hostnames | old image |
| `aws_static` | static preset only | build output copied out of the built image (`docker create` + `docker cp`; symlinks skipped) → private S3 bucket `deployer-<slug>-<id8>` (created once, public access blocked) under `d/<deployment_id>/`, per-file `Content-Type`, `Cache-Control` (`no-cache` for HTML, `immutable` for fingerprinted assets, 1 h otherwise) → CloudFront distribution with origin access control, a viewer-request function for directory indexes (`/docs/` → `/docs/index.html`) and 403/404 → `/index.html` (all created once) → later deploys switch the origin path and invalidate `/*` | `https://<dist>.cloudfront.net` (first rollout ~15 min) | origin path back to the old prefix + invalidation |
| `aws_app` | node / python / dockerfile / static | image → ECR repo `deployer-<slug>-<id8>` (created once; `docker login` with the `GetAuthorizationToken` password on **stdin**, into a throw-away `DOCKER_CONFIG`) → App Runner service (created once, 0.25 vCPU / 0.5 GB, access role `deployer-apprunner-ecr-access` created once per account) → later `UpdateService`; the job follows the App Runner **operation** until `SUCCEEDED` (a failed or rolled-back operation fails the deployment; the previous version keeps serving) | `https://<id>.<region>.awsapprunner.com` | `UpdateService` to the old image tag |
| `firebase_hosting` | static preset only | Hosting site `<slug>-<id8>` (created once) → version with SPA rewrite → `populateFiles` with SHA-256 of each gzipped file → upload only the hashes Hosting asks for → finalize → preview channel `d-<dep8>` (7 days, its URL in the log) → release to live | `https://<site>.web.app` | release the old version again |
| `firebase_app` | node / python / dockerfile / static | image → Artifact Registry `<region>-docker.pkg.dev/<project>/deployer/<slug>-<id8>` (repo created once; `docker login` user `oauth2accesstoken`, access token on stdin) → Cloud Run v2 service (create once, then update; the job waits for the long-running operation) → public invoker (`allUsers`, once) → Hosting release with `** → run` rewrite (once) | `https://<site>.web.app` | Cloud Run update to the old image |

Every created resource id is written to `apps.cloud_state` (JSON) the moment it exists, so a failed or
interrupted deploy never creates a second one, and teardown knows what to remove. A deployment's
`image_tag` is the cloud artifact (S3 prefix, image URI or Hosting version); `deployments.target_url`
the URL it went live on. The last 5 artifacts are kept (older S3 prefixes and ECR images are deleted;
Hosting versions and Artifact Registry images follow the providers' own retention). Environment:
the app's own variables minus names the platforms reserve (`PORT`, `K_SERVICE`, `K_REVISION`,
`K_CONFIGURATION`, `AWSAPPRUNNER*`); secrets are plain runtime environment for now (follow-up: AWS
Secrets Manager / Google Secret Manager references). Images are built for the PC's architecture (amd64
on typical PCs, which App Runner and Cloud Run need).

**Rules** (`routers/apps.py`): only project **admins** choose or change a cloud target or connection
(it is billed to that account; developers keep editing everything else and deploying); the connection
must be instance-wide or the app's project's, and of the target's provider; the static targets need
the `static` preset; `database_access`, `cohost` and `api_key_id` are refused on cloud targets (and
switched off when an app moves to one). Moving an app (target or connection) needs no running
deployment and no custom domains, enqueues `app.cloud_teardown` for the old target (or `app.remove` for
the local container), marks the live deployment superseded and forgets old artifacts (no rollback
across targets). Deleting an app enqueues the same teardown. The confirm dialogs list what will be
removed (`app.cloud.resources`); the teardown job attempts every step and fails with the list of
anything it couldn't remove - never silently. The shared App Runner access role and the shared
Artifact Registry repository are kept.

### Custom domains

`POST /apps/{id}/domains` on a cloud app (after its first deploy) asks the target for the hostname -
`aws_static`: an ACM certificate in us-east-1 (DNS validation; one custom domain per CloudFront site
for now); `aws_app`: `AssociateCustomDomain`; Firebase: a Hosting custom domain - and stores a
`domains` row (`provider` aws|firebase, `target_type` `cloud_app`, never on the tunnel, `dns_records`
JSON). Job `app.cloud_domain` then polls (up to 30 min): new records the provider asks for (validation
CNAMEs, the hostname's CNAME / A / TXT) are merged in and, **when Cloudflare is linked and one of its
zones contains the hostname**, created there as DNS-only records; otherwise the dashboard lists them to
add by hand with **Check again** (`POST .../domains/{did}/check`). Once validated: CloudFront gets the
alias + certificate, App Runner / Hosting report active, the domain turns `active` and joins `urls`.
Removing one detaches it from the target and deletes the Cloudflare records Deployer created (anything
left, e.g. a certificate still attached while CloudFront updates, comes back as `warnings`).

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/instance/cloud` | owner | – | `{connections: CloudConnection[], targets}` |
| GET | `/instance/cloud/requirements` | owner | – | `{aws: {policy}, firebase: {roles, apis}}` |
| POST | `/instance/cloud` | owner | `{provider, name, project_id?, aws?: {access_key_id, secret_access_key, region, role_arn?}, firebase?: {service_account_json, project_id?, region?}}` | `CloudConnection` (201); 422 `cloud_credentials_invalid` when the provider refuses them; audit `cloud.connection_create` (no credentials) |
| POST | `/instance/cloud/{id}/check` | owner | – | `CloudConnection` with a fresh `status` |
| DELETE | `/instance/cloud/{id}` | owner | – | `{ok}`; 409 `connection_in_use` while apps use it |
| GET | `/projects/{pid}/cloud/connections` | admin+ | – | the connections the project may use (read-only) |
| GET | `/projects/{pid}/cloud/targets` | viewer+ | – | `CloudTarget[]` (`id, label, provider, kind, for, when_pc_off, cost, uses_deployer_data, available`) |
| POST | `/projects/{pid}/apps/{id}/domains/{did}/check` | admin+ | – | `{job_id}` (cloud domains) |

`CloudConnection = {id, provider, name, project_id, status, status_message, account: {account_id,
region, role_arn, access_key_id_last4} | {project_id, region, client_email}, apps_using?, created_at,
updated_at}` - never a secret. Apps gain `target`, `cloud_connection_id` (create/PATCH) and
`cloud: {provider, connection_name, url, resources} | null`; `local_url` is null on cloud targets;
`PATCH` / `DELETE` return `teardown_job_id`; deployments gain `target_url`; domains gain `provider` and
`dns_records: [{type, name, value, created, error}]`.

### Dashboard

- **Settings → Cloud accounts** (instance owner): connected accounts (account id / project, region,
  scope, status, apps using, Check, Remove) and the two guides above.
- **New app / app Settings → "Where should this run?"**: one card per target (what it's for, "keeps
  serving when this PC is off", cost drivers), **Recommended** on the best connected target for the
  preset (static → Firebase Hosting, else AWS static; servers → App Runner, else Cloud Run), disabled
  with the reason when the preset doesn't fit or no account is connected, then the account picker and
  the environment note. API key and database-access fields are hidden for cloud targets.
- **App page**: target badge, cloud URL, "keeps running when this PC is off", rollout status while a
  deployment runs; the build log shows every cloud step (App Runner / Cloud Run status changes, the
  preview link); runtime logs point to the provider's console. Settings: domains with their DNS
  records, move / delete confirmations listing the cloud resources and following the teardown job.

### MCP

`list_cloud_connections` (service key / developer+; no secrets), `list_cloud_targets` (targets with
explanations and availability), and `get_app` / `list_apps` / `deploy_app` / `deployment_status` report
`target` and the cloud URL (`cloud_url`, `target_url`). Choosing a target stays a dashboard action for
project admins (it is billable). See MCP.md.

### Transfer (export / import)

Connections are not exported (they hold credentials). Apps keep `target` / `cloud_state` only on an
instance import where the connection exists; otherwise they come back as `local` apps.

### Not verified against real clouds

Everything above is tested against fake AWS / Google clients (`tests/test_cloud.py`) and the Google
token exchange against a mock transport; the real boto3 / REST request shapes follow the providers'
documentation but have not been run against live accounts yet.

## C2 - cloud databases (planned)

| Provider | Engine | Support |
|---|---|---|
| AWS | **RDS / Aurora** MySQL, MariaDB, PostgreSQL | create a small instance (class, storage, backups on, public access off + App Runner VPC connector) or connect existing ones; the SQL browser / query / schema / DDL export then work |
| AWS | **DynamoDB** | new NoSQL engine: tables, items, Query/Scan, schema inference, on-demand backups |
| Firebase | **Cloud Firestore** | new NoSQL engine: collections/documents, queries, schema inference, export |
| Firebase | **Realtime Database** | new engine: JSON tree browse/edit, path queries |

Seams left by C1: data sources reuse `cloud_connections` (same encryption, scope and validation);
cloud apps get their database settings through `cloud_deploy.cloud_env` (the one place a cloud app's
environment is assembled) as references to credentials the cloud injects (App Runner instance role /
Cloud Run service account, Secrets Manager / Secret Manager), never the PC's `DEPLOYER_DB_*`. MCP gains
`create_cloud_database` (service keys; billable, requires `confirm_billing: true`) and the data tools
work on the new engines.

## C3 - GitHub Actions builds (planned)

Each cloud app picks where it builds: *This PC* (C1, the worker builds, pushes and rolls out) or
*GitHub Actions* (Deployer commits a workflow that builds and deploys on every push with GitHub OIDC →
AWS role / Google workload identity, so pushes deploy even when the PC is off). Seams left by C1:
`cloud_deploy.go_live` publishes from an artifact reference (the same path rollbacks use), so a
workflow that pushes the image / uploads the site only needs the rollout half; `apps.cloud_state` holds
the ids the workflow needs; the role / identity provider joins `cloud.AWS_POLICY` and the Google roles.
