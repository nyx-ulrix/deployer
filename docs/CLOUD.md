# Cloud hosting and databases (AWS, Firebase)

Owner's request (2026-09-28): host sites **completely from the cloud**, "just like Vercel and
Supabase and not just static sites", on the user's **own** AWS and Firebase accounts, chosen per app /
per database, with the UI explaining each option - and **everything deployed to the cloud must stay
reachable when the Deployer PC is off.** All of it is also exposed through the MCP server, the docs
and the `deploy-website` skill.

| Phase | What | Status |
|---|---|---|
| **C1** | Cloud connections + hosting targets (this document, "C1 as built") | **Built** (migration `0011_cloud`) |
| **C2-1** | Cloud database groundwork + AWS RDS / Aurora ("C2-1 as built") | **Built** (migration `0013_cloud_databases`) |
| **C2-2** | DynamoDB engine ("C2-2 as built") | **Built** (no migration) |
| **C2-3** | Cloud Firestore engine ("C2-3 as built") | **Built** (no migration) |
| **C2-4** | Firebase Realtime Database engine ("C2-4 as built") | **Built** (no migration) |
| **Firestore backups** | New Firestore databases, managed exports to Cloud Storage and imports, scheduled backups and restores ("Firestore backups as built") | **Built** (no migration) |
| **C2-5** | MCP roles, data tools on every cloud engine, transfer, project delete keep / delete ("C2-5 as built") | **Built** (no migration) |
| **C3** | GitHub Actions builds with OIDC, so pushes deploy with the PC off ("C3 as built") | **Built** (no migration) |
| **Delete over API / MCP** | Deleting a cloud database with an admin's session or a service key, MCP `delete_cloud_database` ("Deleting a cloud database over the API and MCP") | **Built** (no migration) |
| **DynamoDB recovery** | Point-in-time recovery per table and restores of a backup / point in time into a new table and data source ("C2-2 as built": "Point-in-time recovery and restores") | **Built** (no migration) |
| **Polish** | Billing confirmation for putting an app on a cloud target, MCP `set_app_target` ("C1 as built": Rules, MCP) | **Built** (no migration) |
| **G1** | App secrets in AWS Secrets Manager / Google Secret Manager (opt-in), environment changes reaching App Runner / Cloud Run apps at once ("G1 as built") | **Built** (no migration) |
| **G3** | Permissions boundary `deployer-boundary` on every IAM role Deployer creates ("G3 as built") | **Built** (no migration) |
| **Firestore recovery** | Firestore point-in-time recovery, restoring to a time into a new database, deleting Firestore databases, backups and exports ("Firestore point-in-time recovery and deletes") | **Built** (no migration) |

## Principles

- **Bring your own account.** The owner connects AWS (access key of a dedicated IAM user with the
  least-privilege policy the dashboard shows, optionally assuming a role) and/or Firebase / Google Cloud
  (a service-account JSON key). Credentials are stored encrypted like other secrets, validated on save,
  never shown again, removable any time. Nothing from the Deployer authors is involved; AWS / Google
  bill the user directly, and the UI says so before a cloud target is chosen.
- **Runtime never depends on the PC.** Apps on a cloud target serve from AWS / Google and get **only
  their own environment variables**: never `DEPLOYER_URL`, `DEPLOYER_API_KEY` or this PC's databases
  (those point at the PC). The one addition: an App Runner app with database access gets
  `DEPLOYER_DB_<NAME>_*` for the project's databases **in the same AWS account** (C2-1, C2-2), which point at
  AWS, and a Cloud Run app with database access the project's Firestore databases **in the same Firebase
  project** (C2-3) and its Realtime Databases (C2-4). The dashboard says so next to the target chooser and in the Environment card. The
  dashboard, deploys, rollbacks and settings run on the PC, so *managing* needs the PC on; *serving*
  does not - and with GitHub Actions builds (C3) neither does *deploying a push*.
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
with step-by-step guides (StepCards): AWS - create an IAM user, create the managed policies `DeployerHosting`,
`DeployerDatabases` and `DeployerRoles` from the JSON shown (`GET /instance/cloud/requirements`; one policy
no longer fits IAM's size limit, see "AWS policy split as built"), attach them, create an access key, paste
and validate; Firebase - an explainer of the two Firebase options, create/pick the project (Blaze plan for
full apps), enable the four APIs, create a service account with the listed roles, download a JSON key,
paste and validate. A cost note heads the page.

Required permissions (C1's part of `cloud.AWS_POLICIES`, scoped to `deployer-*` resources where AWS allows it):
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
`K_CONFIGURATION`, `AWSAPPRUNNER*`); secrets are plain runtime environment unless the app keeps them in the account's secret
store ("G1 as built"). Images are built for the PC's architecture (amd64
on typical PCs, which App Runner and Cloud Run need).

**Rules** (`routers/apps.py`): only project **admins** choose or change a cloud target or connection
(it is billed to that account; developers keep editing everything else and deploying); putting an app on a
cloud target or another connection needs **`confirm_billing: true`** on `POST` / `PATCH .../apps` (`422
billing_not_confirmed` with the target's cost note otherwise; the form's target chooser has the tick); the connection
must be instance-wide or the app's project's, and of the target's provider; the static targets need
the `static` preset; `database_access`, `cohost` and `api_key_id` are refused on cloud targets (and
switched off when an app moves to one) - except `database_access` on `aws_app`, which since C2-1 means the
project's AWS databases, and on `firebase_app`, which since C2-3 / C2-4 means the project's Firestore and Realtime
Databases. Moving an app (target or connection) needs no running
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
| GET | `/instance/cloud/requirements` | owner | – | `{aws: {policies: [{name, for, document}], boundary, boundary_name}, firebase: {roles, apis}}` |
| POST | `/instance/cloud` | owner | `{provider, name, project_id?, aws?: {access_key_id, secret_access_key, region, role_arn?}, firebase?: {service_account_json, project_id?, region?}}` | `CloudConnection` (201); 422 `cloud_credentials_invalid` when the provider refuses them; audit `cloud.connection_create` (no credentials) |
| POST | `/instance/cloud/{id}/check` | owner | – | `CloudConnection` with a fresh `status` |
| DELETE | `/instance/cloud/{id}` | owner | – | `{ok}`; 409 `connection_in_use` while apps use it |
| GET | `/projects/{pid}/cloud/connections` | admin+ | – | the connections the project may use (read-only) |
| GET | `/projects/{pid}/cloud/targets` | viewer+ | – | `CloudTarget[]` (`id, label, provider, kind, for, when_pc_off, cost, uses_deployer_data, available`) |
| POST | `/projects/{pid}/apps/{id}/domains/{did}/check` | admin+ | – | `{job_id}` (cloud domains) |

`CloudConnection = {id, provider, name, project_id, status, status_message, account: {account_id,
region, role_arn, access_key_id_last4} | {project_id, region, client_email}, apps_using?, created_at,
updated_at}` - never a secret. Apps gain `target`, `cloud_connection_id` (create/PATCH, plus `confirm_billing:
true` when the app moves onto a cloud target or connection) and
`cloud: {provider, connection_name, url, resources} | null`; `local_url` is null on cloud targets;
`PATCH` / `DELETE` return `teardown_job_id`; deployments gain `target_url`; domains gain `provider` and
`dns_records: [{type, name, value, created, error}]`.

### Dashboard

- **Settings → Cloud accounts** (instance owner): connected accounts (account id / project, region,
  scope, status, apps using, Check, Remove) and the two guides above.
- **New app / app Settings → "Where should this run?"**: one card per target (what it's for, "keeps
  serving when this PC is off", cost drivers), **Recommended** on the best connected target for the
  preset (static → Firebase Hosting, else AWS static; servers → App Runner, else Cloud Run), disabled
  with the reason when the preset doesn't fit or no account is connected, then the account picker,
  the environment note and, when the app moves onto a cloud target or account, the tick *I understand AWS /
  Google charges this cloud account for it* with the target's cost. API key and database-access fields are hidden for cloud targets.
- **App page**: target badge, cloud URL, "keeps running when this PC is off", rollout status while a
  deployment runs; the build log shows every cloud step (App Runner / Cloud Run status changes, the
  preview link); runtime logs point to the provider's console. Settings: domains with their DNS
  records, move / delete confirmations listing the cloud resources and following the teardown job.

### MCP

`list_cloud_connections` (project admin, like its route - C2-5; no secrets), `list_cloud_targets` (targets with
explanations and availability), and `get_app` / `list_apps` / `deploy_app` / `deployment_status` report
`target` and the cloud URL (`cloud_url`, `target_url`). `set_app_target` (project admin, like changing it in the
dashboard; `app_id`, `target`, `connection_id`, `confirm_billing`, `confirm_teardown`) moves an app between this PC
and a cloud target: a cloud target needs `confirm_billing: true`, and moving an app off a cloud target where it has
resources answers `teardown_not_confirmed` with the list until `confirm_teardown: true`. See MCP.md.

### Transfer (export / import)

Connections are not exported (they hold credentials). Apps keep `target` / `cloud_state` only on an
instance import where the connection exists; otherwise they come back as `local` apps. Cloud databases: "C2-5 as built".

### Not verified against real clouds

Everything above is tested against fake AWS / Google clients (`tests/test_cloud.py`) and the Google
token exchange against a mock transport; the real boto3 / REST request shapes follow the providers'
documentation but have not been run against live accounts yet.

## C2-1 as built: cloud databases in AWS (RDS / Aurora)

### Data model

A cloud database is an ordinary **`external`** data source - so the SQL browser, query console, schema,
DDL export and the data API work through the normal external-source path - with two new columns
(migration `0013`): `data_sources.cloud_connection_id` (FK `cloud_connections`, `SET NULL`) and
`cloud_state` (JSON, never secrets). `status` gains `creating`. `config_encrypted` holds the usual
`{host, port, username, password, database, tls: true, tls_verify: false}` (`encrypt_json`; `tls_verify:
false` only matters for an endpoint the RDS CA bundle does not cover, see "Networking"); the
password is shown only through `GET .../data-sources/{id}/connection` (developer+, audited), like every
other source. `cloud_state`:

- connected: `{provider: aws, service: rds, created: false, instance_id | cluster_id, region, vpc_id,
  group_ids, port}`;
- created: `{provider, service, created: true, instance_id, region, instance_class, storage_gb, port,
  job_id, vpc_id, group_id, allowed_ip, instance_requested}` - each id written the moment it exists, so
  an interrupted job never creates a second resource.

A connection with databases on it cannot be removed (`409 connection_in_use`). Export / import: the
cloud link survives only an instance import where the connection exists; a project copy never owns
(and so never deletes) the original's instance - it stays a plain external connection.

### Where a database can live (Add database)

The **Add database** dialog asks *Where should it live?* with four cards, each with one plain sentence on
what it means, what happens when the PC is off and the cost (`GET /projects/{id}/cloud/databases/options`,
also the MCP tool `cloud_database_options`): **On this PC** (managed), **On another PC or server**
(external), **In your AWS account** (RDS for SQL, below; DynamoDB for NoSQL, "C2-2"), **In your Firebase
project** (NoSQL: Firestore, "C2-3", and the Realtime Database, "C2-4"). In AWS the user picks the account (the project's AWS connections) and:

- **Connect one you already have**: `GET .../cloud/connections/{cid}/databases` lists the region's RDS
  instances (not part of a cluster) and Aurora / RDS clusters (`rds:DescribeDBInstances`,
  `DescribeDBClusters`) with the reason Deployer can't use one (`problem`: unsupported engine - only
  MySQL, MariaDB, PostgreSQL and their Aurora versions - or not publicly accessible) and this PC's public
  IP. The user enters the database login; Deployer tests it over TLS and stores it. **It never changes
  that instance or its firewall**: the user allows this PC's IP in the instance's security group (the
  error says which IP), and removing it only forgets the connection.
- **Create a new database** (billable: the dialog shows the cost note and needs a ticked *I understand
  AWS charges my account*; the API needs `confirm_billing: true`, else `422 billing_not_confirmed`):
  engine MySQL / MariaDB / PostgreSQL (newest version AWS offers), size `db.t4g.micro` (default),
  `db.t4g.small` or `db.t4g.medium`, 20 GB gp3, automated backups kept 7 days, deletion protection on,
  storage encrypted, single AZ, master user `deployer` with a random 32-character password
  (`secrets.token_urlsafe`, stored encrypted, never logged), first database named after the source.
  Job `data_source.cloud_create` (progress on the card and in Activity): default VPC of the region
  (none: a plain error saying how to create one) -> security group `deployer-db-<id8>` tagged
  `managed-by=deployer` -> ingress from this PC's public IP (`checkip.amazonaws.com`) ->
  `CreateDBInstance` (`deployer-<name>-<id8>`, publicly accessible, in that group) -> waits for
  `available` (up to 45 min) -> `ALTER USER 'deployer'@'%' REQUIRE SSL` on MySQL / MariaDB (RDS for
  PostgreSQL 15+ already forces TLS with `rds.force_ssl=1`) -> connection test -> `ok`. A failure leaves
  the source in `error` with the reason and everything created recorded, so **Remove** cleans it up.

Deleting a created database (typing its name in the dialog, which lists what goes) queues
`data_source.cloud_delete` and removes the source at once: deletion protection off ->
`DeleteDBInstance` with a **final snapshot** `<instance>-final-<UTC yyyymmddHHMM>` (kept, billed for
storage until the user deletes it; automated backups go with the instance) -> waits until it is gone ->
deletes the security group (retried for up to 10 minutes while the old instance's network interface
still holds it). Anything it could not remove fails the job with the list. Deleting is refused while the
database is still being created. Deleting a **project** that still has databases Deployer created in AWS or apps with
cloud resources asks what to do with them (C2-5, "Deleting a project"), so nothing is left running and
billed without the owner choosing it.

### Networking (the trade-off)

Requirement: this PC must browse / query the database **and** App Runner apps must reach it, with the
PC off for the apps. Design:

- **The PC** connects to a *publicly accessible* endpoint whose security group lets in only the PC's
  current public IP `/32`. The scheduler checks the IP every 5 minutes (`cloud_db.refresh_pc_ips`, also
  on **Check status**): when it changed, the new IP is allowed and the old one revoked. Connections use
  TLS and **verify the server**: RDS signs with Amazon's own CA, which is not in the system store, so the
  API image ships AWS's global RDS CA bundle (`api/app/certs/rds-global-bundle.pem`, vendored from
  `https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem`; refresh by downloading that URL over
  it) and every TLS connection to an RDS / Aurora endpoint (`<name>.<id>.<region>.rds.amazonaws.com`,
  cluster endpoints included - created, connected or added by hand as an external database) trusts only
  that bundle and checks the host name: PyMySQL gets an `ssl` context with that CA file,
  `CERT_REQUIRED` and `check_hostname`; psycopg gets `sslmode=verify-full` and `sslrootcert` (the SQL
  browser, query console, schema / DDL, data API, connection tests and the `REQUIRE SSL` step all connect
  this way, `connections._connect_args`). A certificate that does not verify fails with a plain hint
  (use the endpoint AWS shows; the instance must be on a current CA such as `rds-ca-rsa2048-g1`). Other
  external databases keep their settings; RDS Proxy endpoints (a public certificate, in the system
  store) and GovCloud / China endpoints (other bundles) keep the old encrypted-but-unverified mode.
- **App Runner apps** reach it privately: an App Runner **VPC connector** `deployer-<vpc-id>` (one per
  VPC, created once, shared, free) with its own security group `deployer-apprunner-<vpc-id>`, which the
  database's group lets in on the database port. Apps without database access keep App Runner's default
  egress.
- Trade-offs, shown in the dialog and the app form: the endpoint is on the internet (only the PC's IP
  gets through the firewall, the password is long and random, TLS is required); while the PC's IP
  changes, the PC is locked out for up to 5 minutes; **an App Runner app linked to a database sends all
  its outgoing traffic through the VPC**, which has no internet route by default, so an app that also
  calls other internet services needs a NAT gateway (about US$32/month) - Deployer does not create one.
  The alternatives were worse for this audience: a private-only database needs a bastion or VPN for the
  PC, and opening the database to App Runner's public egress would mean `0.0.0.0/0`.

### Apps

On `aws_app`, **database access** is allowed (admins, as on the PC) and means *the project's databases
in the same AWS connection* (so the same account and region). `cloud_deploy.cloud_env` adds
`DEPLOYER_DB_<NAME>_{HOST,PORT,USER,PASSWORD,DATABASE,URL}` (URL with `ssl=true` / `sslmode=require`)
before the app's own variables (which win); they go to App Runner as its runtime environment (stored
encrypted by App Runner, or as Secrets Manager references when the app opted in, "G1 as built"). For an RDS endpoint the bundle covers
it also adds `DEPLOYER_DB_<NAME>_SSL_CA_URL` (the RDS CA bundle's URL above). The URL stays
`sslmode=require` (encrypted, works with no CA file); to also verify the server, as Deployer does, the
app fetches that bundle (e.g. in its Dockerfile: `ADD https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/rds-ca.pem`)
and connects with it: PostgreSQL `sslmode=verify-full&sslrootcert=/etc/ssl/rds-ca.pem`; MySQL / MariaDB
the driver's CA option (Node `ssl: { ca: fs.readFileSync("/etc/ssl/rds-ca.pem") }`, PyMySQL
`ssl={"ca": "/etc/ssl/rds-ca.pem"}`, `mysql` CLI `--ssl-ca=... --ssl-verify-server-cert`). The deploy then ensures the VPC
connector, lets its security group into each created database's group, and creates / updates the
service with `EgressType: VPC` (back to `DEFAULT` once database access is off). A connected (not
created) database's firewall is the user's: the build log names the connector's security group to
allow. A database still `creating`, in another account or in another VPC is skipped with a log line.
Other cloud targets still refuse database access. Moving an app to `aws_app` keeps its database-access
switch.

### Permissions added (now in the `DeployerDatabases` policy, shown in Settings -> Cloud accounts)

`rds:DescribeDBInstances`, `rds:DescribeDBClusters`, `ec2:DescribeVpcs`, `ec2:DescribeSubnets`,
`ec2:DescribeSecurityGroups` (read, `*`); `rds:CreateDBInstance`, `ModifyDBInstance`, `DeleteDBInstance`,
`CreateDBSnapshot`, `AddTagsToResource` on `db:deployer-*` and `snapshot:deployer-*` (plus the default
subnet / parameter / option groups a new instance uses); `ec2:CreateSecurityGroup`; `ec2:CreateTags` only
while creating a security group; `ec2:AuthorizeSecurityGroupIngress`, `RevokeSecurityGroupIngress`,
`DeleteSecurityGroup` only on groups tagged `managed-by=deployer`; `apprunner:CreateVpcConnector`,
`ListVpcConnectors`; the service-linked roles of RDS and App Runner networking. Owners who attached the
C1 policy paste the new one over it (the guide says so).

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| GET | `/projects/{pid}/cloud/databases/options` | viewer+ | – | `{locations: [{id, label, what, when_pc_off, cost, available?, note?}], aws: {engines, instance_classes, default_instance_class, storage_gb, backup_days, cost, network}}` |
| GET | `/projects/{pid}/cloud/connections/{cid}/databases` | admin+ | – | `{region, pc_ip, databases: [{id, kind, engine, deployer_engine, status, host, port, public, vpc_id, security_groups, database, username, problem}]}` |
| POST | `/projects/{pid}/cloud/databases` | admin+ | `{connection_id, name, engine (mysql, mariadb, postgresql), instance_class?, confirm_billing: true}` | `{data_source, job}` (201); audit `data_source.create` with `cloud: create` |
| POST | `/projects/{pid}/cloud/databases/connect` | admin+ | `{connection_id, name, resource_id, username, password?, database?}` | `DataSource` (201); `400 connection_failed` names this PC's IP to allow |

Data sources gain `cloud: {provider, connection_id, connection_name, service, created, resource_id,
resource_kind, region, instance_class, allowed_ip, job_id, resources, when_pc_off} | null`; `allowed_ip` (this
PC's public IP) is null for members below admin. `PATCH .../data-sources/{id}` of a created one may rename it or
change its user, password, database and TLS, but answers 422 to a new host or port.
`DELETE .../data-sources/{id}` of a created one returns `{ok, job}` (`data_source.cloud_delete`), and
`409 cloud_database_creating` while it is being created; the connection details and data routes answer
`409 cloud_database_creating` until it is ready.

### MCP

`cloud_database_options`, `list_cloud_databases` (`connection_id`), `create_cloud_database`
(`connection_id, name, engine, instance_class?, confirm_billing` - billable: the tool description tells
the agent to get the user's agreement first; `confirm_billing: false` returns `billing_not_confirmed`),
`connect_cloud_database`; `list_data_sources` adds `cloud` for cloud databases. Like their REST routes, the
account tools need a project **admin** (C2-5: an admin's session, not a service key). Deleting a cloud
database: `delete_cloud_database` (an admin's session or a service key, with the database's name typed;
"Deleting a cloud database over the API and MCP").

### Not verified against real clouds

Tested against a fake AWS client (`tests/test_cloud_db.py`: create sequence and parameters, billing
confirmation, IP refresh, delete with snapshot and failure report, connect, App Runner env + connector,
MCP, migration). Not yet run against a live account: the RDS / EC2 / App Runner VPC connector request
shapes, whether App Runner accepts every default-VPC subnet for a connector (some AZs are unsupported in
a few regions), the `ALTER USER ... REQUIRE SSL` step on RDS, and the time AWS takes.
Certificate verification is tested by capturing what reaches the drivers (`tests/test_rds_tls.py`: the
PyMySQL context trusts exactly the vendored bundle's CAs with `CERT_REQUIRED` + `check_hostname`, psycopg
gets `verify-full` + `sslrootcert`, other hosts unchanged, the app's `SSL_CA_URL`, the hint); no TLS
handshake with a real RDS instance has been made with it yet (instance vs. cluster vs. reader endpoint
host names, MariaDB on RDS).

## C2-2 as built: DynamoDB

### Data model

A DynamoDB database is an `external` data source with `kind: nosql`, `engine: dynamodb` on an AWS cloud
connection: **one or more tables** of the connection's region. No migration: `cloud_state` holds
`{provider: aws, service: dynamodb, created, tables: [...], region}` (created ones add `keys: [{name, type}]`,
`job_id`, `table_requested`), and `config_encrypted` is `{}` - the source has **no secret of its own**;
every call is made with the connection's key (`cloud_aws.AwsClient.ddb`, one generic method named after
the AWS operation, which is the seam the tests fake). A source only ever reaches **its own tables**
(`404` for any other table name, also in the query console), so the project's API keys cannot read the
account's other tables. It reuses the MongoDB seams (`kind: nosql`): the documents endpoints, the data
browser's documents view, the MongoDB-shaped console answer, schema entities of type `collection` -
`services/dynamo.py` is the adapter, branched on `engine` in `source_ops`, `introspection`,
`query_console`, `ddl_export` and `connections`.

- **Items are plain JSON both ways**: numbers as numbers (DynamoDB keeps them exact; floats are sent as
  their decimal text), binary as `{"$base64": "..."}`, string / number / binary **sets** as
  `{"$set": [...]}` (so editing an item keeps a set a set), `null`, booleans, lists and maps as themselves.
- **An item's id** (`{doc_id}` of the documents endpoints, the browser's edit / delete) is its key as JSON,
  `{"customer": "c1", "n": 2}`, or for a table with only a partition key its plain value (`u1`).

### Add database -> In your AWS account -> NoSQL

The dialog first says in one paragraph what DynamoDB is (items found by a key you choose, no server to run,
used with the AWS SDK, not SQL), then the same two choices as RDS:

- **Create a new table** (billable: cost note + ticked box; API `engine: "dynamodb"`, `confirm_billing:
  true`): a **partition key** (default a text `id`; plain hint: "the field every item is found by") and an
  optional **sort key** (text, number or binary). Job `data_source.cloud_create`: `CreateTable`
  `deployer-<name>-<id8>` with **on-demand billing** (`PAY_PER_REQUEST`: pay per read / write, nothing to
  size), **deletion protection** on, tagged `managed-by=deployer` -> waits for `ACTIVE` (seconds) -> `ok`.
  A retried job never creates a second table (`table_requested`, `ResourceInUseException` is fine).
- **Connect tables you already have**: `ListTables` of the region (also listed with the RDS databases by
  `GET .../cloud/connections/{cid}/databases` as `tables`, or `tables_problem` when the AWS user's policy
  predates DynamoDB), tick one or more; each must answer `DescribeTable`. Deployer only reads and writes
  their items and takes backups; removing the source never touches the tables.

Deleting a **created** table (typing its name; the dialog lists it) queues `data_source.cloud_delete`:
deletion protection off -> `CreateBackup` `<table>-final-<UTC yyyymmddHHMM>` -> waits until it is
`AVAILABLE` -> `DeleteTable`. The final backup stays in the account (billed for storage until the user
deletes it in the DynamoDB console). A project with created tables cannot be deleted (C2-1's rule).

### Browsing, editing, querying

- **Data tab** (the same documents view as MongoDB, labelled *items* / *tables*): pages with
  **`cursor`** (`next_cursor` of the previous page; DynamoDB's `LastEvaluatedKey`, opaque) instead of
  `skip`; the filter box takes **equality** filters (`{"status": "open"}`); naming the partition key (and
  the sort key) runs a `Query` on that partition, anything else a `Scan` with a filter (DynamoDB applies
  `Limit` before the filter, so up to 5 pages are read to fill one). `total` is the table's own
  `ItemCount` (AWS refreshes it about every 6 hours) and `null` with a filter; `key` lists the key
  attributes. Insert needs the key (`400 missing_key`; an existing key is `409 document_exists` - no
  silent overwrite), edit can't change the key (`400 immutable_field`) and sends `UpdateItem` SET / REMOVE
  with a condition that the item exists (`404 document_not_found`), delete likewise. Tables are not
  created or dropped from the Data tab (`400 not_supported`: add a database, or use the AWS console).
- **Query console**: one JSON request, AWS's own parameter names with plain JSON values (QUERY_CONSOLE.md
  "DynamoDB"); viewers may only `Query`, `Scan` and `GetItem` (`403 read_only_role`), developers also
  `PutItem`, `UpdateItem`, `DeleteItem`. The answer has the MongoDB console's shape (`result`,
  `result_docs`, `output`, in-band `error`), so the notebook / terminal show it unchanged.
- **Schema**: per table, the key attributes first (primary key; the partition key alone is `unique` when
  there is no sort key), the other fields inferred from a sampled `Scan` (types `string`, `int`,
  `double`, `bool`, `binData`, `array` for sets and lists, `object` for maps), indexes = the primary key
  plus global / local secondary indexes, `row_count` = `ItemCount`. The naming checks skip table names
  (they are AWS resource names). The schema export writes each table's `CreateTable` input as comments.
- **Connection details** show the region, endpoint and tables - there is no URI, user or password.

### Backups (Backups tab)

DynamoDB databases get an **AWS backups** card instead of the "up to their provider" note: the tables'
on-demand backups (`ListBackups`, newest first, including ones made in the AWS console) and **Back up now**
(admin; billable, so a cost note and a ticked box; `CreateBackup` `<table>-<UTC yyyymmddHHMMSS>` of every
table or one).

### Point-in-time recovery and restores (Backups tab)

- **Point-in-time recovery** per table, **off unless the admin turns it on**: the card lists each table with
  on / off and, when on, the window it can be restored to (`DescribeContinuousBackups`:
  `EarliestRestorableDateTime` - `LatestRestorableDateTime`, 35 days); a table AWS refuses to describe (an
  owner who has not pasted the new policy yet) shows the reason instead. **Turn on** is billable (about US$0.20
  per GB of table per month; the dialog shows the note and needs the tick; API `confirm_billing: true`, else
  `422 billing_not_confirmed`); **Turn off** says the window is deleted and needs no tick
  (`UpdateContinuousBackups` either way; audit `data_source.cloud_pitr`).
- **Restore** (admin; billable: about US$0.15 per GB restored, then the new table's storage, so a cost note +
  tick / `confirm_billing: true`): an AVAILABLE on-demand backup (**Restore** on its row) or a table with
  point-in-time recovery on (**Restore to a time**: the latest restorable time, or a date and time in the
  window, in the viewer's time zone) goes into a **new table**, never over the original. The request is checked
  first: the backup must be of one of the source's own tables (`DescribeBackup`: `404` otherwise, `409
  backup_not_ready` while AWS makes it), point-in-time recovery must be on (`409 pitr_not_enabled`) and the time
  inside the window (`400 invalid_restore_time`). It then creates a **new data source** (the name the admin
  typed; `created: true`, `cloud.restored_from: {kind, table, backup | time | latest, source_id,
  source_name}`) with the table `deployer-<name>-<id8>` and queues **`data_source.cloud_restore`** (progress in
  the dialog, on the database's card and in Activity): `RestoreTableFromBackup` / `RestoreTableToPointInTime`
  with `BillingModeOverride: PAY_PER_REQUEST` -> waits for `ACTIVE` with no restore in progress (minutes to
  hours, up to 12 h) -> `TagResource` `managed-by=deployer` and deletion protection on (restores take neither) ->
  `ok`. A retried job never asks twice (`table_requested`; `TableAlreadyExistsException` is fine). From then on
  it is a created DynamoDB table like any other: removing it deletes only the new table after a final backup,
  and the project's delete asks about it. The restored table has point-in-time recovery off and no
  auto scaling / stream / TTL settings of the original (AWS does not copy them).

### Apps on App Runner

`database_access` on an `aws_app` now also means the project's DynamoDB databases on the same connection:

- `DEPLOYER_DB_<NAME>_TABLE` (the first table), `_TABLES` (comma-separated), `_REGION` and `_DATABASE` -
  **no credentials**.
- An **instance role** `deployer-app-<slug>-<id8>` (created on the first deploy that needs it, trust
  `tasks.apprunner.amazonaws.com`, tagged) with one inline policy `deployer-databases` allowing
  `GetItem`, `BatchGetItem`, `Query`, `Scan`, `PutItem`, `UpdateItem`, `DeleteItem`, `BatchWriteItem`,
  `ConditionCheckItem`, `DescribeTable` on **exactly those tables' ARNs** (and their indexes); the service
  runs as it (`InstanceConfiguration.InstanceRoleArn`), so the AWS SDK in the app finds credentials by
  itself. Database access off: the policy is removed (the role stays, allowed nothing). The app's
  teardown deletes the role; the delete dialog lists it.
- DynamoDB is reached over AWS's own endpoint, so it needs no VPC connector. When the app also has an RDS
  database (its traffic then goes through the VPC), the deploy adds a free **DynamoDB gateway endpoint**
  to that VPC's route tables (created once, shared, kept), so the tables stay reachable without a NAT.

### Permissions added (now in the `DeployerDatabases` policy)

`dynamodb:ListTables`, `ListBackups` (`*`: AWS has no resource-level permissions for them);
`DescribeTable`, `GetItem`, `Query`, `Scan`, `PutItem`, `UpdateItem`, `DeleteItem`, `CreateBackup`,
`DescribeBackup` on `table/*` and `table/*/backup/*` - any
table, because connected tables keep their own names (a source still only uses its own); `CreateTable`,
`UpdateTable`, `DeleteTable`, `TagResource` only on `table/deployer-*`; `iam:GetRole`, `CreateRole`,
`TagRole`, `PutRolePolicy`, `DeleteRolePolicy`, `DeleteRole`, `PassRole` only on `role/deployer-app-*`;
`ec2:DescribeVpcEndpoints`, `DescribeRouteTables` (read) and `ec2:CreateVpcEndpoint` + `CreateTags` (only
while creating an endpoint) for the gateway endpoint. (The role statement is now in `DeployerRoles`, the rest in
`DeployerDatabases`; see "AWS policy split as built".)

Point-in-time recovery and restores add `DescribeContinuousBackups`, `UpdateContinuousBackups`,
`RestoreTableFromBackup`, `RestoreTableToPointInTime` on `table/*` and `table/*/backup/*` (the source table and
backup keep their own names) and `BatchWriteItem` only on `table/deployer-*` (AWS requires the item write
permissions on the restore's target table; the other write actions are already allowed). The new table itself
is always `deployer-*`.

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/projects/{pid}/cloud/databases` | admin+ | `{connection_id, name, engine: "dynamodb", partition_key?: {name, type: S\|N\|B}, sort_key?, confirm_billing: true}` | `{data_source, job}` (201) |
| POST | `/projects/{pid}/cloud/databases/connect` | admin+ | `{connection_id, name, tables: [...]}` | `DataSource` (201); `400 connection_failed` names the table AWS refused |
| GET | `/projects/{pid}/data-sources/{sid}/cloud-backups` | viewer+ | – | `{backups: [{table, arn, name, status, type, size_bytes, created_at}], pitr: [{table, status ENABLED\|DISABLED\|null, earliest, latest, days, problem}], cost, pitr_cost, restore, restore_cost}` |
| POST | `/projects/{pid}/data-sources/{sid}/cloud-backups` | admin+ | `{table?, confirm_billing: true}` | `{backups}` (201); audit `data_source.cloud_backup` |
| PUT | `/projects/{pid}/data-sources/{sid}/cloud-backups/pitr` | admin+ | `{table, enabled, confirm_billing (true to switch on)}` | the table's `pitr` entry; audit `data_source.cloud_pitr` |
| POST | `/projects/{pid}/data-sources/{sid}/cloud-backups/restore` | admin+ | `{name, backup_arn}` or `{name, table, point_in_time (ISO, UTC without a zone) \| latest: true}`, plus `confirm_billing: true` | `{data_source, job}` (201, the new source `creating`); `404` / `409 backup_not_ready` / `409 pitr_not_enabled` / `400 invalid_restore_time`; audit `data_source.create` with `cloud: restore` |
| GET | `/projects/{pid}/data-sources/{sid}/collections/{table}/documents` | viewer+ / API keys | `filter?`, `limit`, `cursor?` | `{documents, total, key, next_cursor}` |

`GET .../cloud/databases/options` adds `dynamodb: {what, keys, key_types, cost, network}`; the
listing adds `tables` and `tables_problem`; data sources' `cloud` adds `tables` and `resource_kind:
"table"`. Editing a DynamoDB source's connection settings is refused (rename only).

### MCP

`create_cloud_database` takes `engine: "dynamodb"` with `partition_key` / `sort_key`,
`connect_cloud_database` takes `tables`, `list_cloud_databases` returns `tables`, `list_documents` takes
`cursor`, `run_query` takes the JSON request, plus `list_cloud_backups` (any key; with `pitr`),
`create_cloud_backup`, `set_point_in_time_recovery` and `restore_cloud_backup` (project admin since C2-5;
billable, `confirm_billing` - switching point-in-time recovery off needs none). See MCP.md.

### Not verified against real clouds

Tested against an in-memory DynamoDB behind the `ddb` seam (`tests/test_dynamo.py`: create / delete with
a final backup, connect, paging, Query vs Scan, insert / update / delete, value round trips, the console
and its read-only rule, schema, backups, the App Runner role and gateway endpoint, MCP, policy size). Not
yet run against a live account: the exact request shapes (botocore validates parameters, the fake does
not), App Runner taking the instance role on an existing service, and the gateway endpoint on default
VPCs.

Point-in-time recovery and restores (`tests/test_dynamo_restore.py`): on / off with the billing rule, the
window, an older policy's refusal; restoring a backup and a point in time / the latest time into a new source,
the checks (another table's backup, recovery off, a time outside the window, both or neither of backup / table),
the retried job, deleting the copy, MCP and the policy against the in-memory fake; and the whole flow (list, on,
both restores with their jobs) through the **real `AwsClient.ddb` with botocore's `Stubber`**, so every request
and canned response is checked against botocore's DynamoDB model; the dialogs in `CloudBackups.test.tsx`. Not yet
run against a live account: which resource ARN AWS checks the restore actions and the item writes against (the
policy grants the documented set; a refusal fails the job with AWS's message and the source stays in `error`
for Remove), how long real restores take, and `TagResource` / `UpdateTable` straight after a restore reaches
`ACTIVE`.

## C2-3 as built: Cloud Firestore

### Data model

A Firestore database is an `external` data source with `kind: nosql`, `engine: firestore` on a **Firebase**
cloud connection: **one Firestore database** of the connection's Google project - `(default)` or a named
one. No migration: `cloud_state` holds `{provider: firebase, service: firestore, created: false, database,
project_id, location}` and `config_encrypted` is `{}` - like DynamoDB, the source has **no secret of its
own**; every call is a Firestore REST v1 request (`https://firestore.googleapis.com/v1/projects/<project>/
databases/<id>/...`) signed with the connection's service-account token (the existing PyJWT flow, no Google
SDK). `cloud_gcp.GcpClient.firestore(method, path, body, params)` is the one seam: it only accepts paths
under `databases/...` (each id percent-encoded, so `:` or `#` in an id never becomes a REST method) and
the token only ever goes to `firestore.googleapis.com`. Access tokens are now cached per key for their
hour (every request builds a client, so this saves a token exchange per call). `services/firestore.py` is
the adapter, reached through `connections.cloud_engine(engine)` - the same function names as
`services/dynamo.py`, so `source_ops`, `introspection`, `query_console`, `ddl_export` and `connections`
branch once for both engines.

Since "Firestore backups" Deployer can create a Firestore database, and since "Firestore point-in-time recovery and
deletes" delete one - only from its Backups tab, with the name typed. Removing the source only forgets it; nothing in Google changes, so there is no cleanup job and project deletion
is not blocked by it.

- **Documents are plain JSON both ways**, with the document id as **`_id`** (a stored field literally
  named `_id` is not shown): whole numbers are `integerValue`, other numbers `doubleValue`, and
  Firestore's own types use `$` forms - `{"$timestamp": "2026-01-01T00:00:00Z"}`, `{"$base64": "..."}`
  (bytes), `{"$ref": "users/u1"}` (a reference to a document of the same database), `{"$geo":
  {"latitude": 1.5, "longitude": 2.5}}`; maps and arrays as themselves.
- **Collections are paths**: `users`, or a subcollection `users/u1/orders`. The documents routes take the
  path as `{name}` (routed as `{name:path}`; the dashboard sends it URL-encoded) and validate it (odd
  segments for a collection, no empty / `.` / `..` segment).

### Add database -> In your Firebase project

The **In your Firebase project** card is now available for **NoSQL** (`only: "nosql"` in
`cloud_db.LOCATIONS`; the dialog greys it out for SQL; the Realtime Database joined it in C2-4). The section
explains Firestore in one paragraph (documents in collections, a document can hold its own collections, no
server to size, used with the Firebase / Google Cloud SDK), where the database comes from, how apps and this
PC reach it and the cost (connecting is free; Google bills reads, writes and storage beyond the daily free
quota, including what the dashboard reads). The user picks the Firebase connection and a database: the id
field suggests the project's databases (`GET .../cloud/connections/{cid}/databases` returns `firestore:
[{id, location, type, problem}]` for a Firebase connection, `problem` for a Datastore-mode database) and
still takes a typed id when listing is refused (`firestore_problem`). Connecting checks `GET
databases/<id>` (`400 connection_failed` with a hint to create it in the Firebase console when it does not
exist, or that Datastore mode is not supported). No billing confirmation: nothing is created.

### Browsing, editing, querying

- **Data tab**: the sidebar lists the top-level collections (from the schema) plus **Open a collection
  path** (a subcollection, or a new collection, which appears with its first document) and **Export as
  JSON**. The documents view pages with **`cursor`** (`next_cursor`, the last document id; documents are
  ordered by id), the filter box takes **equality** filters (`{"status": "open"}`, dotted names reach
  into maps: `{"address.city": "Oslo"}`, `{"_id": "u1"}` is the document id) and `total` is an exact
  count (a count aggregation, with the filter). Each document has a **Collections inside this document**
  button (`GET .../collections/{name}/documents/{doc_id}/collections`, one `listCollectionIds` call) to
  open a subcollection, and a subcollection has a button back to its parent collection. Insert takes an
  optional `_id` (else Firestore makes one; an existing id is `409 document_exists`); edit sets / removes
  top-level fields with an update mask of exactly those fields and `currentDocument.exists` (`404
  document_not_found` for a missing one; `_id` can't change, `400 immutable_field`); delete likewise
  (subcollections of a deleted document stay). Collections are not created or dropped here (`400
  not_supported`).
- **Query console**: one JSON request, a subset of Firestore's structuredQuery (QUERY_CONSOLE.md
  "Firestore"): `from` (a collection path, or `{"collectionId": "orders"}` for every collection with
  that name), `where` (`{field, op, value}`, lists AND-ed, `{"and": [...]}` / `{"or": [...]}`, unary
  `IS_NULL` / `IS_NAN` / `IS_NOT_NULL` / `IS_NOT_NAN`), `orderBy`, `select`, `limit` (capped at
  `max_rows`), `offset`; `operation` `count` and `get` read, `create`, `update`, `delete` write. Viewers
  may only `query`, `count` and `get` (`403 read_only_role`). Answers have the MongoDB console's shape;
  documents carry `_path`. Firestore's own errors (a missing composite index comes with the console link
  that creates it) are in-band.
- **Schema**: per top-level collection, fields inferred from up to `sample` documents (`_id` first as
  the primary key; timestamps are `date`, bytes `binData`, references `string`), every field `indexed`
  (Firestore indexes each field by itself unless exempted), indexes = the document id plus the
  collection group's **composite indexes** (`GET databases/<id>/collectionGroups/-/indexes`; left out
  when the service account may not list them), `row_count` = a count aggregation. The schema export
  writes the collections and the composite indexes as `firestore.indexes.json` (deployable with `firebase
  deploy --only firestore:indexes`) in comments.
- **Export**: `GET .../data-sources/{sid}/firestore/export?collection=<path>&limit=` (viewer+, audited as
  `data_source.export`) returns `{project_id, database, exported_at, documents, truncated, collections:
  {path: [documents]}}` - every document of the top-level collections, or of the given collection paths
  (subcollections are exported by naming their path), up to 10,000 documents per call (`truncated` says
  when more were left). Plain JSON in the same `$` forms, so documents can be inserted again. Managed exports
  to a Cloud Storage bucket: "Firestore backups as built".
- **Connection details** show the project id, database id, endpoint and location - no URI, user or password.
- **Backups**: scheduled backups, restores and managed exports are on the Backups tab ("Firestore backups as
  built"); point-in-time recovery is still set up in the Google Cloud console.

### Apps on Cloud Run

`database_access` on a **`firebase_app`** now means the project's Firestore databases on the **same
Firebase connection** (`cloud.DATABASE_TARGETS = ("aws_app", "firebase_app")`; `firebase_hosting` still
refuses it). The app gets `DEPLOYER_DB_<NAME>_PROJECT` and `_DATABASE` (the database id) - **no
credentials**: on Cloud Run the Google SDKs sign in as the service's own identity, the project's **default
compute service account** (`<project number>-compute@developer.gserviceaccount.com`). That account needs
the **Cloud Datastore User** role (it has it when the project still grants Editor to it by default); Deployer
does not grant IAM roles itself (that would need project IAM admin rights), so the build log names the
account (from the project's `projectNumber`) and the role, and the app form and the Settings guide say so.
A Firestore database in another Firebase project is skipped with a log line; App Runner apps never get one.

### Permissions added (Settings -> Cloud accounts guide)

`cloud.GOOGLE_ROLES` + **Cloud Datastore User** (`roles/datastore.user`: read and write documents, list
collections and indexes, count, get the database), marked "only needed for Firestore databases";
`GOOGLE_APIS` + **Cloud Firestore API** (`firestore.googleapis.com`). Listing a project's databases may need
`datastore.databases.list`; when the role refuses it the dialog says so and still takes a typed database id.
The guide also tells owners who already made the `deployer` account to add the role, and to give it to the
default compute service account for full apps.

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/projects/{pid}/cloud/databases/connect` | admin+ | `{connection_id (Firebase), name, database?}` (default `(default)`) | `DataSource` (201); `400 connection_failed` |
| GET | `/projects/{pid}/data-sources/{sid}/collections/{name}/documents` | viewer+ / API keys | `filter?`, `limit`, `cursor?` | `{documents, total, next_cursor}`; `{name}` may be a subcollection path |
| GET | `/projects/{pid}/data-sources/{sid}/collections/{name}/documents/{doc_id}/collections` | viewer+ / API keys | – | `{collections: ["users/u1/orders"]}` |
| GET | `/projects/{pid}/data-sources/{sid}/firestore/export` | viewer+ | `collection?` (repeatable), `limit?` (1-10000) | `{project_id, database, exported_at, documents, truncated, collections}` |

`GET .../cloud/databases/options` adds `firestore: {what, connect, cost, network}` and the Firebase
location's `only: "nosql"`; the connection listing adds `provider`, `project_id`, `firestore`,
`firestore_problem` for Firebase connections; data sources' `cloud` adds `project_id` and `resource_kind:
"database"`. Editing a Firestore source's connection settings is refused (rename only).

### MCP

`connect_cloud_database` takes a Firebase `connection_id` with `database`, `list_cloud_databases` returns
`firestore`, the document tools take collection paths, `list_documents` pages with `cursor`, `run_query`
takes the JSON request, plus `list_subcollections` (any key) and `export_documents` (service key; up to
200 documents per call, the MCP result cap). See MCP.md.

### Not verified against real clouds

Tested against an in-memory Firestore behind the `firestore` seam (`tests/test_firestore.py`: values and
paths, connect / listing / Datastore mode / missing database, paging, filters, subcollections, insert /
update masks / delete, the console and its read-only rule, collection-group and OR queries, schema and
composite indexes, both exports, the Cloud Run app's environment and the log naming its service account,
MCP) and the real client's URL building, error parsing and token cache against `httpx.MockTransport`. Not yet
run against a live project: the exact REST shapes (cursors with `startAt`, the count aggregation, the
update mask's quoting), whether `roles/datastore.user` includes `datastore.databases.list` (the dialog
works either way), and Cloud Run reaching Firestore as the default compute service account.

## Firestore backups as built: new databases, managed exports, scheduled backups, restores

Everything goes through the **Firestore Admin REST API v1** (`https://firestore.googleapis.com/v1/projects/<p>/...`)
behind the same `GcpClient.firestore` seam - its path guard now also accepts `databases:restore`,
`databases/<id>/{operations,backupSchedules}/...` and `locations/<l>/backups` - and, for the export bucket, the
**Cloud Storage JSON API** (`GcpClient.bucket` / `create_bucket`, `https://storage.googleapis.com/storage/v1/b`),
with the Firebase connection's service-account token (no Google SDK). `services/firestore_admin.py` holds the
exports, schedules, backups and restore checks; `cloud_db.create_firestore` and its job make databases. No
migration: `cloud_state` gains `job_id`, `create_requested` / `create_op`, `import_from` / `import_requested` /
`import_op`, `restore_from` and `export_bucket`. Everything that costs money is **off until confirmed**: the
dialogs show the cost note and need a tick; the API and MCP need `confirm_billing: true` (`422
billing_not_confirmed` with the note otherwise). Removing a source only forgets it (`created` stays false);
`GcpClient.firestore` refuses any `DELETE` that is not a document or a backup schedule, whatever the caller.
Deleting a database, a backup or an export in Google is the separate, name-confirmed step of "Firestore
point-in-time recovery and deletes", through its own method `GcpClient.delete_firestore`.

### New databases

**Add database -> In your Firebase project -> Cloud Firestore** now ends with *Or create a new Firestore
database*: a **location** (`cloud_db.FIRESTORE_LOCATIONS`: `nam5` US multi-region - the default -, `eur3`, and
ten regions; it cannot move later), an optional **database id** (default `deployer-<name>-<id8>`) and the cost
tick (the free quota covers only one database per project). `POST .../cloud/databases {engine: "firestore",
connection_id, name, location?, database?, confirm_billing: true}` checks a typed id is free (`409
database_exists`: connect it instead), adds a `creating` source and queues `data_source.cloud_create`:
`POST databases?databaseId=<id> {locationId, type: FIRESTORE_NATIVE}` -> follows the long-running operation
(`GET databases/<id>/operations/<op>`; when Google names none it can read, until `GET databases/<id>` answers)
-> `ok` with the location Google reports. A failed operation leaves the source in `error` with Google's reason.

### Managed exports and imports (Backups tab -> Exports to Cloud Storage)

- **Export now** (admin, cost tick): `POST databases/<id>:exportDocuments {outputUriPrefix, collectionIds?}` to
  `gs://<bucket>/deployer-exports/<database>/<UTC yyyymmdd-HHMMSS>`. The bucket is one the user made (it must answer
  `GET b/<bucket>`, else `400 bucket_unavailable` saying how to create it and grant the role), or - the default
  in the dialog - **`deployer-<project>-firestore`**, made on request (`POST b?project=<p>`: uniform access, public
  access prevented, label `managed-by=deployer`, location `US` / `EU` for `nam5` / `eur3`, else the database's
  region; an existing bucket the account can see is reused, one it cannot is "taken by another Google
  project"). The bucket used is remembered (`export_bucket`) as the next default. Collections are collection ids
  (every collection with that name at any depth); none = all. The export runs on in Google.
- The list shows the database's recent exports and imports (`GET databases/<id>/operations`, Google keeps them
  a few days): kind, state, the `gs://` folder, documents done, start time, error; it polls while one runs.
- **Import into a new database** on a finished export (admin, cost tick; `POST .../firestore/import {input_uri,
  name, database?, location?}`): Google only imports into an existing database and an import **overwrites**
  documents with the same ids, so Deployer always makes a **new** database (same job as above, in the source
  database's location unless given; a typed id that exists is refused), then `POST databases/<new>:importDocuments
  {inputUriPrefix, collectionIds?}` and follows that operation. The new database is a new data source.

### Scheduled backups and restores (Backups tab)

- **Scheduled backups**: `GET/POST databases/<id>/backupSchedules`, `DELETE .../backupSchedules/<sid>`. *Add
  schedule* (admin, cost tick): every day (kept 1-7 days) or every week on a chosen day (kept 1-98 days);
  `{retention: "<days*86400>s", dailyRecurrence: {}}` or `{weeklyRecurrence: {day}}`. Google allows one daily and
  one weekly schedule per database (`409 schedule_exists` before asking it). Google takes the backups itself, also
  while this PC is off. *Remove* stops new backups; the taken ones stay until they expire.
- **Backups**: `GET locations/-/backups` filtered to this database (`database == projects/<p>/databases/<id>`),
  newest first: time, state, size, documents, expiry. **Restore...** on a ready one (admin, cost tick; `POST
  .../firestore/restore {backup, name, database?}`): the backup must be this project's
  (`projects/<p>/locations/<l>/backups/<id>`); the job sends `POST databases:restore {databaseId, backup}` and
  follows the operation. Google can only restore into a **new** database (in the backup's location), which
  becomes a new data source; the original is not touched.
- Each of the three lists is read on its own, so a missing role empties only that list, with the reason
  (`problems`).

### Permissions added (Settings -> Cloud accounts guide)

`cloud.GOOGLE_ROLES`, marked "only needed to create Firestore databases, back them up, export or restore them":
**Cloud Datastore Import Export Admin** (`roles/datastore.importExportAdmin`: exports and imports), **Cloud
Datastore Owner** (`roles/datastore.owner`: create databases, backup schedules, list backups, restore - Google has
no narrower predefined role that creates a database; it includes the import / export rights) and **Storage
Admin** (`roles/storage.admin`) granted **on the export bucket** (its Permissions tab), or on the project only to
let Deployer make the `deployer-*-firestore` bucket (Cloud Storage IAM cannot limit bucket creation by name).
`GOOGLE_APIS` + **Cloud Storage API** (`storage.googleapis.com`). Firestore writes the export files as its own
service agent (`service-<number>@gcp-sa-firestore.iam.gserviceaccount.com`), which has access to buckets of the
same project by default.

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/projects/{pid}/cloud/databases` | admin+ | `{connection_id (Firebase), name, engine: "firestore", location?, database?, confirm_billing: true}` | `{data_source, job}` (201); `409 database_exists` |
| GET | `/projects/{pid}/data-sources/{sid}/firestore/backups` | viewer+ | – | `{database, location, bucket, default_bucket, days, max_retention_days, costs, notes, problems, schedules: [{id, recurrence, day, retention_days, created_at}], backups: [{name, id, location, state, snapshot_time, expire_time, size_bytes, documents}], operations: [{id, kind, done, state, uri, collections, documents, started_at, ended_at, error}]}` |
| POST | `/projects/{pid}/data-sources/{sid}/firestore/exports` | admin+ | `{bucket? \| create_bucket: true, collections?, confirm_billing: true}` | `{operation, bucket, output_uri}` (201); audit `data_source.cloud_export` |
| POST | `/projects/{pid}/data-sources/{sid}/firestore/import` | admin+ | `{input_uri: "gs://...", name, database?, location?, collections?, confirm_billing: true}` | `{data_source, job}` (201); audit `data_source.create` with `cloud: import` |
| POST | `/projects/{pid}/data-sources/{sid}/firestore/backup-schedules` | admin+ | `{recurrence: daily \| weekly, day?, retention_days, confirm_billing: true}` | the schedule (201); `409 schedule_exists`; audit `data_source.cloud_backup_schedule` |
| DELETE | `/projects/{pid}/data-sources/{sid}/firestore/backup-schedules/{schedule_id}` | admin+ | – | `{ok}`; `404 schedule_not_found`; audit `data_source.cloud_backup_schedule_delete` |
| POST | `/projects/{pid}/data-sources/{sid}/firestore/restore` | admin+ | `{backup, name, database?, confirm_billing: true}` | `{data_source, job}` (201); audit `data_source.create` with `cloud: restore` |

`GET .../cloud/databases/options` adds `firestore.create_cost` and `firestore.locations`. The other routes answer
`400 wrong_source_kind` for a non-Firestore source and `409 cloud_database_creating` while it is being made.

### MCP

`create_cloud_database` takes `engine: "firestore"` with `location` / `database`; plus `list_firestore_backups`
(any key) and the project-admin tools `firestore_export`, `firestore_import`, `set_firestore_backup_schedule`,
`delete_firestore_backup_schedule` and `restore_firestore_backup` (all but the delete billable: `confirm_billing`
after the user agreed). See MCP.md.

### Not verified against real clouds

Tested against an in-memory Firestore Admin behind the `firestore` seam that accepts only the documented REST
paths and the real client's path guard (`tests/test_firestore_admin.py`: create with location / id / billing /
taken id, operation polling and a failed operation, exports to a named and a made bucket, a missing bucket,
the operations list, import into a new database, schedule create / limits / one-per-kind / delete, backups
filtered to the database, restore and its project check, a missing role emptying one list, roles, MCP), the
real client's Firestore Admin and Cloud Storage URLs against `httpx.MockTransport`, and the dashboard's Backups
card (`FirestoreBackups.test.tsx`). Not yet run against a live project: the exact operation names Google returns
for creating and restoring a database (the fallback polls the database itself), whether a restored database
answers `GET` before the restore has finished, the bucket location Google accepts for `nam5` / `eur3` exports
(`US` / `EU` assumed), whether `roles/datastore.owner` alone lists backups across locations (`locations/-`), the
retention limits (7 days daily, 14 weeks weekly, as documented), and the prices in the cost notes (approximate,
they vary by location).

## Firestore point-in-time recovery and deletes (as built)

The two Firestore leftovers of "C2 - cloud databases (what is left)", on the same **Firestore Admin REST API v1**
seam (`GcpClient.firestore`; its path guard already accepted `databases:clone`, `PATCH` / `DELETE databases/<id>`
and `locations/<l>/backups/<id>`) and, for export files, the **Cloud Storage JSON API** (`GcpClient.list_objects` /
`delete_object`: `GET b/<bucket>/o?prefix=&delimiter=&pageToken=`, `DELETE b/<bucket>/o/<percent-encoded name>`).
Code: `services/firestore_admin.py` (status, PITR, clone checks, deletes), `cloud_db.create_firestore(clone_from=)`
and its job. No migration, no new Google role: **Cloud Datastore Owner** (already asked for) covers updating,
cloning and deleting databases and deleting backups; **Storage Admin** on the bucket covers deleting export files.

### Point-in-time recovery (Backups tab -> Point-in-time recovery)

- The card reads the database (`GET databases/<id>`): **on / off** (`pointInTimeRecoveryEnablement`), *restorable
  from* (`earliestVersionTime`) and Google's **delete protection** (`deleteProtectionState`). The Backups tab's
  answer carries them as `status` (`problems.status` when the account may not read the database).
- **Turn on...** (admin; billable: Google keeps 7 days of versions instead of 1 hour and bills their storage at the
  database's storage price - the dialog shows the note and needs the tick; API `confirm_billing: true`, else `422
  billing_not_confirmed`) / **Turn off...** (no tick; says the older versions go): `PATCH databases/<id>
  ?updateMask=pointInTimeRecoveryEnablement {pointInTimeRecoveryEnablement: POINT_IN_TIME_RECOVERY_ENABLED |
  _DISABLED}`. Google applies it as a long-running operation; the card shows the new state on its next read.
  Audit `data_source.cloud_pitr`.
- **Restore to a time...** (admin; billable like a restore, cost tick / `confirm_billing: true`): a `datetime-local`
  minute in the viewer's time zone, any time from *restorable from* until a minute ago (the last hour even with
  point-in-time recovery off). The API takes `point_in_time` (ISO 8601; UTC when it has no zone), rounds it
  **down to the whole minute** (Google's rule), refuses one in the future or before `earliestVersionTime` (`400
  invalid_restore_time`), then - like a backup restore - makes a **new** data source (`creating`, typed name, id
  `deployer-<name>-<id8>` unless given; a taken id is `409 database_exists`) and queues `data_source.cloud_create`,
  which sends `POST databases:clone {databaseId, pitrSnapshot: {database: projects/<p>/databases/<id>,
  snapshotTime}}` and follows the operation. The copy is in the source database's location; the original is
  never touched. Audit `data_source.create` with `cloud: clone`.

### Deletes (Backups tab; typed name)

Every delete names the database's **exact name** (the data source's, as in "Deleting a cloud database over the
API and MCP") and `confirm_delete: true`; without them the answer is the dry run, `422 delete_not_confirmed` with
`details: {name, removes, keeps}`. The dashboard's dialogs ask for the name typed. **Project admins only** -
service keys get `401` / `403`: G4 lets keys delete a cloud database because a final snapshot / backup is kept,
and nothing is kept here.

- **Delete database...** (card *Delete this database*): `GET databases/<id>` first; while Google's **delete
  protection** is on the button is off and the API answers `409 delete_protected` (turn it off in the Google Cloud
  console - Deployer never changes it). Otherwise `DELETE databases/<id>?etag=<etag>`, then the data source is
  removed like the dashboard's remove (audits `data_source.cloud_database_delete` and `data_source.delete`).
  Google deletes the documents and the backup schedules; backups already taken stay until they expire (restoring
  them needs the Google Cloud console, since their source is gone here) and exports stay in Cloud Storage. Removing
  a Firestore source on the Databases tab (or `delete_cloud_database`) still only forgets it.
- **Delete...** on a backup: the name must be one of this project's backups (`422` otherwise) and `GET
  locations/<l>/backups/<id>` must name this database (`404 backup_not_found` otherwise); then `DELETE` it. Audit
  `data_source.cloud_backup_delete`.
- **Stored exports** (Exports card): the export folders Deployer made of this database in its remembered bucket
  when that is a `deployer-*` one (`GET b/<bucket>/o?prefix=deployer-exports/<database>/&delimiter=/`), newest
  first, each with **Import...** and **Delete...** (the answer's `exports: [{uri, created_at}]`). Deleting takes
  only `gs://deployer-.../deployer-exports/<this database>/<yyyymmdd-HHMMSS>` (`422` for any other bucket or
  folder - exports in a bucket the user made are deleted in the Google Cloud console), lists every object under
  the folder and deletes them one by one while the request waits (`404 export_not_found` when none are left).
  Audit `data_source.cloud_export_delete` with the file count.

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| PUT | `/projects/{pid}/data-sources/{sid}/firestore/pitr` | admin+ | `{enabled, confirm_billing (to turn on)}` | `{pitr}` |
| POST | `/projects/{pid}/data-sources/{sid}/firestore/clone` | admin+ | `{point_in_time, name, database?, confirm_billing: true}` | `{data_source, job}` (201); `400 invalid_restore_time` |
| DELETE | `/projects/{pid}/data-sources/{sid}/firestore/database` | admin+ | `?confirm_name=&confirm_delete=true` | `{ok, name, removes, keeps}`; `409 delete_protected` |
| DELETE | `/projects/{pid}/data-sources/{sid}/firestore/backups` | admin+ | `?backup=<name>&confirm_name=&confirm_delete=true` | `{ok, name, removes, keeps}`; `404 backup_not_found` |
| DELETE | `/projects/{pid}/data-sources/{sid}/firestore/exports` | admin+ | `?uri=gs://deployer-...&confirm_name=&confirm_delete=true` | `{ok, files, name, removes, keeps}`; `404 export_not_found` |

`GET .../firestore/backups` adds `status: {pitr, earliest_version_time, delete_protection}`, `exports`,
`costs.pitr`, `costs.clone` and `notes.pitr`.

### MCP

`set_firestore_point_in_time_recovery` and `restore_firestore_to_time` (billable: `confirm_billing` after the
user agreed), and `delete_firestore_database`, `delete_firestore_backup`, `delete_firestore_export` (call with
`confirm_delete: false` first, show the user `removes` / `keeps`, and only after their yes send the name and
`confirm_delete: true`); all project-admin, not in `SERVICE_KEY_TOOLS`. `list_firestore_backups` now also returns
`status` and `exports`. See MCP.md.

### Not verified against real clouds

Tested against the in-memory Firestore Admin fake (`tests/test_firestore_admin.py`: the status read, PITR on with
the billing rule and off, restore to a time - rounding, a time before the window or in the future, the clone call
and its job -, the database delete's dry run, wrong name, developer and service-key refusal, delete protection,
the etag and the removed source, backup deletes of this / another database / another project, the stored exports
list, export deletes with the bucket / folder checks, the MCP tools), the real client's Cloud Storage object URLs
(paging, percent-encoded names) against `httpx.MockTransport`, and the dashboard (`FirestoreBackups.test.tsx`).
Not yet run against a live project: the clone call's exact shape and operation name (`databases:clone` with
`pitrSnapshot`, as documented), whether `roles/datastore.owner` alone may clone, whether backups really outlive a
deleted database, how soon `earliestVersionTime` moves back to 7 days after turning recovery on, whether the
database delete needs the `etag` (sent when Google returns one), and the point-in-time recovery price (the storage
price of the location, approximate).

## C2-4 as built: Firebase Realtime Database

### Data model

A Realtime Database is an `external` data source with `kind: nosql`, `engine: firebase_rtdb` on a **Firebase**
cloud connection: **one database instance** of the connection's Google project. No migration: `cloud_state`
holds `{provider: firebase, service: rtdb, created: false, instance, url, project_id, location}` and
`config_encrypted` is `{}` - no secret of its own. Every data call goes to the database's own REST API
(`<url>/<path>.json`) through `cloud_gcp.GcpClient.rtdb(method, url, path, body, params)` - the seam tests fake -
with an access token for the scopes `firebase.database` + `userinfo.email` from the same PyJWT service-account
flow (tokens are now cached per key **and scope**). The seam only accepts a database URL matching
`https://<id>.firebaseio.com` or `https://<id>.<region>.firebasedatabase.app` (the URL comes from Firebase's
management API, never from the user) and paths of percent-encoded keys (no `.`, so no `..`), so the token only
goes to a Firebase database host. Answers are read as a stream and refused over **32 MB** (`413 too_large`:
read a smaller path or use shallow / limitToFirst), never buffered whole. `services/rtdb.py` is the adapter,
returned by `connections.cloud_engine("firebase_rtdb")`. The service-account token has **admin access**: the
database's security rules do not apply to it (like Firebase's Admin SDK); the dialog says so.

- **The data is one JSON tree addressed by paths**: `users/ann/name`; `""` (or `/`) is the root. Keys are text
  without `. $ # [ ] /` or control characters, at most 768 bytes, 32 levels deep (Firebase's limits, checked
  before sending: `400 invalid_path` / `invalid_value`). Values are plain JSON; a server value such as
  `{".sv": "timestamp"}` passes through.
- **Deployer never deletes a Realtime Database.** Removing the source only forgets it, so there is no cleanup
  job and project deletion is not blocked (`created` stays false even when Deployer created the default
  instance: Firebase keeps a project's default database).

### Add database -> In your Firebase project -> Realtime Database

The Firebase card (NoSQL only) first asks **Which Firebase database?** with one plain sentence each
(`options.firestore.short`, `options.rtdb.short`): *Cloud Firestore keeps separate documents in collections and
can search them by several fields at once - the usual choice for a new app* / *Realtime Database keeps everything
in one big JSON tree that apps read and write by path and that sends every change to open apps instantly - good
for small, fast-changing data like chat or who is online.* The Realtime Database section explains it in one
paragraph, how this PC and apps reach it (the dashboard bypasses the security rules; visitors go through them)
and the cost, then lists the project's instances (`GET .../cloud/connections/{cid}/databases` returns `rtdb:
[{id, url, location, type, state, problem}]` from the management API's `projects/<p>/locations/-/instances`,
`rtdb_problem` when listing is refused):

- **Connect** one (`POST .../cloud/databases/connect` with `instance`): it must be in the listing (so its URL is
  Firebase's own) and answer a shallow read of its root; a disabled one is refused with the reason.
- **Create the project's default database** when it has none (billable once used: cost note + ticked box; API
  `engine: "firebase_rtdb"`, `location` = `us-central1` (default), `europe-west1` or `asia-southeast1` - it cannot
  move later - and `confirm_billing: true`): `POST .../locations/<loc>/instances?databaseId=<project>-default-rtdb`
  with `{type: DEFAULT_DATABASE}`. Synchronous - Firebase answers with the ready database - so there is no job
  (`job: null`). When the project already has a default database (or one appears meanwhile, `409`) that one is
  connected instead (a disabled one is refused with the reason); a retry never creates a second one. Further (`USER_DATABASE`) instances are made in the
  Firebase console (Blaze plan) and connected here.

### Browsing, editing, querying

- **Data tab**: a tree instead of the collections list. Each branch opens with one **shallow** read
  (`shallow=true`: each child cut to `true`, or kept when it is a plain value), so a big database stays fast; up
  to 200 children are listed per branch (more: open a deeper path or search in the Query tab). A path box opens
  any path, **Up** goes to the parent. Developers **edit** a value as JSON (the full value is loaded first;
  saving replaces it and everything under it), **add** a child (a typed key, or empty for a Firebase-made,
  time-ordered key via push) and **delete** a path (confirmed). The root cannot be replaced or deleted (`400
  root_write`). **Export as JSON** downloads the whole database (`format=export`, the JSON the Firebase console
  imports).
- **Data API** (viewer+ and anon keys read, developer+ and service keys write; DATA_API.md "Realtime Database"):
  `GET .../data-sources/{sid}/rtdb?path=` with `shallow`, or Firebase's query parameters `orderBy` (`$key`,
  `$value`, `$priority` or a child path) + `startAt` / `endAt` / `equalTo` (JSON, or plain text) / `limitToFirst`
  / `limitToLast` -> `{path, value}` plus `children: [{key, value}]` in Firebase's order (the REST API answers
  filtered results unordered; Deployer sorts them: null, false, true, numbers, text, objects; keys that are 32-bit
  whole numbers first). `PUT` (set), `PATCH` (update: keys may be child paths such as `address/city`, the others
  stay), `POST` (push -> `{key}`), `DELETE ?path=`. Ordering by a child needs an `.indexOn` rule; Firebase's
  refusal comes back as `400 query_failed` with how to add it. The documents and collections routes answer `400
  not_supported` for a Realtime Database.
- **Query console**: one JSON request (QUERY_CONSOLE.md "Realtime Database"): `{"path", "orderBy", "startAt",
  "endAt", "equalTo", "limitToFirst", "limitToLast", "shallow"}` for `get` (the default), or `"operation": "set"
  | "update" | "push" | "delete"` with `"value"`. Viewers may only `get` (`403 read_only_role`). Ordered reads
  without a limit get `limitToFirst = max_rows + 1`. Answers have the MongoDB console's shape; `result_docs` are
  the children as `{_key, ...fields}` (plain values as `{_key, _value}`).
- **Schema**: the top-level keys (up to 50) as collections, fields inferred from their first 20 children (whole
  subtrees, so far fewer than for documents) with `_key` as the primary key, `row_count` null; naming conventions
  are not checked (keys are data). The schema export lists the URL and top-level keys and says where the rules
  and `.indexOn` indexes live (`database.rules.json`, `firebase deploy --only database`).
- **Export**: `GET .../data-sources/{sid}/rtdb-export?path=` (viewer+, audited as `data_source.export`) ->
  `{project_id, instance, url, path, exported_at, data}`, up to the 32 MB read cap.
- **Connection details** show the URL (as the URI), project, database id and location - no user or password.
- **Backups**: the "up to their provider" note; Firebase's daily Realtime Database backups (Blaze plan) are set
  up in the Firebase console.

### Apps on Cloud Run

`database_access` on a `firebase_app` also gives the project's Realtime Databases on the same Firebase
connection: `DEPLOYER_DB_<NAME>_URL` (the database URL the Firebase Admin SDK takes), `_PROJECT` and `_DATABASE`
(the instance id) - **no credentials**. The app signs in as the project's default compute service account, which
needs the **Firebase Realtime Database Admin** role (or Editor); the build log names the account and the role
each of its databases needs.

### Permissions added (Settings -> Cloud accounts guide)

`cloud.GOOGLE_ROLES` + **Firebase Realtime Database Admin** (`roles/firebasedatabase.admin`: list and create
instances, read and write their data), marked "only needed for Realtime Databases"; `GOOGLE_APIS` + **Firebase
Realtime Database Management API** (`firebasedatabase.googleapis.com`, for listing and creating instances; the
data REST API needs no API switched on). Google has no narrower predefined role that both creates the default
instance and writes data; the Viewer role would leave the dashboard read-only.

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/projects/{pid}/cloud/databases` | admin+ | `{connection_id (Firebase), name, engine: "firebase_rtdb", location?, confirm_billing: true}` | `{data_source, job: null}` (201) |
| POST | `/projects/{pid}/cloud/databases/connect` | admin+ | `{connection_id (Firebase), name, instance}` | `DataSource` (201); `400 connection_failed` |
| GET | `/projects/{pid}/data-sources/{sid}/rtdb` | viewer+ / API keys | `path?`, `shallow?`, `orderBy?`, `startAt?`, `endAt?`, `equalTo?`, `limitToFirst?`, `limitToLast?` | `{path, value, children?}` |
| PUT | `/projects/{pid}/data-sources/{sid}/rtdb` | developer+ / service keys | `{path, value}` | `{path, value}` |
| PATCH | `/projects/{pid}/data-sources/{sid}/rtdb` | developer+ / service keys | `{path, value: {child path: value}}` | `{path, value}` |
| POST | `/projects/{pid}/data-sources/{sid}/rtdb` | developer+ / service keys | `{path, value}` | `{path, key}` |
| DELETE | `/projects/{pid}/data-sources/{sid}/rtdb` | developer+ / service keys | `path` | `{path, deleted: true}` |
| GET | `/projects/{pid}/data-sources/{sid}/rtdb-export` | viewer+ | `path?` | `{project_id, instance, url, path, exported_at, data}` |

`GET .../cloud/databases/options` adds `rtdb: {short, what, connect, cost, network, locations}` and
`firestore.short`; the connection listing adds `rtdb` / `rtdb_problem`; data sources' `cloud` adds `url`.
Editing a Realtime Database source's connection settings is refused (rename only).

### MCP

`rtdb_read` (any key: `path`, `shallow`, the query parameters; `limitToFirst` defaults to 200 with `orderBy`),
`rtdb_write` (service key: `operation` set / update / push / delete, `path`, `value`), `create_cloud_database`
with `engine: "firebase_rtdb"` + `location` (billable, `confirm_billing`), `connect_cloud_database` with
`instance`, `list_cloud_databases` returns `rtdb`, `export_documents` takes `path` for a Realtime Database and
`run_query` the JSON request. See MCP.md.

### Not verified against real clouds

Tested against an in-memory Realtime Database behind the `rtdb` seam (`tests/test_rtdb.py`: paths, values, query
parameters and Firebase's ordering; listing, connect, creating the default database with billing confirmation and
its idempotence; shallow browsing, ordered / filtered reads, the missing-index error, set / update / push /
delete, the root guard, roles and API keys, the size cap; the console and its read-only rule; schema; export; the
Cloud Run app's environment and log; MCP) and the real client's URLs, scopes, error parsing, size cap and URL /
path guards against `httpx.MockTransport`. Not yet run against a live project: the management API's exact shapes
(creating the default instance on a Spark-plan project, the `locations/-` listing), whether every instance type
accepts the `firebase.database` + `userinfo.email` token as admin, how Firebase's `shallow` renders plain
children (the tree handles both readings), and Cloud Run reaching the database as the default compute service
account.

## C2-5 as built: MCP, transfer, project delete

### MCP: every tool needs at least its REST route's role

The MCP handlers call the route functions directly, so the routes' own `require_role` never ran: since C2-1
the cloud account tools were open to **service keys** (developer) although their routes are admin-only.
Each tool's role is now at least its route's (`tests/test_mcp.py` maps every tool to the route(s) it wraps
and compares the roles read from the routes' dependencies, so a new tool must name its route):
`list_cloud_connections`, `list_cloud_databases`, `create_cloud_database`, `connect_cloud_database` and
`create_cloud_backup` need a project **admin** - an admin's dashboard session (JWT) as the MCP bearer; a
service key does not see them (`-32602 Unknown tool`), and the agent asks the user to do it in the dashboard
(*Add database -> In your AWS account / In your Firebase project*) instead. The billable ones still need
`confirm_billing: true`. No other tool was below its route.

### Data tools on cloud databases

The data tools reach every cloud engine through the same `source_ops` / query console paths as the REST
API: RDS / Aurora are ordinary SQL sources (`list_rows`, `insert_/update_/delete_row`, `run_query`,
`get_schema`; `409 cloud_database_creating` until AWS has made the database), DynamoDB and Firestore use the
document tools (`cursor` paging, collection paths), a Realtime Database `rtdb_read` / `rtdb_write`, and
`run_query` takes each engine's JSON request (QUERY_CONSOLE.md).

### Transfer (export / import)

- **Configuration, not data.** A cloud database's row travels with its `cloud_state` and its connection
  settings - for RDS that includes the database password - **only inside the passphrase-encrypted export**
  (AES-256-GCM like every other secret in the file; never in plain text). Its data is **not** exported: it
  stays in AWS / Google (export with the provider's tools, the Firestore / Realtime Database JSON export of
  the Data tab, or a SQL dump of the RDS database). Cloud connections are never exported.
- **Instance import** keeps the cloud link when the connection exists on the new instance (same id);
  otherwise RDS becomes a plain external connection and DynamoDB / Firestore / Realtime Database sources are
  skipped with a warning (they have no login of their own).
- **Project import (a copy)** never owns the original's resources: RDS comes back as a plain external
  connection, DynamoDB / Firestore / Realtime Database as *connected* (`created: false`) when the
  connection may be used by the new project, else skipped with a warning. So deleting a copy never deletes
  the original's database.

### Deleting a project

`DELETE /projects/{id}?confirm=<slug>` on a project with databases Deployer **created** in a cloud account
(RDS instances, DynamoDB tables) or apps with cloud resources answers `409 cloud_resources_left`, with
`details.resources: [{type: database | app, id, name, resources}]` and a message explaining the choice. The
owner passes **`cloud=delete`** or **`cloud=keep`**:

- `delete` queues each one's cleanup exactly as removing it would (`data_source.cloud_delete` with its final
  snapshot / backup, `app.cloud_teardown`). The jobs are detached from the project (`project_id` NULL) so
  they outlive it; a failed one raises the critical alert `cloud_cleanup_failed` (for 7 days) naming what
  is left to delete in the provider's console. Refused (`409 cloud_connection_in_project`) when a cleanup
  needs a cloud connection scoped to this project only, because that connection goes with the project:
  remove those databases / apps first, or keep them.
- `keep` leaves them running (and billed) in the account; Deployer stops tracking them. The audit entry
  `project.delete` records the choice and the list either way.

Connected databases (Firestore, the Realtime Database, connected RDS / DynamoDB) are only forgotten, as
before. The dashboard's delete dialog lists the cloud resources with both choices in plain words and keeps
the delete button off until one is picked.

### Not verified against real clouds

Everything here is local logic tested with the fakes (`tests/test_mcp.py`, `tests/test_cloud_db.py`:
role mapping, MCP data tools on an RDS source, export / import of a created database, both project delete
choices, the alert, the project-scoped connection refusal; the dashboard dialog in
`ProjectSettingsTab.test.tsx`). The cleanup jobs are the C2-1 / C2-2 / C1 ones, unverified against live
accounts as noted there.

## Deleting a cloud database over the API and MCP (as built)

Until now only the dashboard deleted a cloud database (typing its name). Agents and scripts now can too, with
the same effect and two confirmations instead of the typed dialog. No migration, no new cloud permission (the
cleanup is C2-1 / C2-2's `data_source.cloud_delete` job, already in the `DeployerDatabases` policy).

- **Route**: `DELETE /projects/{pid}/cloud/databases/{sid}?confirm_name=<name>&confirm_delete=true`. It calls
  the dashboard's `DELETE .../data-sources/{sid}` route function, so everything is the same: a database
  Deployer **created** (RDS, DynamoDB) is deleted in AWS by the cleanup job after its **final snapshot** (RDS,
  `<instance>-final-<UTC yyyymmddHHMM>`) or **final backup** of each table (DynamoDB), which stay in the account
  billed for storage until the user deletes them; its security group goes too; `409 cloud_database_creating`
  while AWS is still making it. A **connected** one (Firestore, Realtime Database, connected RDS / DynamoDB) is
  only forgotten - nothing in AWS / Google changes. The source row goes at once either way; apps lose its
  `DEPLOYER_DB_<NAME>_*` settings on their next deploy. Audited as `data_source.delete` (with `api_key_id`
  for a key).
- **Who**: a project **admin's** session, or a project **service key** (`require_role("admin",
  service_keys=True)`: a key gets through although service keys otherwise act as developer). A developer's
  session and anon keys get `403`. A service key can already change or drop all of the project's data
  (`run_query`); here the exact name, `confirm_delete` and the kept final snapshot / backup are the guard.
- **Confirmation**: `confirm_name` must equal the database's name exactly and `confirm_delete` must be
  `true`; otherwise `422 delete_not_confirmed` with `details: {name, removes, keeps}` - what would be
  deleted in the cloud account (`cloud_db.resources`, the dashboard dialog's list) and, in plain words, what
  stays (the final snapshot / backups and their storage cost, or "Deployer only forgets this database"). So
  calling without the confirmations is the dry run. Success answers `{ok, job?, name, removes, keeps}` (`job`:
  the cleanup job, for created databases). A source without a cloud link answers `400 not_a_cloud_database`
  (databases on this PC are still deleted in the dashboard only).
- **MCP**: `delete_cloud_database` (`source_id`, `confirm_name`, `confirm_delete`) wraps the route. Its role is
  `admin` like the route's, and `mcp.SERVICE_KEY_TOOLS` lets service keys see it because the route takes them
  (`tests/test_mcp.py` checks both against the route's dependency). The description tells the agent to call
  with `confirm_delete: false` first, tell the user what `removes` / `keeps` say, and only after their yes
  send the name and `confirm_delete: true`. The `deploy-website` skill says the same.

### Not verified against real clouds

Tested with the fake AWS client (`tests/test_cloud_db.py`: roles, anon / developer refusal, the dry-run
details, wrong or missing confirmations, a non-cloud source, the MCP tool with a service key through to the
final snapshot and the audit's key id, a connected database only forgotten; `tests/test_mcp.py`: tool lists
and the role mapping). The cleanup itself is the C2-1 / C2-2 job, unverified against live accounts as noted
there.

## C2 - cloud databases (what is left)

| Provider | Engine | Support |
|---|---|---|
| AWS | **RDS / Aurora** MySQL, MariaDB, PostgreSQL | **built in C2-1** (above) |
| AWS | **DynamoDB** | **built in C2-2** (above), with point-in-time recovery and restores into a new table |
| Firebase | **Cloud Firestore** | **built in C2-3** (above) |
| Firebase | **Realtime Database** | **built in C2-4** (above) |
| Firebase | Firestore: new databases, managed exports / imports, scheduled backups, restores | **built** ("Firestore backups", above) |
| Firebase | Firestore: point-in-time recovery, restore to a time, deleting databases / backups / exports | **built** ("Firestore point-in-time recovery and deletes", above) |
| all | MCP, transfer, project delete | **built in C2-5** (above) |
| all | deleting one over the API / MCP (admin session or service key) | **built** ("Deleting a cloud database over the API and MCP", above) |

Seams left by C1 and C2-1..4: data sources carry `cloud_connection_id` / `cloud_state` and the Add
database dialog has the AWS / Firebase cards (`cloud_db.LOCATIONS`); cloud apps get their database
settings through `cloud_deploy.cloud_env` (`cloud.DATABASE_TARGETS`); the MCP `create_cloud_database` tool
and the `confirm_billing` rule are in place; a NoSQL engine without its own driver is one module with the
functions of `services/dynamo.py` / `services/firestore.py` / `services/rtdb.py`, returned by `connections.cloud_engine`.
Left (not built; each is also noted in its section above):

- a NAT gateway for App Runner apps linked to an RDS database that also call the internet (the user adds one).

## C3 as built: GitHub Actions builds (pushes deploy with the PC off)

### Where it builds

Every cloud app has a **Where it builds** choice (app Settings; `app.build`, the MCP tool `set_build_location`),
each explained in one plain sentence with what happens while the PC is off and the cost
(`github_actions.LOCATIONS`):

- **This PC** (default, C1): the worker clones, builds and uploads; pushes wait while the PC is off.
- **GitHub Actions**: Deployer commits a workflow file to the app's GitHub repository. GitHub builds every
  push to the app's branch on its own runners and rolls it out straight to the cloud, signing in with a
  short-lived **GitHub OIDC token** - no AWS key or Google key is ever stored in GitHub. Pushes deploy while
  the PC is off; the PC learns about them when it is on.

No migration: the setup lives in `apps.cloud_state["github"]` (`{status setting_up | ready | error, message,
job_id, user_id, repo, repo_id, branch, workflow_path, commit, callback, role, role_arn | provider,
service_account, member}`), next to the target's own ids. `cloud_deploy.save_state` now **merges** the keys a
deploy writes into the row (instead of replacing the whole JSON), so a deploy and the setup job never drop each
other's keys. Moving the app to another target, or deleting it, tears the GitHub Actions setup down with the
rest (`app.cloud_teardown`, listed in the confirm dialogs).

### Switching to GitHub Actions

`PUT /apps/{id}/build {location: "github", confirm_billing: true}` (project admin; the dialog shows the cost
note and needs a ticked *I understand GitHub may bill build minutes*: free for public repositories, the
account's free minutes - 2,000 a month on GitHub Free - then GitHub bills; the IAM role / identity provider
are free). It needs:

- a cloud target that was **deployed once from this PC** (`409 not_deployed`: that first deploy creates the
  bucket / distribution, ECR repository / App Runner service, Hosting site or Cloud Run service the workflow
  then updates);
- a `https://github.com/<owner>/<repo>` repository the admin can push to;
- the admin's **GitHub connection with the `workflow` scope** (GitHub refuses workflow files without it):
  `github.CONNECT_SCOPE` now asks for it; connections made before C3 get `409 github_scope_missing` ("connect
  GitHub again").

It queues **`app.github_actions`** (progress in the card and Activity):

1. *Checking the repository* - `GET /repos/{owner}/{repo}` (canonical `full_name`, `id`, push permission).
2. *Letting GitHub Actions sign in to your cloud account*:
   - **AWS**: the account's IAM OIDC identity provider for `token.actions.githubusercontent.com`
     (`CreateOpenIDConnectProvider`, audience `sts.amazonaws.com`; `EntityAlreadyExists` is fine - one per
     account, shared, kept) and the role **`deployer-gha-<slug>-<id8>`** whose trust policy allows
     `sts:AssumeRoleWithWebIdentity` only with `aud = sts.amazonaws.com` and
     `sub = repo:<owner>/<repo>:ref:refs/heads/<branch>` (re-written when it exists, e.g. after a branch change),
     with one inline policy `deployer-deploy` allowing **only this app's resources**: `aws_app` -
     `ecr:GetAuthorizationToken` plus the push actions on its ECR repository, `DescribeService` / `UpdateService` /
     `ListOperations` on its App Runner service and `iam:PassRole` of the access role to App Runner; `aws_static` -
     `s3:ListBucket` on its bucket, `s3:PutObject` under `d/*` and `GetDistributionConfig` / `UpdateDistribution` /
     `CreateInvalidation` on its distribution.
   - **Google**: the workload identity pool **`deployer-github`** (one per project, shared, kept; a soft-deleted
     one is undeleted) and the OIDC provider **`gh-<id8>`** with issuer `https://token.actions.githubusercontent.com`,
     the mapping `google.subject = assertion.sub`, `attribute.repository`, `attribute.ref`, and the condition
     `assertion.repository_id == '<id>' && assertion.ref == 'refs/heads/<branch>'` (a deleted provider keeps its
     id for 30 days: it is undeleted and patched); then `roles/iam.workloadIdentityUser` on the **connection's own
     service account** for `principalSet://.../workloadIdentityPools/deployer-github/attribute.repository/<owner>/<repo>`
     (`getIamPolicy` / `setIamPolicy` on that account, keeping its other bindings and the etag). The workflow acts
     as that account (it already holds the Hosting / Cloud Run / Artifact Registry roles); a dedicated, narrower
     account would need project IAM admin rights to grant it roles, which Deployer does not ask for. So on Google
     anyone who can push to that branch gets **everything the deployer account may do** in the project (its
     Firestore / Realtime Database access and the two IAM roles below included); the confirm dialog says so.
3. *Adding `.github/workflows/deployer-<slug>-<id8>.yml`* - one commit on the app's branch through the
   contents API (an unchanged file is not committed again). That push runs the workflow once straight away, as a
   first check. When the branch changed, the old branch's copy is deleted (best effort).

A failure leaves `status: error` with the reason (the card offers *Set up again*; until then this PC keeps
building pushes); choosing GitHub Actions again re-runs the job, which is idempotent. Changing a build setting
(`branch`, `root_dir`, `preset`, the install / build / start commands, `output_dir`) re-runs it to rewrite the
workflow and the branch in the trust (`PATCH` returns `build_job_id`). Changing the repository is refused
(`409 builds_on_github`): the workflow, the trust and the reports belong to it, so switch back to This PC first.

### The workflow

`github_actions.render_workflow`: `on: push` to the branch and `workflow_dispatch`; `permissions: contents:
read, id-token: write`; one job on `ubuntu-latest` (45 min timeout, a concurrency group per app so runs never
overlap):

1. `actions/checkout@v4`, then `docker build` with **the same recipe the PC uses**
   (`deployments.generate_dockerfile`, written from base64; the `dockerfile` preset uses the repository's own) in
   `root_dir`.
2. Sign-in: `aws-actions/configure-aws-credentials@v4` with the role, or `google-github-actions/auth@v2` with the
   provider and service account (`token_format: access_token`).
3. Roll-out, tagged `gh-<run id>-<attempt>`:
   - `aws_static`: the build output copied out of the image (`docker cp`; dotfiles were already removed by the
     recipe) -> `aws s3 sync` to `d/gh-<run>/` (`no-cache` for HTML, 1 h for the rest) -> CloudFront origin path
     switched to it (`get-distribution-config` + `jq` + `update-distribution --if-match`) -> invalidation `/*`;
   - `aws_app`: push to the app's ECR repository -> `UpdateService` with the service's current source
     configuration and only the image changed (port, environment and access role stay) -> waits for the
     operation (`SUCCEEDED`, or the run fails and the previous version keeps serving);
   - `firebase_hosting`: `firebase-tools deploy --only hosting` of the output with the same SPA rewrite and HTML
     `no-cache` header, then the live channel's version name (the artifact);
   - `firebase_app`: push to Artifact Registry with the access token -> `gcloud run services update --image`
     (keeps the port and environment).
4. *Tell Deployer* (`if: always()`, never fails the run): requests a GitHub OIDC token for the audience
   **`deployer:<app id>`** and posts `{status: success | failure | cancelled, artifact, message}` to the app's
   existing webhook URL with `X-GitHub-Event: deployer_build` and `Authorization: Bearer <token>`. Left out (and
   the card says so) while Deployer's public URL is not reachable from the internet.

Every value the app's settings control is a JSON-quoted YAML value or base64, and none may contain `${{` (GitHub
would evaluate it; the setup fails with a plain error), so a build setting can neither change the workflow nor
reach repository secrets. Environment variables are **not** in the workflow: App Runner / Cloud Run keep the
ones Deployer last set, and a changed variable is applied by this PC right away ("G1 as built": an `env`
deployment republishes the live artifact with today's variables; GitHub never sees them).

### Reports, Deploy now, runs

- **Reports** (`POST /v1/hooks/github/{app_id}` with `X-GitHub-Event: deployer_build`): the token is verified
  against GitHub's published keys (`https://token.actions.githubusercontent.com/.well-known/jwks`, PyJWT's
  `PyJWKClient`, cached an hour; a test hook replaces it) - RS256, issuer, audience `deployer:<app id>`, and the
  claims `repository_id`, `repository`, `ref` (the app's branch) and `workflow_ref` (this app's workflow file) must
  match the setup, else `401 bad_signature`. `run_id`, `run_attempt` and `sha` come from the signed token, not
  the body. Each run becomes **one deployment** (`trigger: github`, log = the run's link; a repeated report is
  ignored): `success` -> `live` (the previous live one is superseded) with the artifact **derived by Deployer**
  (`d/gh-<run>`, `<ecr repo>:gh-<run>`, `<registry>/<package>:gh-<run>`; only Hosting's version comes from the
  report and must be a version of the app's own site), so a rollback to it works like any other and a report
  can't point the app elsewhere; `failure` / `cancelled` -> `failed` / `cancelled` with the run's link as the
  error. A live report queues **`app.cloud_prune`** (old S3 prefixes / ECR images beyond the newest 5, as after
  a PC deploy). Rate-limited together with the push webhook.
- **Pushes**: the PC's push webhook ignores pushes of an app that builds on GitHub (`{ignored: true}`) unless
  its setup failed.
- **Deploy now** (`POST /apps/{id}/deploy`) on such an app runs the workflow there (`workflow_dispatch` on the
  app's branch; another `branch` is `422`) and answers `202 {github_actions: true, status: "dispatched",
  runs_url}` instead of a deployment.
- **Runs**: `GET /apps/{id}/github-runs` (viewer+) -> `{runs: [{id, attempt, status, conclusion, event, branch,
  sha, message, created_at, updated_at, url}], runs_url}`, the workflow's newest 10 runs from the GitHub API with
  the setup admin's connection - including runs that finished while this PC was off.
- **Runs this PC missed** (`github_actions.reconcile`, from the worker's scheduler tick: on the first tick after
  the worker starts, then every 5 minutes): for every app with a ready setup, the workflow's newest 10 runs are
  fetched (one GitHub call per app; a failure is logged and tried again next time) and each *completed* run of
  the app's branch (`push` / `workflow_dispatch`) that has no deployment yet becomes one, oldest first, with the
  run's commit, message, its own `created_at` / `finished_at`, the log link and the same derived artifact as a
  report (`d/gh-<run>`, `<ecr>:gh-<run>`, `<registry>/<package>:gh-<run>`), so rollback to it works. A success
  newer than the live deployment goes **live** (superseding it; the next newer one supersedes that in turn); a
  success older than what is live is recorded as `superseded` with its artifact; `cancelled` -> `cancelled`;
  any other conclusion (`failure`, `timed_out`, ...) -> `failed` with the run's link. Only Firebase Hosting
  can't derive the version from the run: the **newest** successful run gets the live channel's current version
  (one Hosting call, only while that run is not recorded yet), older ones are recorded without an artifact (no
  rollback to them); while another run of the branch is still going it may have released already, so then the
  newest is recorded without one too. Every live one queues
  **`app.cloud_prune`**, so the S3 prefixes / ECR images of runs the PC never saw fall under the same keep-5
  retention (Hosting versions and Artifact Registry images stay with the providers' retention, as after a PC
  deploy). The log says *Recorded by Deployer afterwards: the run finished while this PC was off*. Idempotent
  (a recorded run is skipped - also when its own report arrives later), safe to repeat, no migration.
- **Rollbacks** still run on this PC (the `app.deploy` job republishes the old artifact), and so do
  environment changes ("G1 as built").

### Switching back, teardown

`PUT /apps/{id}/build {location: "pc"}` queues `app.cloud_teardown` with only the GitHub part: the workflow file
is deleted from the branch (a commit), the `deployer-gha-*` role (inline policy first) or the `gh-<id8>`
provider is deleted, and the service-account binding is removed unless another app of the same repository on
that connection still uses it. The shared OIDC provider / pool stay (like the shared App Runner access role).
Anything that can't be removed fails the job with the list. Moving or deleting the app does the same as part of
its teardown.

**Deleting (or moving, or switching back) while the setup job still runs** leaves nothing behind:

- the teardown's caller cancels the app's queued / running `app.github_actions` job (`cancel_setup`, in every
  `enqueue_teardown` / `enqueue_removal`) and stores its id (`setup_job_id`); the setup job checks for the
  cancel between its steps, and every save it makes re-checks that the app still builds on GitHub (row gone,
  state popped by a move or switch-back) and stops otherwise - so it never commits the workflow file for an app
  that is gone;
- the teardown job first waits for that setup job to stop (up to 5 minutes), then removes the role / provider
  **by their deterministic names** (`deployer-gha-<slug>-<id8>`, `gh-<id8>`, from the job's `slug` / `app_id`)
  even when the setup never got to record them in the state (missing ones are no errors);
- after its steps every cloud teardown runs **`sweep_orphans`** on the connection: AWS - `ListRoles`, every
  `deployer-gha-*` role tagged `managed-by=deployer` whose app no longer builds on GitHub Actions is deleted;
  Google - every `gh-*` provider of the `deployer-github` pool that no such app uses, and every
  `attribute.repository` member of the connection's service account whose repository no such app builds from
  (matched by repository, which a setup saves before it adds the member), is removed. A sweep that can't run (an older policy
  without `iam:ListRoles`) is noted in the job's result (`sweep_error`), it does not fail the teardown. The
  sweep assumes one Deployer per cloud account (like the shared `deployer-github` pool and OIDC provider): a
  second Deployer's `deployer-gha-*` roles in the same account would count as leftovers.

### Permissions added

- **AWS** (now the `DeployerRoles` policy): `iam:CreateOpenIDConnectProvider`, `TagOpenIDConnectProvider` on
  `oidc-provider/token.actions.githubusercontent.com`; `iam:GetRole`, `CreateRole`, `TagRole`, `ListRoleTags`,
  `UpdateAssumeRolePolicy`, `PutRolePolicy`, `DeleteRolePolicy`, `DeleteRole` on `role/deployer-gha-*` (no
  `PassRole`: GitHub assumes the role, nothing passes it); `iam:ListRoles` on `*` for the orphan sweep (it has
  no resource scope; only roles with Deployer's tag are touched). Like the `deployer-app-*` roles, Deployer
  writes these roles' policies itself; since G3 the `deployer-boundary` permissions boundary caps what they can
  be given ("G3 as built").
- **Google** (`cloud.GOOGLE_ROLES` / `GOOGLE_APIS`, marked "only needed to build apps on GitHub Actions"): **IAM
  Workload Identity Pool Admin** (`roles/iam.workloadIdentityPoolAdmin`) and **Service Account Admin**
  (`roles/iam.serviceAccountAdmin`) granted **on the deployer service account itself** (its Permissions tab), not
  the project, so it can only change who may act as that one account; APIs `iam.googleapis.com`,
  `sts.googleapis.com`, `iamcredentials.googleapis.com`.
- **GitHub**: the `workflow` OAuth scope.

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| PUT | `/projects/{pid}/apps/{id}/build` | admin+ | `{location: "pc" or "github", confirm_billing?}` | `App & {job_id}`; `422 billing_not_confirmed`, `409 not_deployed` / `github_not_connected` / `github_scope_missing` / `deployment_active`; audit `app.build_location` |
| GET | `/projects/{pid}/apps/{id}/github-runs` | viewer+ | – | `{runs, runs_url}`; `409 not_on_github` |
| POST | `/projects/{pid}/apps/{id}/deploy` | developer+ | `{branch?}` | GitHub Actions apps: `{github_actions: true, status: "dispatched", runs_url}` (202) |
| POST | `/hooks/github/{app_id}` | GitHub OIDC token | `X-GitHub-Event: deployer_build`, `{status, artifact?, message?}` | `{deployment_id, status}` or `{ignored: true}` |

Apps gain `build: {location: "pc"} | {location: "github", status, message, job_id, repo, workflow_path,
workflow_url, runs_url, reports}`; deployments gain `trigger: "github"`; `PATCH` returns `build_job_id`.

### Dashboard

- **App Settings -> Where it builds** (cloud apps): the two choices as cards (what, when the PC is off, cost),
  the confirm dialog listing exactly what Deployer will add (the commit, the IAM role / identity provider) with the
  cost note and the billing tick, the setup job's progress, then the workflow link, the note about environment
  variables, errors with *Set up again*, and *Build on This PC* (confirm) to switch back. The Push to deploy card
  says the webhook is not used for pushes then.
- **App page**: a *Builds on GitHub Actions* badge; **GitHub Actions runs** (status, commit, time, log link;
  polled while one runs) above the deployments, where GitHub-built deployments show the trigger *GitHub
  Actions* (the card says runs that finished while the PC was off join the deployments within minutes of it
  coming back on); **Deploy now** starts a run there.
- **Settings -> Cloud accounts**: the AWS step mentions the GitHub Actions statements; the Firebase role list
  marks the two new roles and APIs and says to grant Service Account Admin on the deployer account itself.

### MCP

`set_build_location` (project admin, like its route; `app_id`, `location`, `confirm_billing` - the description
tells the agent to explain the GitHub minutes and get the user's agreement first) and `list_github_runs` (service
key); `get_app` / `list_apps` return `build`; `deploy_app` on a GitHub Actions app answers `{github_actions: true,
status: "dispatched"}`. See MCP.md.

### Not verified against real clouds

Tested with fakes (`tests/test_github_actions.py`: the switch's checks and billing confirmation, the AWS role's
trust and scoped policy, the Google pool / provider / binding calls, the committed workflow and its recipe,
pushes ignored, dispatch, the runs list, signed reports with a wrong audience / repository / ref / workflow
refused, derived artifacts, rollback to a GitHub-built deployment, rewriting on settings changes, the `${{`
guard, both teardowns; missed runs recorded with their artifact, live / superseded / failed in order, the
rate limit, the duplicate report, the Hosting live version, rollback to a recorded run; a delete before and
during the setup job cancelling it, the role removed by name and the orphan sweep on both providers; the Google
REST shapes of the binding and the provider undelete / patch, the provider list, the pool members and the live
channel against `httpx.MockTransport`; `github_roles` (ListRoles pages + ListRoleTags) against botocore's IAM
model with `Stubber`; the dashboard chooser in `GitHubBuild.test.tsx`). Not yet run for real: the workflow
itself on GitHub's runners (the AWS CLI / `jq` / `firebase-tools` / `gcloud` steps, `firebase-tools` signing in
through the workload identity credentials file), the IAM / IAM Credentials request shapes against live
accounts, GitHub's `sub` claim for organisations that customised it (the AWS trust expects the default
`repo:<owner>/<repo>:ref:<ref>`), committing to a protected branch (the setup then fails with GitHub's
message), the runs list's field names on a live repository (`workflow_runs[].run_attempt`, `head_branch`,
`updated_at`, as documented), and the delete-during-setup race with two real worker runners (the teardown's wait
is tested with the sequential test runner).

## G1 as built: app secrets in a secret store, environment changes without a rollback

### Secrets in AWS Secrets Manager / Google Secret Manager (opt-in)

An App Runner or Cloud Run app (`cloud.DATABASE_TARGETS`) can keep its secrets in the cloud account's secret
store instead of the service's plain environment: **Settings -> Environment variables -> "Keep these in AWS
Secrets Manager / Google Secret Manager"** (project admin; off by default). Switching it on is billable, so the
dialog shows the cost (`cloud_secrets.COST`: AWS about US$0.40 per secret per month plus reads; Google 6 active
versions free, then about US$0.06 per version per month plus reads) and needs a ticked *I understand AWS /
Google charges this cloud account for it* - over the API `PATCH .../apps/{id} {cloud_secrets: true,
confirm_billing: true}` (`422 billing_not_confirmed` otherwise; `422` on a static target; developers get `403`).
No migration: `apps.cloud_state["secrets"] = {enabled, stored: {NAME: ARN | secret id}}` (`services/cloud_secrets.py`).

**What is a secret**: every variable of the app's own - Deployer stores them all encrypted, reveals them to
admins only and redacts them from logs, and has no per-variable flag - plus the `DEPLOYER_DB_*` values that carry
a database password (RDS `_PASSWORD` and `_URL`). Hosts, ports, user names, database and table names, project
ids, Realtime Database URLs and variables with an empty value (the stores refuse those) stay plain environment.
Values are never logged, never returned by the API and
never shown again by the dashboard (`cloud.secrets` lists only the **names** in the store).

On every deploy, rollback and environment change (`Publish.aws_app` / `firebase_app`, after the environment is
assembled):

- **AWS**: one secret `deployer-<slug>-<id8>-<NAME>` per value (`CreateSecret`, tagged `managed-by=deployer`;
  when it exists, `GetSecretValue` and `PutSecretValue` only if the value changed, so an unchanged redeploy
  writes nothing). Its ARN is written to `cloud_state` the moment it exists. The app's instance role
  `deployer-app-<slug>-<id8>` (C2-2; created on first use) gets a statement `secretsmanager:GetSecretValue` on
  **exactly those ARNs** next to its DynamoDB statement, and the service's `RuntimeEnvironmentSecrets` maps each
  name to its ARN (`RuntimeEnvironmentVariables` keeps the rest). App Runner reads them when an instance starts.
- **Google**: one secret `deployer-<slug>-<id8>-<NAME>` (`POST projects/<p>/secrets?secretId=`, automatic
  replication, label `managed-by=deployer`; `409` = exists), `versions/latest:access` to compare and
  `:addVersion` only when the value changed (Google bills per active version), then `:setIamPolicy` on **each
  secret** giving `roles/secretmanager.secretAccessor` to the project's default compute service account
  (`<number>-compute@developer.gserviceaccount.com`, the identity the Cloud Run service runs as; the project
  number comes from the Firebase project info - without it the deploy fails with a plain error). The Cloud Run
  container's `env` carries `{name, valueSource: {secretKeyRef: {secret, version: "latest"}}}` for them.
- After the rollout succeeded, secrets the new version no longer references are **deleted** (`DeleteSecret` with
  `ForceDeleteWithoutRecovery`, `DELETE secrets/<id>`): variables that were removed, and all of them when the
  option was switched off (the secret store is then plain environment again; the AWS role keeps no secret
  statement). Deleting after the rollout means a failed one, which keeps the previous version serving, still
  finds its secrets. Deleting the app or moving it to another target deletes every stored secret with the
  rest (`app.cloud_teardown`; the confirm dialogs list them as "AWS Secrets Manager secrets A, B").

GitHub Actions builds (C3) keep working unchanged: the workflow only swaps the image and keeps the service's
source configuration / environment, references included.

### Environment changes reach App Runner / Cloud Run apps at once

`PATCH .../apps/{id}` with `env`, `database_access` or `cloud_secrets` on an `aws_app` / `firebase_app` that
has a live deployment with an artifact starts a deployment of trigger **`env`** right away
(`deployments.republish`; the response carries `env_deployment_id`): the `app.deploy` job on this PC
republishes the live artifact - no clone, no build - with today's variables, databases and secrets, exactly like
a rollback to the live deployment (`rollback_of` = the live one), and goes live when the provider's operation
succeeded (the previous version keeps serving on failure). **Path chosen: from the PC**, also for apps whose
pushes build on GitHub Actions: the workflow never sees the variables (they would otherwise have to be
written into the repository's workflow or GitHub secrets), the PC already holds everything the service needs,
and the user is on the dashboard at that moment anyway. Changing the variables of a static target (where they
are build-time only) or of a local app still applies on the next deploy, as before. A run of the app's GitHub
workflow at the same moment makes the provider refuse one of the two updates ("operation in progress"): the
`env` deployment then fails with the provider's message and can be repeated.

### Permissions added

- **AWS** (now the `DeployerHosting` policy, statement `AppSecrets`): `secretsmanager:CreateSecret`, `GetSecretValue`,
  `PutSecretValue`, `DeleteSecret`, `TagResource` on `secret:deployer-*` only (GetSecretValue is what skips
  rewriting an unchanged value). The
  instance roles' `GetSecretValue` statements are written by Deployer through the existing `iam:PutRolePolicy`
  on `role/deployer-app-*`.
- **Google** (`cloud.GOOGLE_ROLES` / `GOOGLE_APIS`, marked "only needed when an app keeps its variables in
  Secret Manager"): **Secret Manager Admin** (`roles/secretmanager.admin`: create the secrets, add versions,
  set each secret's own IAM policy, delete) and the **Secret Manager API** (`secretmanager.googleapis.com`).
  Google has no predefined role scoped to a name prefix; an owner who wants to narrow it adds an IAM condition
  `resource.name.startsWith("projects/<number>/secrets/deployer-")` to the binding.

### API, dashboard, MCP

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| PATCH | `/projects/{pid}/apps/{id}` | admin+ for `cloud_secrets` | `{cloud_secrets: true, confirm_billing: true}` / `{cloud_secrets: false}` | `App & {env_deployment_id}`; `422 billing_not_confirmed` (with the cost note), `422` on a static target |
| POST | `/projects/{pid}/apps` | admin+ | `cloud_secrets?: true` with the usual `confirm_billing: true` of a cloud target | `App` (201) |

Apps' `cloud` gains `secrets: {enabled, store, note, cost, stored: [names]} | null` (null outside App Runner /
Cloud Run); deployments gain the trigger `env`; `PATCH` returns `env_deployment_id`. Dashboard: the Environment
card of an App Runner / Cloud Run app has the tick with the cost and the names in the store, its save toast
says the live version is being republished, the Deploys table labels `env` deployments *Environment*, the
"Where it builds" note says changed variables are applied right away, and Settings -> Cloud accounts marks the
new Google role and API. MCP: `set_app_secrets_store` (project admin, like its route; `app_id`, `enabled`,
`confirm_billing` - the description tells the agent to get the user's agreement first). See MCP.md.

### Not verified against real clouds

Tested with the fakes (`tests/test_cloud_secrets.py`: which values go to the store, the references and the
role statement, nothing in logs or responses, the `env` deployment on a variable change - also for a
GitHub-built app - stale secrets deleted after the rollout, switching off, teardown on delete / move, the
billing confirmation and roles, MCP, the policy statements), the real `AwsClient` secret calls against
botocore's models (`Stubber`: create / exists-unchanged / exists-changed / delete / already gone) and the real
`GcpClient` secret calls against `httpx.MockTransport` (paths, bodies, the unchanged-value check, the Cloud
Run `secretKeyRef` body). Not yet run for real: App Runner taking `RuntimeEnvironmentSecrets` together with
an instance role created in the same `UpdateService`, Cloud Run's permission check on `secretKeyRef` at
revision time, and `versions/latest:access` on a secret whose latest version was disabled in the console.
## G3 as built: a permissions boundary for the roles Deployer creates

### The threat

Deployer's AWS key creates IAM roles and writes their policies itself: the shared App Runner access role
`deployer-apprunner-ecr-access` (C1), one instance role `deployer-app-<slug>-<id8>` per App Runner app that uses
DynamoDB tables (C2-2) and one `deployer-gha-<slug>-<id8>` role per app that builds on GitHub Actions (C3). A role's
policy is whatever `PutRolePolicy` says, so a bug in Deployer, a future change that widens a policy by mistake, or
anyone who got hold of the key (it is stored encrypted on this PC, but the PC is the trust boundary) could give one
of those roles far more than its app or workflow needs - and an App Runner app or a GitHub workflow then runs with
it, outside this PC, with the PC off. The key itself is already limited to `deployer-*` resources by
its policies, but `iam:PutRolePolicy` on `role/deployer-app-*` was a way around that: the policy text is
free, and the role is assumed by code Deployer does not control.

### The fix: `deployer-boundary`

IAM's answer is a **permissions boundary**: a managed policy attached to a role as its ceiling - the role may do
only what both its own policies *and* the boundary allow, and the boundary cannot grant anything by itself.

- `cloud_aws.BOUNDARY_DOCUMENT` (shown in Settings -> Cloud accounts, `GET /instance/cloud/requirements` ->
  `aws.boundary`) is the most any role Deployer creates may do: `ecr:GetAuthorizationToken`; push and pull on
  `repository/deployer-*`; `DescribeService` / `UpdateService` / `ListOperations` on `service/deployer-*`;
  `iam:PassRole` of the access role only; list / get / put / delete objects on `deployer-*` buckets;
  `GetDistributionConfig` / `UpdateDistribution` / `CreateInvalidation` (distributions have ids, not names, so `*`:
  each role's own policy names its one distribution); `secretsmanager:GetSecretValue` / `DescribeSecret` on
  `secret:deployer-*` (what G1's secret references need); DynamoDB **item** operations and `DescribeTable` on any
  table (connected tables keep their own names; the instance role's own policy names exactly the project's
  tables; never `CreateTable` / `DeleteTable`). Nothing in IAM, nothing that creates or deletes services,
  buckets, tables or repositories; RDS is reached with the database password in the environment, not IAM
  authentication, and App Runner writes the app's logs itself, so neither is in the ceiling.
- `AwsClient.ensure_boundary(account)` creates the managed policy **`deployer-boundary`** once per account
  (`CreatePolicy`; `EntityAlreadyExists` is fine) and returns its ARN plus whether the account's copy still
  matches this version's document (`GetPolicy` + `GetPolicyVersion` of the default version). It runs **when the
  AWS connection is saved or checked** (`cloud.validate`, failure ignored: a key whose policy predates G3 still
  saves, and the first deploy reports the missing permission) as well as before every deploy and GitHub Actions
  setup: the key may create the boundary only while none exists, so if that window stayed open until the first
  app deploy, a copy of the key could create a wider `deployer-boundary` first and build unbounded roles with it -
  for ever, in an account that only holds databases. **Deployer never
  changes it**: a key that could rewrite the boundary could lift it, so the IAM user has no `CreatePolicyVersion`,
  `SetDefaultPolicyVersion`, `DeletePolicy` or `DeletePolicyVersion`. When a later Deployer version needs more in
  the boundary (G1's secrets, say), the build log says *the IAM policy deployer-boundary in your AWS account is
  older than this version of Deployer expects* and the owner pastes the new JSON over it in the IAM console (the
  guide shows it). Owners who prefer that the key never writes the boundary create it from that JSON before the
  first deploy.
- Every role Deployer creates is created with `PermissionsBoundary = <that ARN>` (`ensure_access_role`,
  `ensure_instance_role`, `ensure_github_role`), and a role that already exists without it - made before G3 -
  gets it with `PutRolePermissionsBoundary` the next time Deployer touches it: the access role and the instance
  role on the app's next deploy or rollback (`cloud_deploy.aws_app` now checks the access role every deploy
  instead of once), the GitHub Actions role when its setup runs again (a build-setting change, or switching
  GitHub Actions off and on). The deploy ensures the boundary before any role, so an account where the key may
  not create it fails the deploy with AWS's message instead of creating an uncapped role.
- The key's policies (since the split: `DeployerRoles`, which holds every IAM statement) only allow `iam:CreateRole`, `PutRolePolicy`, `AttachRolePolicy` and
  `PutRolePermissionsBoundary` on the three role families (one statement `RolesWithinBoundary`) with the
  condition `ArnLike: iam:PermissionsBoundary = arn:aws:iam::*:policy/deployer-boundary` - IAM refuses the call
  unless the role carries (or is being created with) exactly that boundary. These four actions appear nowhere
  else in any of the policies (test-enforced), and the statement is `ArnLike`, not `...IfExists`: a request without a
  boundary must fail, which `IfExists` would let through. `GetRole`, `TagRole`, `PassRole`,
  `UpdateAssumeRolePolicy`, `DeleteRolePolicy` and `DeleteRole` stay unconditional in their families' statements
  (reading, tagging, passing and removing permissions cannot escalate, and a teardown must still remove a role made
  before G3); `DeleteRolePermissionsBoundary` is absent. The new statement `BoundaryPolicy` allows `CreatePolicy`,
  `GetPolicy`, `GetPolicyVersion` on `policy/deployer-boundary` only. (At about 6,100 of IAM's 6,144 characters
  this filled the single policy; "AWS policy split as built" below split it.)

What this does **not** cover: the key's own direct permissions (S3, CloudFront, ECR, App Runner, RDS, DynamoDB,
EC2 security groups) are limited by the key's policies alone, as before; a boundary is for the roles. On Google there is
no equivalent: the GitHub Actions workflow acts as the deployer service account itself (C3 says so in the dialog).

### Dashboard, API

Settings -> Cloud accounts, AWS step 2 explains the ceiling in plain words and shows the `deployer-boundary` JSON
under the user policy (create it yourself first, or paste it over an older copy). `GET /instance/cloud/requirements`
returns `aws: {policy, boundary, boundary_name}` (`policies` since the split). No new routes, MCP tools or migrations.

### Not verified against real clouds

Tested in `tests/test_cloud_boundary.py`: `ensure_boundary`, `ensure_access_role`, `ensure_instance_role` and
`ensure_github_role` run the real `AwsClient` bodies against botocore's IAM service model with `Stubber` (so a wrong
operation or parameter name fails), including a pre-G3 role receiving the boundary and an outdated copy being
reported; the shape of the AWS policies (the four role-writing actions only under the `ArnLike` condition, no
escalation actions anywhere, the boundary policy read-only); the boundary document's own scope; and
the deploy wiring with the fake (the boundary before any role, the log line for an older copy, a refused
`CreatePolicy` failing the deploy before anything else is made). The GitHub Actions setup passing the boundary is
in `tests/test_github_actions.py`. Not run against a live account: that IAM's evaluation of
`iam:PermissionsBoundary` with `ArnLike` behaves as the documentation and the policy simulator describe for
`CreateRole` / `PutRolePolicy` / `AttachRolePolicy` / `PutRolePermissionsBoundary` (the condition key is listed for
all four), that App Runner accepts an instance role carrying a boundary, and the real `GetPolicyVersion` document
decoding (botocore returns it as a dict; a string is handled too).

## AWS policy split as built: purpose-sized managed policies

### Why

IAM caps a customer managed policy at 6,144 characters (whitespace not counted). The single `DeployerHosting`
policy had reached about 6,125 after G3, so no further permission fitted. An IAM user can have up to 10 managed
policies attached, so the permissions are now three policies, one per purpose:

| Policy | What for | Statements |
|---|---|---|
| `DeployerHosting` | static sites, container images, App Runner services, app secrets | `WhoAmI`, `StaticSiteBuckets`, `CloudFront`, `Certificates`, `RegistryLogin`, `ContainerRepositories`, `AppRunner`, `AppSecrets` |
| `DeployerDatabases` | RDS / Aurora and their firewall, DynamoDB tables, backups, restores, the gateway endpoint | `DatabasesRead`, `Databases`, `DatabaseFirewall*`, `DynamoDB*` |
| `DeployerRoles` | every IAM permission: the roles Deployer creates, always within `deployer-boundary` (G3), GitHub Actions sign-in, service-linked roles | `AppRunnerImageAccessRole`, `RolesWithinBoundary`, `BoundaryPolicy`, `ServiceLinkedRoles`, `AppRunnerInstanceRoles`, `GitHubActionsSignIn`, `GitHubActionsRoles` |

The statements are exactly the previous ones, moved verbatim: nothing added, removed or changed. Every `iam:*`
action is in `DeployerRoles`, so the G3 boundary condition on `RolesWithinBoundary` is reviewed in one place.

### Code, API, dashboard

- `services/cloud.py`: `AWS_HOSTING_STATEMENTS`, `AWS_DATABASE_STATEMENTS`, `AWS_ROLE_STATEMENTS` and
  `AWS_POLICIES = [{name, for, document}]`. **A new permission goes into the statement list whose purpose it
  serves**; when one runs out of room, add a new entry to `AWS_POLICIES` (and say in the guide what owners must
  create) rather than squeezing. `cloud.AWS_POLICY` is gone; tests read `cloud.aws_statements()` (all statements).
- `GET /instance/cloud/requirements` returns `aws: {policies: [{name, for, document}], boundary, boundary_name}`
  instead of `aws.policy`. The only reader is the dashboard, which ships with the API.
- Settings -> Cloud accounts, AWS step 2: create each policy with the name shown and attach all of them to the
  `deployer` user. Owners who pasted the old single `DeployerHosting` policy are told what to do: create and attach
  `DeployerDatabases` and `DeployerRoles` first, then replace `DeployerHosting`'s JSON with the new, shorter one
  (in that order nothing stops working in between). Until they do, the old policy keeps working as before; only
  permissions added after the split would be missing.
- No migration, no MCP change, no change to `deployer-boundary`.

### Tests

`tests/test_cloud_policies.py`: every policy's minified size is at most 6,144 - 600 characters (600 of headroom
each; today about 2,150 / 2,490 / 1,570), at most 10 policies, unique names; the union of the statements equals
the pre-split statement set (statement ids plus a SHA-256 of their exact contents; a statement added later goes
into `ADDED_SINCE_SPLIT`, a deliberately changed one updates the fingerprint), no statement in two policies; and
every `iam:*` action sits in `DeployerRoles`.

### Not verified against real clouds

Not run against a live account: that IAM accepts each document as a managed policy (sizes are computed the way
the IAM documentation describes: whitespace not counted) and that three attached policies grant the same as the
one before (IAM evaluates the union of attached policies, so it should).
