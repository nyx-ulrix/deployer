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
| C2 | Firebase Realtime Database | Planned ("C2 - cloud databases") |
| C3 | GitHub Actions builds, so pushes deploy with the PC off | Planned ("C3 - GitHub Actions builds") |

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
  project** (C2-3). The dashboard says so next to the target chooser and in the Environment card. The
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
switched off when an app moves to one) - except `database_access` on `aws_app`, which since C2-1 means the
project's AWS databases, and on `firebase_app`, which since C2-3 means the project's Firestore databases. Moving an app (target or connection) needs no running
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

## C2-1 as built: cloud databases in AWS (RDS / Aurora)

### Data model

A cloud database is an ordinary **`external`** data source - so the SQL browser, query console, schema,
DDL export and the data API work through the normal external-source path - with two new columns
(migration `0013`): `data_sources.cloud_connection_id` (FK `cloud_connections`, `SET NULL`) and
`cloud_state` (JSON, never secrets). `status` gains `creating`. `config_encrypted` holds the usual
`{host, port, username, password, database, tls: true, tls_verify: false}` (`encrypt_json`); the
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
project** (shown as coming soon). In AWS the user picks the account (the project's AWS connections) and:

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
database is still being created. Deleting a **project** is refused (`409 cloud_resources_left`, naming
them) while it still has databases Deployer created in AWS or apps with cloud resources: removing those
first runs their cleanup, so nothing is left running and billed with no record of it.

### Networking (the trade-off)

Requirement: this PC must browse / query the database **and** App Runner apps must reach it, with the
PC off for the apps. Design:

- **The PC** connects to a *publicly accessible* endpoint whose security group lets in only the PC's
  current public IP `/32`. The scheduler checks the IP every 5 minutes (`cloud_db.refresh_pc_ips`, also
  on **Check status**): when it changed, the new IP is allowed and the old one revoked. Connections use
  TLS; Deployer does not verify the RDS certificate yet (RDS signs with its own CA, which is not in the
  system store - encrypted but not authenticated, like PostgreSQL's `sslmode=require`; follow-up: pin
  the RDS CA bundle).
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
encrypted by App Runner; follow-up: Secrets Manager references). The deploy then ensures the VPC
connector, lets its security group into each created database's group, and creates / updates the
service with `EgressType: VPC` (back to `DEFAULT` once database access is off). A connected (not
created) database's firewall is the user's: the build log names the connector's security group to
allow. A database still `creating`, in another account or in another VPC is skipped with a log line.
Other cloud targets still refuse database access. Moving an app to `aws_app` keeps its database-access
switch.

### Permissions added (`cloud.AWS_POLICY`, shown in Settings -> Cloud accounts)

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
resource_kind, region, instance_class, allowed_ip, job_id, resources, when_pc_off} | null`.
`DELETE .../data-sources/{id}` of a created one returns `{ok, job}` (`data_source.cloud_delete`), and
`409 cloud_database_creating` while it is being created; the connection details and data routes answer
`409 cloud_database_creating` until it is ready.

### MCP

`cloud_database_options`, `list_cloud_databases` (`connection_id`), `create_cloud_database`
(`connection_id, name, engine, instance_class?, confirm_billing` - billable: the tool description tells
the agent to get the user's agreement first; `confirm_billing: false` returns `billing_not_confirmed`),
`connect_cloud_database`; `list_data_sources` adds `cloud` for cloud databases. Service keys (developer
role), as planned. Deleting a cloud database stays a dashboard action.

### Not verified against real clouds

Tested against a fake AWS client (`tests/test_cloud_db.py`: create sequence and parameters, billing
confirmation, IP refresh, delete with snapshot and failure report, connect, App Runner env + connector,
MCP, migration). Not yet run against a live account: the RDS / EC2 / App Runner VPC connector request
shapes, whether App Runner accepts every default-VPC subnet for a connector (some AZs are unsupported in
a few regions), the `ALTER USER ... REQUIRE SSL` step on RDS, and the time AWS takes.

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
table or one). Restoring is in the AWS console (DynamoDB -> Backups -> Restore creates a new table, which can
then be connected here); the card says so. Point-in-time recovery is not switched on (it costs about 20%
of the storage price; follow-up).

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

### Permissions added (`cloud.AWS_POLICY`)

`dynamodb:ListTables`, `ListBackups` (`*`: AWS has no resource-level permissions for them);
`DescribeTable`, `GetItem`, `Query`, `Scan`, `PutItem`, `UpdateItem`, `DeleteItem`, `CreateBackup`,
`DescribeBackup` on `table/*` and `table/*/backup/*` - any
table, because connected tables keep their own names (a source still only uses its own); `CreateTable`,
`UpdateTable`, `DeleteTable`, `TagResource` only on `table/deployer-*`; `iam:GetRole`, `CreateRole`,
`TagRole`, `PutRolePolicy`, `DeleteRolePolicy`, `DeleteRole`, `PassRole` only on `role/deployer-app-*`;
`ec2:DescribeVpcEndpoints`, `DescribeRouteTables` (read) and `ec2:CreateVpcEndpoint` + `CreateTags` (only
while creating an endpoint) for the gateway endpoint. The policy stays under IAM's 6,144-character limit
(test-enforced). Owners paste the new policy over the old one (the guide says so).

### API

| Method | Path | Role | Body / Query | Response |
|---|---|---|---|---|
| POST | `/projects/{pid}/cloud/databases` | admin+ | `{connection_id, name, engine: "dynamodb", partition_key?: {name, type: S\|N\|B}, sort_key?, confirm_billing: true}` | `{data_source, job}` (201) |
| POST | `/projects/{pid}/cloud/databases/connect` | admin+ | `{connection_id, name, tables: [...]}` | `DataSource` (201); `400 connection_failed` names the table AWS refused |
| GET | `/projects/{pid}/data-sources/{sid}/cloud-backups` | viewer+ | – | `{backups: [{table, arn, name, status, type, size_bytes, created_at}], cost, restore}` |
| POST | `/projects/{pid}/data-sources/{sid}/cloud-backups` | admin+ | `{table?, confirm_billing: true}` | `{backups}` (201); audit `data_source.cloud_backup` |
| GET | `/projects/{pid}/data-sources/{sid}/collections/{table}/documents` | viewer+ / API keys | `filter?`, `limit`, `cursor?` | `{documents, total, key, next_cursor}` |

`GET .../cloud/databases/options` adds `dynamodb: {what, keys, key_types, cost, network}`; the
listing adds `tables` and `tables_problem`; data sources' `cloud` adds `tables` and `resource_kind:
"table"`. Editing a DynamoDB source's connection settings is refused (rename only).

### MCP

`create_cloud_database` takes `engine: "dynamodb"` with `partition_key` / `sort_key`,
`connect_cloud_database` takes `tables`, `list_cloud_databases` returns `tables`, `list_documents` takes
`cursor`, `run_query` takes the JSON request, plus `list_cloud_backups` (any key) and
`create_cloud_backup` (service key; billable, `confirm_billing`). See MCP.md.

### Not verified against real clouds

Tested against an in-memory DynamoDB behind the `ddb` seam (`tests/test_dynamo.py`: create / delete with
a final backup, connect, paging, Query vs Scan, insert / update / delete, value round trips, the console
and its read-only rule, schema, backups, the App Runner role and gateway endpoint, MCP, policy size). Not
yet run against a live account: the exact request shapes (botocore validates parameters, the fake does
not), App Runner taking the instance role on an existing service, and the gateway endpoint on default
VPCs.

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

Deployer **never creates or deletes** a Firestore database (create it in the Firebase console: Build ->
Firestore Database -> Create database). Removing the source only forgets it; nothing in Google changes, so
there is no cleanup job and project deletion is not blocked by it.

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
`cloud_db.LOCATIONS`; the dialog greys it out for SQL and says Realtime Database is coming). The section
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
  when more were left). Plain JSON in the same `$` forms, so documents can be inserted again. A managed
  export to a Cloud Storage bucket is not built (follow-up).
- **Connection details** show the project id, database id, endpoint and location - no URI, user or password.
- **Backups**: the Backups tab shows the "up to their provider" note; Firestore's own scheduled backups and
  point-in-time recovery are set up in the Google Cloud console (not managed by Deployer yet).

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

## C2 - cloud databases (planned)

| Provider | Engine | Support |
|---|---|---|
| AWS | **RDS / Aurora** MySQL, MariaDB, PostgreSQL | **built in C2-1** (above) |
| AWS | **DynamoDB** | **built in C2-2** (above) |
| Firebase | **Cloud Firestore** | **built in C2-3** (above) |
| Firebase | **Realtime Database** | new engine: JSON tree browse/edit, path queries |

Seams left by C1 and C2-1..3: data sources carry `cloud_connection_id` / `cloud_state` and the Add
database dialog has the AWS / Firebase cards (`cloud_db.LOCATIONS`); cloud apps get their database
settings through `cloud_deploy.cloud_env` (`cloud.DATABASE_TARGETS`); the MCP `create_cloud_database` tool
and the `confirm_billing` rule are in place; a NoSQL engine without its own driver is one module with the
functions of `services/dynamo.py` / `services/firestore.py`, returned by `connections.cloud_engine`.
Left: the Realtime Database engine, creating Firestore databases and their managed exports / scheduled
backups from Deployer, and Secrets Manager / Secret Manager references instead of plain runtime
environment.

## C3 - GitHub Actions builds (planned)

Each cloud app picks where it builds: *This PC* (C1, the worker builds, pushes and rolls out) or
*GitHub Actions* (Deployer commits a workflow that builds and deploys on every push with GitHub OIDC →
AWS role / Google workload identity, so pushes deploy even when the PC is off). Seams left by C1:
`cloud_deploy.go_live` publishes from an artifact reference (the same path rollbacks use), so a
workflow that pushes the image / uploads the site only needs the rollout half; `apps.cloud_state` holds
the ids the workflow needs; the role / identity provider joins `cloud.AWS_POLICY` and the Google roles.
