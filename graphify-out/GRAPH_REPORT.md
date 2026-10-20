# Graph Report - Deployer  (2026-10-21)

## Corpus Check
- 500 files · ~622,822 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 8592 nodes · 28362 edges · 271 communities (243 shown, 28 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 1827 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3352dedb`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- CloudAccountsPage.tsx
- App.tsx
- useToast
- types.ts
- source_sync.py
- oauth.py
- cn
- device_host.py
- apps.py
- FlatButton
- is_online
- client.ts
- utcnow
- test_github_integration.py
- rtdb.py
- RestoreDialog.tsx
- docs/PLATFORMS.md - Platforms and accounts this project uses
- SchemaTab.tsx
- CloudflareSetup.tsx
- data_browser.py
- deploys.ts
- CloudError
- mcp.py
- services/remote_access.py
- get_redis
- ControlForm
- ApiError
- Publish
- get_settings
- _wrap
- firestore.py
- run_job
- CloudflareClient
- device_rpc.py
- deployer.sh
- connection
- WizardForm
- .Rebuild
- services/__init__.py
- dynamo.py
- github_actions.py
- auth_headers
- test_data_api_keys.py
- run_queued
- test_source_sync.py
- MCP.md
- README.md
- firestore_admin.py
- routers/backups.py
- FakeCloud
- build_export_file
- test_rds_tls.py
- models.py
- schema_ops.py
- BackupExecutor
- docs/ARCHITECTURE.md - Deployer Architecture
- services/transfer.py
- crowsfoot.ts
- Deployer HTTP API v1
- Integration
- backup_crypto.py
- NotebookConsole.tsx
- deployments.py
- factory
- _TempArtifact
- common.ps1
- test_dynamo.py
- MembersTab.tsx
- docker-compose.yml (production stack)
- test_query_log.py
- _call
- test_setup.py
- DockerCli
- ddl_export.py
- source_ops.py
- test_firestore_admin.py
- _Writer
- set_setting
- make_project
- aws_statements
- Deployments (push-to-deploy) — phase 4
- query_console.py
- query_log.py
- test_remote_access.py
- tests/test_query_console.py
- test_oauth.py
- Write-DeployerInfo
- UninstallForm
- introspection.py
- FakeCloudflare
- Write-DeployerWarn
- test_devices_agent.py
- Path
- By section
- DumpScanner
- connections.py
- executors.py
- shell_runner.py
- .TestMarkers
- device_worker.py
- record
- PitrFake
- device_local.py
- conventions.py
- DeviceExecutor
- saved_queries.py
- cohost_problem
- test_github_actions.py
- Invoke-Update
- .Ask
- CaddyProxyHeaders
- run
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- ._c
- mongo_snapshot
- AwsClient
- test_devices_local.py
- test_firestore.py
- SchemaDiffView.tsx
- compilerOptions
- cloud_deploy.py
- test_rtdb.py
- create_replica
- OutputWindow
- How the main code paths work
- test_backups_engine.py
- cloud_secrets.py
- FakeDockerCli
- integration/test_query_console.py
- dependencies
- Get-DeployerSource
- setup_import
- compilerOptions
- NativeMethods
- test_data_sources.py
- devDependencies
- routers/remote_access.py
- cloud_aws.py
- create_app
- Remote Access & Custom Domains (Cloudflare)
- test_conventions.py
- test_transfer_stream.py
- DeployerSetup
- supervisor.sh
- .get
- _replay_binlogs
- gcp_for
- test_projects.py
- test_mcp.py
- github_repos
- field_validator
- _clean_up_slot
- key_hash
- apiSnippets.ts
- HANDOVER.md
- test_device_rpc.py
- backup_engine.py
- .value
- Data API with API keys
- cancel_job
- LocalExecutor
- API runtime dependencies (requirements.txt)
- test_container_config.py
- query/diff.ts
- Cloud hosting and databases (AWS, Firebase)
- wslplatform.tests.ps1
- sweep_orphans
- Write-DeployerLog
- Any
- C2-3 as built: Cloud Firestore
- Deploy a website with Deployer
- .delete_nat_gateway
- C3 as built: GitHub Actions builds (pushes deploy with the PC off)
- C2-1 as built: cloud databases in AWS (RDS / Aurora)
- C1 as built
- lan.tests.ps1
- Condition
- .transfer
- test_devices_enrollment.py
- fix_state_ownership
- test_migration_table_options.py
- main
- apply_changes
- fake_device
- test_api_docs_routes.py
- test_release_workflow.py
- scripts
- DataSource
- TempFileResponse
- .create_service
- dec
- exports_dir
- test_dead_code.py
- C2-2 as built: DynamoDB
- C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway)
- 0010_cohost_apps.py
- test_fixture_layout.py
- test_query_docs.py
- test_skill_doc.py
- test_version.py
- package.json
- setup-engine.sh
- 0011_cloud.py
- 0012_datetime_microseconds.py
- test_migrations_mariadb.py
- test_ci_workflow.py
- test_docs_index.py
- test_roadmap_doc.py
- tsconfig.json
- docker-entrypoint.sh
- scheduler_tick
- .ensure_github_role
- eslint-plugin-react-refresh
- globals
- tailwindcss
- @tailwindcss/vite
- @types/react-dom
- entrypoint.sh
- upgrade.sh
- CI workflow
- Release workflow (v* tags)
- deployer-api
- handle
- .ensure_vpc_connector
- C2-4 as built: Firebase Realtime Database
- test_source_ops.py
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
- check
- id_candidates
- _fake_binlog
- .__init__
- test_big_mongo_document_is_sent_in_a_batch_of_its_own
- .__init__
- Firestore point-in-time recovery and deletes (as built)
- G1 as built: app secrets in a secret store, environment changes without a rollback
- C2-5 as built: MCP, transfer, project delete
- Settings
- eslint
- heartbeat
- G3 as built: a permissions boundary for the roles Deployer creates
- main
- @tanstack/react-query

## God Nodes (most connected - your core abstractions)
1. `ApiError` - 509 edges
2. `utcnow()` - 182 edges
3. `useToast()` - 152 edges
4. `cn()` - 152 edges
5. `errorMessage()` - 146 edges
6. `get_settings()` - 132 edges
7. `DataSource` - 130 edges
8. `ProjectAccess` - 116 edges
9. `record()` - 108 edges
10. `run_queued()` - 101 edges

## Surprising Connections (you probably didn't know these)
- `Host devices (spare PCs, outbound connection)` --semantically_similar_to--> `Open from any device with your own domain (Cloudflare tunnel)`  [INFERRED] [semantically similar]
  README.md → docs/SETUP.md
- `Hard rule: always ask which platform to deploy to` --semantically_similar_to--> `Billable tools need confirm_billing true after the user agrees`  [INFERRED] [semantically similar]
  skills/deploy-website/SKILL.md → docs/MCP.md
- `Guiding rules (self-contained, free by default, one control plane, portable)` --semantically_similar_to--> `Ground rules`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → CONTRIBUTING.md
- `Pick the computer (Windows PC vs Linux server requirements)` --semantically_similar_to--> `Requirements`  [INFERRED] [semantically similar]
  docs/SETUP.md → README.md
- `deployer-deploy.zip release asset` --references--> `docker-compose.yml (production stack)`  [INFERRED]
  .github/workflows/release.yml → deploy/docker-compose.yml

## Import Cycles
- 3-file cycle: `api/app/services/deployments.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 3-file cycle: `api/app/services/device_host.py -> api/app/services/transfer.py -> api/app/services/devices.py -> api/app/services/device_host.py`
- 4-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 4-file cycle: `api/app/services/deployments.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 4-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/device_moves.py -> api/app/services/backups.py`
- 4-file cycle: `api/app/services/cohosting.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py`
- 4-file cycle: `api/app/services/cohost_apps.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/cloud_db.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py -> api/app/services/cloud_db.py`
- 5-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/device_apps.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`

## Hyperedges (group relationships)
- **Release pipeline: CI gate, images, setup exe, bundle** — _github_workflows_release_tests, _github_workflows_release_images, _github_workflows_release_setup_exe, github_workflows_release_bundle [EXTRACTED 1.00]
- **MCP billable tools gated by confirm_billing** — docs_mcp_confirm_billing_pattern, docs_mcp_tool_set_app_target, docs_mcp_tool_create_cloud_database, docs_mcp_tool_set_build_location, docs_mcp_tool_set_app_secrets_store, docs_mcp_tool_set_app_internet_access [EXTRACTED 1.00]
- **Secrets encrypted at rest with MASTER_KEY** — docs_platforms_master_key, docs_platforms_table_instance_settings, docs_platforms_table_github_connections, docs_platforms_table_apps, docs_platforms_table_cloud_connections, docs_platforms_table_data_sources [EXTRACTED 1.00]
- **Backup protection layers for a managed database** — docs_backups_snapshots, docs_backups_pitr, docs_backups_safety_snapshots, docs_backups_recently_deleted, docs_backups_platform_backup, docs_backups_verification [EXTRACTED 1.00]
- **Device runtime protocol (control channel, RPC routing, methods, transfers)** — docs_devices_control_channel, docs_devices_rpc_routing, docs_devices_rpc_methods, docs_devices_bulk_transfers [EXTRACTED 1.00]
- **Cloudflare tunnel stack (link, sidecar, supervisor, handshake files, Caddy 8081)** — docs_remote_access_link_step, docs_remote_access_tunnel_sidecar, docs_remote_access_supervisor, docs_remote_access_desired_status_files, docs_remote_access_caddy_8081 [INFERRED 0.85]

## Communities (271 total, 28 thin omitted)

### Community 0 - "CloudAccountsPage.tsx"
Cohesion: 0.05
Nodes (54): useInstanceSettings(), useProjects(), CloudProvider, ImportSummary, ProviderSettings, ExtLink(), StepStatus, AlertSettingsCard() (+46 more)

### Community 1 - "App.tsx"
Cohesion: 0.04
Nodes (84): ApiError, isApiError(), isApiStarting(), useProviders(), useSetupStatus(), Identity, ProviderName, App() (+76 more)

### Community 2 - "useToast"
Cohesion: 0.04
Nodes (93): errorMessage(), useQueryLog(), AppReplica, AppSecrets, DnsRecord, FirestoreBackup, JsonObject, JsonValue (+85 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (137): buildQuery(), client, createApiClient(), filenameFromDisposition(), Call, ApiKey, ApiKeyConfig, ApiKeyCreateResponse (+129 more)

### Community 4 - "source_sync.py"
Cohesion: 0.04
Nodes (93): Device, A row/document changed on both copies since their last common version (like a…, A version of a row/document the sync applied or confirmed (base for conflict…, SourceReplica, SyncConflict, SyncVersion, BaseModel, ReplicaCreate (+85 more)

### Community 5 - "oauth.py"
Cohesion: 0.02
Nodes (214): sha256_hex(), client_ip(), The peer address. Behind Caddy, main.CaddyProxyHeaders has already set it from…, RefreshToken, UserIdentity, change_password(), LinkIn, login() (+206 more)

### Community 6 - "cn"
Cohesion: 0.03
Nodes (146): hasLiveReplica(), useApp(), useApps(), useDataSourcesWithReplicas(), useDeployment(), useDeployments(), useDevices(), useSyncConflict() (+138 more)

### Community 7 - "device_host.py"
Cohesion: 0.04
Nodes (129): _detach(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore(), Local administration commands, run inside the api container. python -m app.cli… (+121 more)

### Community 8 - "apps.py"
Cohesion: 0.08
Nodes (72): _actions_report(), add_domain(), _audit_cohost(), _audit_database_access(), cancel_deployment(), _check_api_key_access(), _check_billing(), _check_database_access() (+64 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (45): Control, FontStyle, GraphicsPath, IButtonControl, IDeviceContext, PaintEventArgs, PaintEventArgs, Graphics (+37 more)

### Community 10 - "is_online"
Cohesion: 0.07
Nodes (56): approve_enrollment(), _can_remove_copy(), deny_enrollment(), _enrollment_for_action(), get_device(), list_devices(), move_data_source(), placement_options() (+48 more)

### Community 11 - "client.ts"
Cohesion: 0.05
Nodes (108): ApiClientOptions, codeForStatus(), DownloadResult, FetchFn, isErrorBody(), parseError(), QueryValue, RequestOptions (+100 more)

### Community 12 - "utcnow"
Cohesion: 0.03
Nodes (188): Backup, BackupCopy, BackupLogSegment, BackupPolicy, new_id(), utcnow(), any_copy(), archive_source_logs() (+180 more)

### Community 13 - "test_github_integration.py"
Cohesion: 0.06
Nodes (55): GitHubConnection, A user's GitHub OAuth token for repository access (docs/DEPLOYMENTS.md "Connect…, _api(), apps_using(), _check_token_status(), delete_hook(), detect_draft(), get_connection() (+47 more)

### Community 14 - "rtdb.py"
Cohesion: 0.05
Nodes (98): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _json_or_text(), list_documents() (+90 more)

### Community 15 - "RestoreDialog.tsx"
Cohesion: 0.05
Nodes (74): usePlacementOptions(), Backup, BackupSchedule, DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability (+66 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.13
Nodes (35): Platform data model (UUID-keyed MariaDB tables), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), docs/PLATFORMS.md - Platforms and accounts this project uses, AWS hosting and databases, deployer-boundary IAM permissions boundary, Three AWS IAM policies: DeployerHosting, DeployerDatabases, DeployerRoles, Cloudflare tunnel and DNS, Cloudflare API token (four permissions) (+27 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.04
Nodes (86): useSchema(), ConventionIssue, labels, next, ThemeToggle(), initialMode(), subscribe(), ThemeProvider() (+78 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.11
Nodes (36): CloudflareZone, CloudflareSetup(), HostnameStep(), LinkStep(), PublicUrlStep(), TokenStep(), TunnelStep(), tunnelSummary() (+28 more)

### Community 19 - "data_browser.py"
Cohesion: 0.12
Nodes (51): check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document(), delete_row(), encode_value() (+43 more)

### Community 20 - "deploys.ts"
Cohesion: 0.06
Nodes (58): App, AppDetectDraft, AppPreset, AppTarget, CloudTarget, DeploymentStatus, DeploymentTrigger, GitHubRepo (+50 more)

### Community 21 - "CloudError"
Cohesion: 0.06
Nodes (33): CloudError, Exception, An AWS / Google Cloud call failed (docs/CLOUD.md). `message` is the provider's…, _api_error(), GcpClient, _name(), Any, The Google REST calls behind the Firebase hosting targets and databases… (+25 more)

### Community 22 - "mcp.py"
Cohesion: 0.08
Nodes (69): _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result(), _limit(), _mongo() (+61 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.08
Nodes (68): _add_cloud_domain(), docs/CLOUD.md "Custom domains": the target is asked for the hostname; with…, _active_hostnames(), add_hostname(), apps_tunnel_name(), _cached_zones(), _client(), connector_state() (+60 more)

### Community 24 - "get_redis"
Cohesion: 0.07
Nodes (54): get_redis(), active(), deliver(), deliver_async(), evaluate(), One evaluation round. Returns the (event, alert) pairs it sent ("open" /…, Open alerts (pending ones haven't lasted long enough yet), critical first., collect_metrics() (+46 more)

### Community 25 - "ControlForm"
Cohesion: 0.06
Nodes (22): ContextMenuStrip, IEnumerable, bool, DateTime, Dictionary, EventHandler, Form, IDictionary (+14 more)

### Community 26 - "ApiError"
Cohesion: 0.04
Nodes (168): AdminOrServiceKey, encrypt_json(), ApiError, Raise from handlers/services; rendered as {"error": {code, message, details}}., CloudConnection, A user's own AWS or Firebase/Google Cloud credentials (docs/CLOUD.md "Cloud…, _audit(), AwsCredentials (+160 more)

### Community 27 - "Publish"
Cohesion: 0.10
Nodes (21): cache_control(), content_type(), _export(), instance_role_name(), Publish, (relative path with /, absolute path) of the regular files under `root`.…, HTML revalidates every time; fingerprinted assets are immutable; everything…, One deployment's publish step; `artifact` / `url` are the results. (+13 more)

### Community 28 - "get_settings"
Cohesion: 0.04
Nodes (122): get_settings(), SECURITY.md "Query console": loads the Settings, then drops the secrets from…, seal_process(), Shared Redis client (OAuth state, rate limits, job queue). Always call…, _check_mariadb(), _check_mongodb(), _mongo_client(), None when MongoDB is switched off (no AVX CPU, or a Linux kernel MongoDB 8… (+114 more)

### Community 29 - "_wrap"
Cohesion: 0.07
Nodes (12): A DynamoDB gateway endpoint in the VPC (free, created once, shared): an App…, One DynamoDB API call by its AWS name (`Query`, `PutItem`, `CreateTable`...)…, Names of the account's `deployer-gha-*` roles that carry Deployer's tag (the…, botocore errors -> CloudError with AWS's code and message (no request data, no…, Bucket policy: only this CloudFront distribution (through its OAC) may read…, `{status, records: [{type, name, value}]}` (records appear a few seconds after…, (registry host, username, password) for `docker login --password-stdin`., PENDING | IN_PROGRESS | SUCCEEDED | FAILED | ROLLBACK_IN_PROGRESS |… (+4 more)

### Community 30 - "firestore.py"
Cohesion: 0.14
Nodes (42): _and(), _bad(), call(), check_path(), _cursor_in(), _cursor_out(), delete_document(), display() (+34 more)

### Community 31 - "run_job"
Cohesion: 0.14
Nodes (24): Runs the job in a thread of this process (tests replace this with `_run`)., _run(), _spawn(), claim(), heartbeat_key(), SessionFactory, Claims and runs one job. Returns the final status, or None if it was not…, Fails `running` jobs whose worker stopped heartbeating. Returns how many were… (+16 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.06
Nodes (25): CloudflareClient, CloudflareError, _cname_body(), Any, ApiError, Exception, Thin Cloudflare API v4 client (docs/REMOTE_ACCESS.md). Only the calls Deployer…, A DNS-only record a cloud target asks for (docs/CLOUD.md "Custom domains"):… (+17 more)

### Community 33 - "device_rpc.py"
Cohesion: 0.07
Nodes (49): dump_source(), DataSource, Path, Writes the source's data entry (transfer.py format) to a local gzip JSON file., restore_into(), call(), CallListener, calls_channel() (+41 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (67): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_compose() (+59 more)

### Community 35 - "connection"
Cohesion: 0.07
Nodes (70): Firebase Hosting site id (globally unique, <= 30 chars)., site_id(), make_app(), App, aws_key_id(), aws_secret(), docs/CLOUD.md "G3": the `deployer-boundary` permissions boundary. The IAM calls…, A copy of the key could otherwise create a wider `deployer-boundary` first and… (+62 more)

### Community 36 - "WizardForm"
Cohesion: 0.07
Nodes (26): Action, Func, int, SettingsDialog, Action, bool, Color, Control (+18 more)

### Community 37 - ".Rebuild"
Cohesion: 0.05
Nodes (31): float, Form, Action, Bitmap, bool, Color, Control, DialogResult (+23 more)

### Community 38 - "services/__init__.py"
Cohesion: 0.03
Nodes (127): api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), load_project_access(), ApiError (+119 more)

### Community 39 - "dynamo.py"
Cohesion: 0.11
Nodes (60): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), connection_info(), create_backups() (+52 more)

### Community 40 - "github_actions.py"
Cohesion: 0.07
Nodes (61): artifact_for(), audience(), _aws_identity(), aws_policy(), builds_on_github(), cancel_setup(), _cel(), check_can_build() (+53 more)

### Community 41 - "auth_headers"
Cohesion: 0.06
Nodes (55): auth_headers(), make_user(), _root_mysql(), test_managed_lifecycle_and_roundtrip(), test_project_create_and_delete_with_provisioning(), project_setup(), providers(), fixture (+47 more)

### Community 42 - "test_data_api_keys.py"
Cohesion: 0.11
Nodes (12): Project API keys on the data, query and schema routes (docs/DATA_API.md)., A-031: an anon key may be public, and each run can hold a query slot for up to…, docs/MONITORING.md: `api_key_rate_limit` requests per minute per key; 429 with…, A-004: an anon key reads every table and collection (no per-table allowlist…, A-018: browsers can call the data API with a key, but cookie/session routes…, test_acting_user_falls_back_to_owner(), test_anon_key_is_not_advertised_as_public(), test_cors_only_on_key_routes_and_without_credentials() (+4 more)

### Community 43 - "run_queued"
Cohesion: 0.06
Nodes (50): local_copy(), perform_verify(), Test hook: runs queued jobs in creation order in this thread, including jobs…, run_queued(), FakeExecutor, _iso(), datetime, Backup API and orchestration against a fake executor (no database servers or… (+42 more)

### Community 44 - "test_source_sync.py"
Cohesion: 0.22
Nodes (24): One round for one replica. Returns stats, or None when nothing ran (offline,…, sync_round(), _conflicts(), fixture, parametrize, Co-hosting sync engine (docs/COHOSTING.md) with in-process fakes for both…, Same row on both copies, already in sync (positions past it)., The echo of a write the sync made can arrive after the key moved on (the other… (+16 more)

### Community 45 - "MCP.md"
Cohesion: 0.14
Nodes (36): CI job: Linux installer (install, CLI, update, uninstall), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Billable tools need confirm_billing true after the user agrees, Connecting, Destructive tools: dry run, then exact name plus confirm_delete, JSON-RPC errors, Limits (+28 more)

### Community 46 - "README.md"
Cohesion: 0.06
Nodes (59): Docker Engine inside the deployer WSL distro (default runtime), Linux server platform (alternative to Windows PC), Windows PC platform (required unless Linux), docs/SETUP.md - Setting up Deployer, Cloudflare API token permissions (Tunnel Edit, Account Settings Read, DNS Edit, Zone Read), Open from any device with your own domain (Cloudflare tunnel), Deploy an app and connect an AI agent (MCP), The deployer command (CLI reference) (+51 more)

### Community 47 - "firestore_admin.py"
Cohesion: 0.08
Nodes (54): backup_delete_summary(), backup_out(), bucket_location(), _call(), clone_spec(), collection_ids(), create_schedule(), database_delete_summary() (+46 more)

### Community 48 - "routers/backups.py"
Cohesion: 0.12
Nodes (46): backup_schema(), create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup(), _download_name() (+38 more)

### Community 49 - "FakeCloud"
Cohesion: 0.12
Nodes (20): Any, Test hook: `client(config)` returns `factory(config)` (None restores the real…, set_factory(), Test hook: `client(config)` returns `factory(config)` (None restores the real…, set_factory(), aws(), aws(), fixture (+12 more)

### Community 50 - "build_export_file"
Cohesion: 0.16
Nodes (26): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), list_transfers(), _my_transfer_job(), _owned_projects(), projects_export() (+18 more)

### Community 51 - "test_rds_tls.py"
Cohesion: 0.12
Nodes (20): friendly_error(), _hint(), BaseException, A-106: one plain sentence on the likely cause of a connection error, or None…, A-106: a connection error as a plain hint followed by the (redacted) driver…, try_sql(), test_connection_errors_get_a_plain_hint_and_keep_the_driver_text(), test_try_sql_gives_up_quickly_on_a_silent_server() (+12 more)

### Community 52 - "models.py"
Cohesion: 0.03
Nodes (167): Base, get_engine(), Engine, ProjectAccess, ApiKey, App, AppReplica, AuditLog (+159 more)

### Community 53 - "schema_ops.py"
Cohesion: 0.14
Nodes (27): build_create_table(), check_collection_name(), check_identifier(), check_type(), _constraint_name(), create_collection(), create_table(), drop_collection() (+19 more)

### Community 54 - "BackupExecutor"
Cohesion: 0.11
Nodes (10): BackupExecutor, IO, Protocol, Create an empty database + dedicated user (restore as a new source). Returns…, `{used_bytes, free_bytes}` of the backup store., Byte-level backup work on the host of a database. All methods may block for a…, Archive closed binlog files / oplog entries of `database_name` newer than…, Restore into a temporary `verify_*` database, compare row counts, always drop… (+2 more)

### Community 55 - "docs/ARCHITECTURE.md - Deployer Architecture"
Cohesion: 0.11
Nodes (26): CI job: Windows installer checks and DeployerSetup.exe, Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Ground rules, Layout (+18 more)

### Community 56 - "services/transfer.py"
Cohesion: 0.03
Nodes (117): _b64d(), _b64e(), decrypt_json(), decrypt_secret(), decrypt_with_passphrase(), _derive(), encrypt_secret(), encrypt_stream_with_passphrase() (+109 more)

### Community 57 - "crowsfoot.ts"
Cohesion: 0.16
Nodes (16): LinkCardinality, RelationshipCardinality, Cardinality, describeEnds(), EndMarker, MARKER_LABEL, MARKER_NOTATION, markerPath() (+8 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.09
Nodes (47): Deployer HTTP API v1, Project API keys (dpl_role_random), Auth endpoints (signup, login, refresh, OAuth), Data sources endpoints and DataSourceInput, Error envelope and common error codes, Export and import endpoints, Health and setup endpoints, Instance settings and users endpoints (+39 more)

### Community 59 - "Integration"
Cohesion: 0.08
Nodes (7): Dictionary, IntPtr, string, StringBuilder, Integration, IShellLinkW, ShellLinkCoClass

### Community 60 - "backup_crypto.py"
Cohesion: 0.06
Nodes (49): backup_key(), DecryptingReader, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material(), iter_decrypt() (+41 more)

### Community 61 - "NotebookConsole.tsx"
Cohesion: 0.02
Nodes (226): isDeviceOffline(), useDataSources(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSourceSchema(), DataSourceKind, MongoQueryResponse (+218 more)

### Community 62 - "deployments.py"
Cohesion: 0.04
Nodes (127): conflict(), Removes passwords from driver error messages (and other text: `limit=None`…, redact(), allocate_port(), app_domains(), app_slug(), apps_dir(), _build() (+119 more)

### Community 63 - "factory"
Cohesion: 0.08
Nodes (52): _job_archive(), _job_copy(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify(), client() (+44 more)

### Community 64 - "_TempArtifact"
Cohesion: 0.13
Nodes (12): copy_artifact(), Any, IO, Path, PathLike, Stores bytes (already encrypted) at `ref` in the device's backup store. Returns…, `backups.register_copy_target` hook: copies an encrypted artifact between…, Binary file object for a downloaded artifact; the temp file is removed on close. (+4 more)

### Community 65 - "common.ps1"
Cohesion: 0.09
Nodes (39): Get-SystemFacts(), Add-DeployerFirewallRule(), Add-DeployerUserPath(), ConvertTo-DeployerArgument(), ConvertTo-DeployerWslPath(), Disable-DeployerLanAccess(), Enable-DeployerLanAccess(), Get-DeployerAcPowerIndex() (+31 more)

### Community 66 - "test_dynamo.py"
Cohesion: 0.16
Nodes (28): base(), connect(), docs_url(), DynamoDB engine, phase C2-2 (docs/CLOUD.md): tables created or connected as…, orders_source(), DataSource, DynamoDB point-in-time recovery and restores into a new table (docs/CLOUD.md…, A connected DynamoDB source of the table `orders`, made directly (no AWS call). (+20 more)

### Community 67 - "MembersTab.tsx"
Cohesion: 0.08
Nodes (27): useProject(), CloudRestoredFrom, InviteRole, Member, Role, { api }, flush(), info (+19 more)

### Community 68 - "docker-compose.yml (production stack)"
Cohesion: 0.11
Nodes (51): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, Integration tests may not be skipped (+43 more)

### Community 69 - "test_query_log.py"
Cohesion: 0.14
Nodes (18): `text` with every password literal, URI `user:password@` and connection-string…, redact(), console(), fixture, parametrize, QueryRun, Query log (docs/QUERY_EDITOR.md): every console run is logged; list/get/delete…, A-031: a run keeps at most STORED_TEXT_LIMIT chars, and a crowded project is… (+10 more)

### Community 70 - "_call"
Cohesion: 0.31
Nodes (9): _call(), delete_file(), dispatch_workflow(), put_file(), One API call that must answer one of `ok`; anything else is a GitHubError with…, Creates or updates `path` on `branch`; returns the commit sha (None when the…, The newest runs of one workflow (queued, in progress and finished)., _repo_path() (+1 more)

### Community 71 - "test_setup.py"
Cohesion: 0.07
Nodes (21): login(), A-003: the forgotten-password recovery run on the Deployer PC (deployer reset-…, _refresh(), test_change_password(), test_logout_revokes(), test_refresh_cookie_secure_follows_request_scheme(), test_refresh_rotates_and_detects_reuse(), test_refresh_without_cookie_or_unknown() (+13 more)

### Community 72 - "DockerCli"
Cohesion: 0.07
Nodes (24): DockerCli, DockerError, _git_env(), parse_size(), _percent(), RuntimeError, (sha, first line of the commit message) of HEAD., Copies `path` out of `image` into the new directory `dest` (docs/CLOUD.md: a… (+16 more)

### Community 73 - "ddl_export.py"
Cohesion: 0.10
Nodes (41): build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources(), export_sql_source() (+33 more)

### Community 74 - "source_ops.py"
Cohesion: 0.14
Nodes (45): cloud_engine(), get_mongo_db(), get_sql_engine(), Engine, The adapter module of an engine reached only through its cloud connection, with…, check_status(), connection_info(), create_collection() (+37 more)

### Community 75 - "test_firestore_admin.py"
Cohesion: 0.09
Nodes (34): BaseTransport, Test hook: route the real client's HTTP through this transport., set_transport(), The real GcpClient against a mock transport: paths, bodies, the unchanged-value…, test_secret_manager_rest_shapes(), test_firebase_connection_token_exchange_ignores_key_token_uri(), Request, Response (+26 more)

### Community 76 - "_Writer"
Cohesion: 0.17
Nodes (18): _dumps(), _json_default(), _mysql_columns(), Any, IO, Minimal streaming JSON writer on top of a text file., Counts the database objects the export does not carry (views, triggers,…, "Data source 'x' has 2 views, 1 trigger that ..." or None when nothing was… (+10 more)

### Community 77 - "set_setting"
Cohesion: 0.09
Nodes (24): Redis, Test hook: replace the process-wide client (None resets to a lazily created…, set_redis(), _clean_state(), client(), fake_redis(), migration_db(), _no_dns() (+16 more)

### Community 78 - "make_project"
Cohesion: 0.10
Nodes (46): DeviceProjectGrant, create_move_job(), Job, Session, User, Drops old copies whose keep period ended. Offline devices are retried an hour…, run_due_cleanups(), make_project() (+38 more)

### Community 79 - "aws_statements"
Cohesion: 0.11
Nodes (19): aws_statements(), Test hook: every statement of every AWS policy (never shown as one policy, IAM…, requirements(), _actions(), _resources(), test_boundary_document_caps_roles_to_deployer_resources(), test_deployer_user_may_only_write_roles_that_carry_the_boundary(), test_policy_covers_databases_and_scopes_the_firewall() (+11 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.05
Nodes (36): API (`/v1/projects/{pid}`), Co-hosting: live two-way database copies and failover websites, Dashboard (for whoever builds it), Database sync (phase 1 - built), Honest limits (phase 2), Honest limits (shown in the dashboard where they matter), Merge model (conflicts), Roles (+28 more)

### Community 81 - "query_console.py"
Cohesion: 0.06
Nodes (41): _clamp(), _connect_uri(), _enter_read_only(), _error_text(), _first_keyword(), _first_line(), _is_blank(), _is_timeout() (+33 more)

### Community 82 - "query_log.py"
Cohesion: 0.08
Nodes (41): QueryRun, One console/editor run. The only place query text is stored (audit logs keep…, delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), datetime, DbSession (+33 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.09
Nodes (42): parametrize, test_delete_app_when_cloudflare_fails(), test_apps_tunnel_created_once_cname_moves_and_ingress(), add_host(), assert_no_secrets(), desired(), link(), Remote access endpoints (docs/REMOTE_ACCESS.md) with a fake Cloudflare API and… (+34 more)

### Community 84 - "tests/test_query_console.py"
Cohesion: 0.08
Nodes (41): _canceller(), mongo_read_only_refusal(), Engine, Why a viewer may not run this script, naming the word that tripped the check…, A callable that stops the statement running on `conn` from another thread (None…, Runs a SQL script; see the module docstring and docs/QUERY_CONSOLE.md for the…, Why a viewer may not run this code, naming the matched write name (None =…, run_sql() (+33 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.19
Nodes (20): _callback(), _error_of(), _link_state(), parametrize, A callback URL started in another browser (login CSRF / forced linking) is…, _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error() (+12 more)

### Community 86 - "Write-DeployerInfo"
Cohesion: 0.19
Nodes (33): Assert-Admin(), Get-Context(), Get-OnOffArgument(), Invoke-Autostart(), Invoke-Compose(), Invoke-Config(), Invoke-Device(), Invoke-KeepAwake() (+25 more)

### Community 87 - "UninstallForm"
Cohesion: 0.05
Nodes (30): int, string, StringBuilder, AppInfo, DeployerCli, Internet, Marker, MarkerKind (+22 more)

### Community 88 - "introspection.py"
Cohesion: 0.10
Nodes (41): match_entity(), `user_id` / `userId` -> `user`; nested paths use the last segment. `id` / `_id`…, Returns the entity that a `<singular>_id` (or `<singular>Id`) field refers to,…, reference_base(), analyze_documents(), apply_mongo_indexes(), approximate_row_counts(), bson_type_name() (+33 more)

### Community 89 - "FakeCloudflare"
Cohesion: 0.15
Nodes (11): BaseTransport, Test hook: route every client through this transport (None restores the…, set_transport(), fake_cf(), fake_cf(), FakeCloudflare, _ok(), fixture (+3 more)

### Community 90 - "Write-DeployerWarn"
Cohesion: 0.10
Nodes (36): Get-InstallerArgumentString(), Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Invoke-Preflight(), Register-ResumeAfterReboot() (+28 more)

### Community 91 - "test_devices_agent.py"
Cohesion: 0.09
Nodes (23): _connector(), _describe(), DeviceAgent, Any, Event, Exception, Runs one call before its deadline, or raises `device_busy` without running it.…, A plain-words reason the connection failed, and whether the main Deployer… (+15 more)

### Community 92 - "Path"
Cohesion: 0.23
Nodes (15): _fetch_binlog(), _index_path(), _load_index(), mariadb_archive_logs(), mariadb_defaults_file(), mongo_config_file(), mongo_root_uri(), _option_value() (+7 more)

### Community 93 - "By section"
Cohesion: 0.06
Nodes (35): 10. Dashboard data features: databases, data browser, schema, query notebook/terminal, backups, devices, co-hosting, jobs, deploys, 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 3. Query console, query log, saved queries, 4. Backups, PITR, jobs, worker, export/import (+27 more)

### Community 94 - "DumpScanner"
Cohesion: 0.19
Nodes (12): count_insert_rows(), _count_row_tuples(), DumpScanner, Number of `(...)` row tuples in a fragment of an extended INSERT (strings…, (table, rows) for the first line of an extended INSERT in a mariadb-dump, else…, Collects the consistent point and exact row counts from mariadb-dump output…, test_dump_scanner_collects_point_and_counts(), Row counting from mariadb-dump output must handle both extended-INSERT layouts. (+4 more)

### Community 95 - "connections.py"
Cohesion: 0.06
Nodes (70): validation_error(), _key_param(), check_data_source(), _config_hosts(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate (+62 more)

### Community 96 - "executors.py"
Cohesion: 0.14
Nodes (11): DeviceExecutorUnavailable, local_executor(), Any, datetime, ProgressFn, RuntimeError, The seam between backup orchestration and the machine that hosts a database.…, Runs one executor method on this installation's LocalExecutor from JSON params… (+3 more)

### Community 97 - "shell_runner.py"
Cohesion: 0.12
Nodes (24): _as_uid(), _child_env(), _field(), _kill(), main(), make_server(), mongosh_command(), _ms() (+16 more)

### Community 98 - ".TestMarkers"
Cohesion: 0.10
Nodes (13): bool, double, CheckResult, Ports, SystemChecks, SystemReport, Control, Dictionary (+5 more)

### Community 99 - "device_worker.py"
Cohesion: 0.11
Nodes (20): See module docstring., register_copy_target(), Installs the device executor factory and copy target (idempotent)., Removes the hooks installed by `register()` (API shutdown)., register(), unregister(), agent_task(), install() (+12 more)

### Community 100 - "record"
Cohesion: 0.14
Nodes (34): create_collection(), create_link(), create_table(), delete_link(), _drop(), drop_collection(), drop_table(), export_schema() (+26 more)

### Community 102 - "device_local.py"
Cohesion: 0.17
Nodes (28): device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to() (+20 more)

### Community 103 - "conventions.py"
Cohesion: 0.14
Nodes (26): check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural(), _issue() (+18 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.19
Nodes (28): _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query(), get_version(), list_saved_queries() (+20 more)

### Community 106 - "cohost_problem"
Cohesion: 0.12
Nodes (28): cohost_devices(), copy_problem(), deploy_params(), device_env(), device_problem(), eligible_devices(), _main_secrets(), App (+20 more)

### Community 107 - "test_github_actions.py"
Cohesion: 0.12
Nodes (42): generate_dockerfile(), The build recipe for the static/node/python presets; None for `dockerfile` (the…, _shell_quote(), `deployer-gha-<slug>-<id8>` (IAM role names are <= 64 characters)., role_name(), workflow_path(), test_default_npm_install_works_without_a_lockfile(), test_static_preset_never_publishes_dotfiles() (+34 more)

### Community 108 - "Invoke-Update"
Cohesion: 0.10
Nodes (26): Initialize-Engine(), Invoke-Backup(), Invoke-Restart(), Invoke-Restore(), Invoke-Start(), Invoke-Update(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder() (+18 more)

### Community 109 - ".Ask"
Cohesion: 0.12
Nodes (8): FormClosingEventArgs, Dictionary, InstallLocator, bool, Exception, Program, IWin32Window, STAThread

### Community 110 - "CaddyProxyHeaders"
Cohesion: 0.12
Nodes (9): CaddyProxyHeaders, _is_ip(), KeyRoutesCORS, CORS for browsers calling the data API with a bearer key. Any origin but no…, X-Forwarded-For / -Proto count only on connections from the `caddy` container…, Pure ASGI middleware: count, 5xx and latency per route template (not raw path)., RequestMetricsMiddleware, test_forwarded_headers_count_only_from_caddy() (+1 more)

### Community 111 - "run"
Cohesion: 0.13
Nodes (28): detect(), _detect_dir(), _dirs(), env_keys(), _find_module(), _join(), Pattern, _python_deps() (+20 more)

### Community 112 - "FakeDynamo"
Cohesion: 0.12
Nodes (7): aws(), FakeDynamo, _missing(), fixture, KwFake for everything else, plus a small in-memory DynamoDB behind `ddb` that…, A delete job that failed after switching deletion protection off (e.g. the…, test_retried_delete_skips_the_protection_switch()

### Community 113 - "Query Console"
Cohesion: 0.10
Nodes (40): Data browser (SQL rows, MongoDB documents), Schema endpoints, SchemaLink and ConventionIssue, Version history and schema diff, Database Planning Conventions, Conventions panel (advisory warnings), Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle) (+32 more)

### Community 115 - "._c"
Cohesion: 0.11
Nodes (9): _code(), Exception, Deletes a role Deployer made (its one inline policy first); also the GitHub…, The secret `name` holds `value`: created once, a new version only when the…, By ARN or name; at once (no recovery window), so the name can be used again…, The account's IAM identity provider for GitHub Actions tokens (one per account,…, `{arn, current}` of the account's `deployer-boundary` managed policy…, `{status, host, port}`, None once the instance is gone. (+1 more)

### Community 116 - "mongo_snapshot"
Cohesion: 0.18
Nodes (21): ArtifactWriter, check_db_name(), _latest_oplog_ts(), mariadb_snapshot(), mongo_archive_logs(), _mongo_client(), _mongo_collections(), _mongo_drop_tmp() (+13 more)

### Community 117 - "AwsClient"
Cohesion: 0.12
Nodes (8): AwsClient, Deletes every object under `prefix` ("" = the whole bucket). Returns the count., Disables the distribution, waits until CloudFront has rolled that out (up to 30…, This PC's public IPv4 address as AWS sees it (AWS's own checkip service, no…, V-02: the real AwsClient body against botocore's service models (Stubber…, test_ensure_vpc_connector_runs_against_the_real_botocore_models(), The real AwsClient methods against botocore's service models (a wrong parameter…, test_secrets_manager_calls_match_botocore_models()

### Community 118 - "test_devices_local.py"
Cohesion: 0.09
Nodes (23): http_host_allowed(), insecure_primary_allowed(), Returns the normalized origin (`scheme://host[:port]`) or raises 422…, validate_primary_url(), fake_primary(), FakePrimary, fixture, parametrize (+15 more)

### Community 119 - "test_firestore.py"
Cohesion: 0.16
Nodes (19): base(), connect(), docs_url(), _fail(), FakeFirestore, gcp(), fixture, Cloud Firestore engine, phase C2-3 (docs/CLOUD.md): a Firebase project's… (+11 more)

### Community 120 - "SchemaDiffView.tsx"
Cohesion: 0.15
Nodes (21): DiffChange, FieldDiff, SchemaDiffEntity, AttributeChange, CHANGE_LABELS, CHANGE_ORDER, DiffSummary, fieldAttributeChanges() (+13 more)

### Community 121 - "compilerOptions"
Cohesion: 0.07
Nodes (26): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+18 more)

### Community 122 - "cloud_deploy.py"
Cohesion: 0.09
Nodes (40): add_domain(), check_domain(), _client_for(), cloud_env(), cloud_url(), _connection(), _create_cf_records(), _delete_cf_records() (+32 more)

### Community 123 - "test_rtdb.py"
Cohesion: 0.17
Nodes (18): base(), connect(), _fail(), FakeRtdb, gcp(), fixture, Firebase Realtime Database engine, phase C2-4 (docs/CLOUD.md): a Firebase…, FakeCloud for the hosting calls, plus an in-memory Realtime Database behind… (+10 more)

### Community 124 - "create_replica"
Cohesion: 0.23
Nodes (23): cohosting_eligibility(), create_replica(), delete_replica(), get_conflict(), list_conflicts(), list_replicas(), DataSource, DbSession (+15 more)

### Community 125 - "OutputWindow"
Cohesion: 0.13
Nodes (11): Color, FormClosedEventArgs, Panel, string, TextBox, LogWindow, OutputWindow, ServiceInfo (+3 more)

### Community 126 - "How the main code paths work"
Cohesion: 0.08
Nodes (24): 1. Signing in, 2. A data API request with an API key, 3. Running a query in the console or notebook, 4. Push-to-deploy, 5. Backups and point-in-time recovery, 6. A co-hosting sync round, 7. Deploying to the cloud, 8. Installing, updating and staying up (+16 more)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.12
Nodes (17): binlog_name_with_seq(), binlog_seq(), _mongo_build_oplog(), name_rewriter(), DEFINER -> the target's user; database name -> target. Data (INSERT) lines are…, Namespace-renamed copy of an oplog entry without collection UUIDs; None if…, rename_oplog_entry(), rewrite_dump_line() (+9 more)

### Community 128 - "cloud_secrets.py"
Cohesion: 0.13
Nodes (24): docs/CLOUD.md "G1": admins switch the secret store on (billable:…, _set_cloud_secrets(), cleanup(), enabled(), out(), App, App secrets in AWS Secrets Manager / Google Secret Manager (docs/CLOUD.md…, Deletes the secrets the live version no longer references - after the rollout,… (+16 more)

### Community 129 - "FakeDockerCli"
Cohesion: 0.11
Nodes (5): FakeDockerCli, Records the call sequence; `fail_at = <step>` makes that step raise;…, FakeProviders, _symlink(), test_build_image_refuses_symlinks_out_of_the_checkout()

### Community 130 - "integration/test_query_console.py"
Cohesion: 0.14
Nodes (23): mongo_uri_password(), mariadb(), mongo(), fixture, Query console against real servers (docs/QUERY_CONSOLE.md). - SQL: a throwaway…, A-001: what code that gets past the name filter can see. It runs in the query-…, run(), sh() (+15 more)

### Community 131 - "dependencies"
Cohesion: 0.09
Nodes (23): @codemirror/autocomplete, @codemirror/lang-javascript, @codemirror/lang-sql, @codemirror/language, @dagrejs/dagre, dependencies, @codemirror/autocomplete, @codemirror/lang-javascript (+15 more)

### Community 132 - "Get-DeployerSource"
Cohesion: 0.21
Nodes (12): Get-BuildSource(), Get-LocalDeploySource(), Resolve-Source(), Copy-DeployerFiles(), Get-DeployerSource(), Invoke-DeployerDownload(), Invoke-DeployerRobocopy(), Resolve-DeployerRef() (+4 more)

### Community 133 - "setup_import"
Cohesion: 0.26
Nodes (14): projects_import(), projects_import_job(), Form, ProjectCreator, Upload, then a job: the file is checked and decrypted here (a wrong passphrase…, _read_projects_upload(), _save_upload(), setup_import() (+6 more)

### Community 134 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+13 more)

### Community 135 - "NativeMethods"
Cohesion: 0.16
Nodes (10): DllImport, int, IntPtr, MEMORYSTATUSEX, NativeMethods, RECT, MarshalAs, MEMORYSTATUSEX (+2 more)

### Community 136 - "test_data_sources.py"
Cohesion: 0.10
Nodes (9): fake_connect(), project_setup(), fixture, Route tests for data sources, schema, links and the SQL data browser. External…, sqlite_engine(), test_create_external_sql_source(), test_internal_network_is_refused_for_non_owners(), test_other_projects_sources_are_hidden() (+1 more)

### Community 137 - "devDependencies"
Cohesion: 0.10
Nodes (21): devDependencies, @eslint/js, eslint-plugin-react-hooks, jsdom, @types/node, @types/react, typescript, typescript-eslint (+13 more)

### Community 138 - "routers/remote_access.py"
Cohesion: 0.20
Nodes (24): add_hostname(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, BaseModel, DbSession (+16 more)

### Community 139 - "cloud_aws.py"
Cohesion: 0.13
Nodes (16): free_blocks(), _nat_alive(), nat_name(), _ours(), _public_subnet(), The AWS calls behind the AWS hosting targets (docs/CLOUD.md), one small method…, Deletes the private subnets; the deleted connector's network interfaces hold…, The Name tag of every NAT resource of a VPC, and the private subnets' VPC… (+8 more)

### Community 140 - "create_app"
Cohesion: 0.10
Nodes (29): create_app(), lifespan(), FastAPI, _check_redis(), health(), get, Response, apply_row_counts() (+21 more)

### Community 141 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.26
Nodes (17): Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Caddy :8081 tunnel-only listener, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes (+9 more)

### Community 142 - "test_conventions.py"
Cohesion: 0.40
Nodes (18): check_conventions(), entity(), field(), _link(), mongo_source(), rules(), sql_source(), test_errored_sources_are_skipped() (+10 more)

### Community 143 - "test_transfer_stream.py"
Cohesion: 0.15
Nodes (13): A source's `data` entry parsed lazily from `fh`: `tables` / `collections` and…, read_data_entry(), _dump(), fake_engine(), FakeConn, materialize(), Audit A-049: device imports / moves restore a gzip `data` entry streamed, not…, Returns at most 7 characters per read, so every token straddles a buffer… (+5 more)

### Community 144 - "DeployerSetup"
Cohesion: 0.16
Nodes (6): DeployerSetup, Icon, AppIcon, Bitmap, Color, Logo

### Community 145 - "supervisor.sh"
Cohesion: 0.32
Nodes (15): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), pid_alive(), read_desired(), supervisor.sh script (+7 more)

### Community 146 - ".get"
Cohesion: 0.13
Nodes (17): check_changes(), ext(), _merge_warnings(), _mongo_change(), Any, ApiError, Event, One pass over the replicas due for a round, up to ROUND_WORKERS at a time.… (+9 more)

### Community 147 - "_replay_binlogs"
Cohesion: 0.15
Nodes (20): BackupEngineError, _check_exit(), _mongo_load_archive(), _mongorestore(), open_artifact_plain(), IO, Popen, ProgressFn (+12 more)

### Community 148 - "gcp_for"
Cohesion: 0.17
Nodes (25): collection_entity(), collection_ids(), composite_indexes(), connection_info(), _count(), database_of(), _documents(), entity() (+17 more)

### Community 149 - "test_projects.py"
Cohesion: 0.20
Nodes (6): slugify(), test_delete(), test_get_requires_membership(), test_patch_requires_admin(), test_slugify(), test_unique_slug_suffix()

### Community 150 - "test_mcp.py"
Cohesion: 0.09
Nodes (18): make_source(), test_external_sources_have_no_backups(), env(), fixture, MCP server for AI agents (docs/MCP.md): JSON-RPC over POST…, The `minimum` (or another argument, e.g. `service_keys`) of the route's…, _route_role(), test_app_tools() (+10 more)

### Community 151 - "github_repos"
Cohesion: 0.18
Nodes (15): github_connect(), github_disconnect(), github_repos(), github_status(), CurrentUser, DbSession, delete, ge (+7 more)

### Community 152 - "field_validator"
Cohesion: 0.24
Nodes (3): _one_line(), field_validator, _valid_branch()

### Community 153 - "_clean_up_slot"
Cohesion: 0.22
Nodes (10): _clean_up_slot(), The live (non-zombie) processes whose real, effective, saved or fs uid is the…, Kills every process of the slot uid (a script may have left one running to…, _slot_pids(), _fake_proc(), V-01: the slot's processes are found in /proc (no shell is started to kill…, V-01, in the API image as root (the CI unit suite): a process of a slot uid is…, test_clean_up_slot_kills_a_real_process() (+2 more)

### Community 154 - "key_hash"
Cohesion: 0.14
Nodes (12): key_hash(), conflicted(), fixture, FakeSide, FakeStore, Crash between apply and position update: the replay changes nothing and opens…, Each round waits at a barrier for the other: this only passes when they run…, test_device_side_speaks_rpc_and_drops_unexpected_fields() (+4 more)

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (13): buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests(), Snippet (+5 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.08
Nodes (39): Release workflow (release.yml), Optional code signing with signtool, Release job: build and push GHCR images, Pre-release tags never become latest, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Notes for AI agents (skill copy, MCP, graphify), Everyday commands (+31 more)

### Community 157 - "test_device_rpc.py"
Cohesion: 0.21
Nodes (15): mark_offline(), mark_online(), online_key(), test_resolve_delete_and_bad_values(), _fresh(), _hello(), Primary-side device RPC: Redis pub/sub routing, the control WebSocket and…, Polls `predicate` (the server handles socket messages on its own threads, so… (+7 more)

### Community 158 - "backup_engine.py"
Cohesion: 0.20
Nodes (22): _load_dump(), _managed_user_for(), _mariadb_clear(), _mariadb_create_db(), mariadb_current_point(), _mariadb_drop_db(), _mariadb_exec(), _mariadb_log_bin_enabled() (+14 more)

### Community 159 - ".value"
Cohesion: 0.42
Nodes (3): Each key of an object; the caller reads its value before asking for the next., Yields before each member of the container just opened; the caller reads it., _stream_parts()

### Community 160 - "Data API with API keys"
Cohesion: 0.14
Nodes (14): Calling from a browser, Config file, Data API with API keys, Databases in the cloud (AWS / Firebase), Documents (MongoDB sources), DynamoDB tables, Errors, Firestore collections (+6 more)

### Community 161 - "cancel_job"
Cohesion: 0.19
Nodes (13): cancel_job(), _get_job(), list_jobs(), Admin, DbSession, ge, get, Job (+5 more)

### Community 162 - "LocalExecutor"
Cohesion: 0.19
Nodes (5): backup_root(), LocalExecutor, Path, Runs dump/restore tools against this installation's managed databases (see…, Main server only: snapshot of the platform metadata database.

### Community 163 - "API runtime dependencies (requirements.txt)"
Cohesion: 0.21
Nodes (13): API runtime dependencies (requirements.txt), alembic, argon2-cffi (password hashing), cryptography, API dev and test dependencies (requirements-dev.txt), fakeredis, pytest, ruff (+5 more)

### Community 164 - "test_container_config.py"
Cohesion: 0.23
Nodes (12): A-153: container settings have one source of truth (compose / Caddy), not…, A-001: mongosh (full Node.js for developers and service keys) runs only in the…, A-019: apps (and apps with database access) never share a network with the API,…, A-044: the dashboard imports through /projects/import/jobs; Caddy's 64 MB cap…, L-01: a long migration (0012 rebuilds every DATETIME table) must not run inside…, read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through() (+4 more)

### Community 165 - "query/diff.ts"
Cohesion: 0.39
Nodes (6): text(), DIFF_MAX_LINES, DiffLine, lineDiff(), lines(), render()

### Community 166 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.20
Nodes (10): AWS policy split as built: purpose-sized managed policies, C2 - cloud databases (what is left), Cloud hosting and databases (AWS, Firebase), Code, API, dashboard, Deleting a cloud database over the API and MCP (as built), Not verified against real clouds, Not verified against real clouds, Principles (+2 more)

### Community 167 - "wslplatform.tests.ps1"
Cohesion: 0.15
Nodes (3): Initialize-WslPlatform(), Get-WindowsOptionalFeature(), Test-Reboot()

### Community 168 - "sweep_orphans"
Cohesion: 0.25
Nodes (9): provider_id(), The role's name from the app's slug and id alone (a teardown knows it after the…, `gh-<id8>`: the app's workload identity provider in the shared pool., (label, call) removing what the setup made; the shared OIDC provider / pool…, Removes the `deployer-gha-*` roles (tagged managed-by=deployer) / `gh-*`…, role_name_for(), sweep_orphans(), teardown_steps() (+1 more)

### Community 169 - "Write-DeployerLog"
Cohesion: 0.28
Nodes (9): Start-Stack(), Get-DeployerHealth(), Get-DeployerKeepAliveProcess(), Invoke-DeployerKeepAliveLoop(), Start-DeployerKeepAlive(), Stop-DeployerKeepAlive(), Wait-DeployerHealth(), Write-DeployerError() (+1 more)

### Community 170 - "Any"
Cohesion: 0.29
Nodes (8): compare_counts(), mongo_verify(), parse_binlog(), parse_mongodump_counts(), Any, Event-header scan of a raw binlog file: databases touched and first/last event…, ts_from(), test_parse_mongodump_counts_and_compare()

### Community 171 - "C2-3 as built: Cloud Firestore"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project, API, Apps on Cloud Run, Browsing, editing, querying, C2-3 as built: Cloud Firestore, Data model, MCP, Not verified against real clouds (+1 more)

### Community 172 - "Deploy a website with Deployer"
Cohesion: 0.17
Nodes (12): Cloud targets (AWS / Firebase through Deployer), Co-host PCs (the same app on other PCs, with failover), Connecting an AI agent (MCP), Deploy a website with Deployer, Do / don't, Feature status (check before promising anything), Hard rule: always ask which platform, People, sign-in and co-hosting (+4 more)

### Community 173 - ".delete_nat_gateway"
Cohesion: 0.25
Nodes (5): (`pending` | `available` | `failed` | `deleting` | `deleted`, AWS's failure…, Deletes the VPC's NAT gateway, waits until AWS has removed it (bounded) and…, Removes the private route table (its subnet associations first)., An EC2 delete for which already gone is fine (two teardowns of the same VPC,…, _unless_gone()

### Community 174 - "C3 as built: GitHub Actions builds (pushes deploy with the PC off)"
Cohesion: 0.18
Nodes (11): API, C3 as built: GitHub Actions builds (pushes deploy with the PC off), Dashboard, MCP, Not verified against real clouds, Permissions added, Reports, Deploy now, runs, Switching back, teardown (+3 more)

### Community 175 - "C2-1 as built: cloud databases in AWS (RDS / Aurora)"
Cohesion: 0.22
Nodes (9): API, Apps, C2-1 as built: cloud databases in AWS (RDS / Aurora), Data model, MCP, Networking (the trade-off), Not verified against real clouds, Permissions added (now in the `DeployerDatabases` policy, shown in Settings -> Cloud accounts) (+1 more)

### Community 176 - "C1 as built"
Cohesion: 0.22
Nodes (9): API, C1 as built, Cloud connections, Custom domains, Dashboard, MCP, Not verified against real clouds, Targets (`apps.target`) (+1 more)

### Community 177 - "lan.tests.ps1"
Cohesion: 0.20
Nodes (3): Get-DeployerNonPrivateNetworks(), Write-DeployerNetworkProfileWarning(), Get-NetConnectionProfile()

### Community 178 - "Condition"
Cohesion: 0.26
Nodes (15): _api_rule(), _backup_rules(), _cloud_cleanup_rule(), Condition, conditions(), _container_rules(), _fmt_age(), _fmt_gb() (+7 more)

### Community 179 - ".transfer"
Cohesion: 0.18
Nodes (11): _dt(), datetime, SyncConflict, Applies `side`'s changes to the other copy (`target`)., test_skipped_views_and_triggers_warn_at_export_and_import(), inline_jobs(), fixture, A-043: a payload too big to unpack in memory is refused with a clear 413, not… (+3 more)

### Community 180 - "test_devices_enrollment.py"
Cohesion: 0.43
Nodes (6): _allow_poll(), _enroll(), Device enrollment (device authorization flow) and device-token authentication., test_deny_and_expiry(), test_device_token_does_not_work_on_user_endpoints(), test_full_enrollment_flow()

### Community 181 - "fix_state_ownership"
Cohesion: 0.67
Nodes (3): fix_state_ownership(), A-082: hands the shared volume back to uid 10001 (the API and the sidecar) when…, test_worker_gives_a_root_owned_state_volume_back_to_uid_10001()

### Community 182 - "test_migration_table_options.py"
Cohesion: 0.25
Nodes (6): head_db_url(), fixture, Migration checks: every migration table gets the utf8mb4 options, and head…, A scratch database upgraded to head: SQLite always, and a throwaway database on…, `create_all` builds the test schema, so a model change without a migration…, test_migrations_match_the_models()

### Community 183 - "main"
Cohesion: 0.28
Nodes (13): acquire_leadership(), _guard(), _load_plugins(), main(), mongo_replset_loop(), Event, Redis, Thread (+5 more)

### Community 184 - "apply_changes"
Cohesion: 0.20
Nodes (9): apply_changes(), _norm(), _project(), Canonical form for comparing versions read from a binlog and from a SELECT., SQL rows are compared on the version's columns (a copy may have extra columns)., Applies changes in order; returns one outcome per change: `{"result":…, MongoDB: `change` is the echo of a write the sync made on `side` (consumed…, row_hash() (+1 more)

### Community 185 - "fake_device"
Cohesion: 0.09
Nodes (26): _key(), SessionFactory, Brings the app's copies in line with its live deployment: a row per eligible…, Every scheduler tick: catch up every co-hosted app, then reconcile each online…, replicate(), sweep(), fake_device(), FakeDevice (+18 more)

### Community 186 - "test_api_docs_routes.py"
Cohesion: 0.52
Nodes (6): _documented(), _norm(), _paths(), Every endpoint the docs name must exist in the router (A-189). Checked: `|…, _routes(), test_documented_endpoints_exist()

### Community 187 - "test_release_workflow.py"
Cohesion: 0.33
Nodes (6): _permissions(), A-149: the release workflow is read-only by default; only the jobs that publish…, Every `permissions:` block at this indent, as {scope: level}., A-190: a tag that fails CI publishes nothing, and an RC never becomes `latest`., test_images_wait_for_ci_and_prereleases_skip_latest(), test_release_workflow_permissions_are_per_job()

### Community 188 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 189 - "DataSource"
Cohesion: 0.38
Nodes (7): _from_canonical(), DataSource, PathLike, Restores a gzip JSON `data` entry (write_source_data) into a source on this…, restore_data(), restore_file(), restore_mongo_data()

### Community 190 - "TempFileResponse"
Cohesion: 0.33
Nodes (4): Streams a temp file and always deletes it, also when the client is gone before…, TempFileResponse, A-044: the export is built before the first byte; a tunnel that gave up must…, test_export_temp_file_deleted_when_client_is_gone()

### Community 192 - "dec"
Cohesion: 0.23
Nodes (9): dec(), enc(), enc_row(), _q(), One binlog row image pair -> change dicts (a primary key update becomes delete…, SQL value -> JSON-safe value (tagged for types JSON can't carry)., row_changes(), test_primary_key_update_becomes_delete_and_insert() (+1 more)

### Community 193 - "exports_dir"
Cohesion: 0.40
Nodes (6): export_path(), exports_dir(), prune_exports(), Path, Finished export files of the API process; `prune_exports` deletes them after…, Deletes export files (and leftovers of interrupted ones) older than the…

### Community 194 - "test_dead_code.py"
Cohesion: 0.47
Nodes (5): A-191: every top-level constant, function and class in app/ is referenced in…, test_a_name_used_only_by_tests_is_dead(), test_no_unreferenced_top_level_names(), _top_level_names(), Module

### Community 195 - "C2-2 as built: DynamoDB"
Cohesion: 0.18
Nodes (11): Add database -> In your AWS account -> NoSQL, API, Apps on App Runner, Backups (Backups tab), Browsing, editing, querying, C2-2 as built: DynamoDB, Data model, MCP (+3 more)

### Community 196 - "C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway)"
Cohesion: 0.29
Nodes (7): API, MCP, dashboard, C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway), Not verified against real clouds, Permissions added (`DeployerDatabases` and `DeployerHosting`, shown in Settings -> Cloud accounts), Shared, reference-counted, removed with the last user, What it is, What the deploy makes (`cloud_deploy.Publish.nat_connector`, `cloud_aws.ensure_nat_network`)

### Community 197 - "0010_cohost_apps.py"
Cohesion: 0.60
Nodes (3): _columns(), _create_app_replicas(), upgrade()

### Community 198 - "test_fixture_layout.py"
Cohesion: 0.50
Nodes (4): _is_fixture(), A-192: shared fixtures live in conftest.py or its plugin modules, never…, test_no_fixture_is_imported_from_a_test_module(), FunctionDef

### Community 199 - "test_query_docs.py"
Cohesion: 0.50
Nodes (3): The query docs describe the shipped Terminal/Notebook modes, not superseded…, _read(), test_query_docs_describe_modes_without_plans()

### Community 200 - "test_skill_doc.py"
Cohesion: 0.60
Nodes (4): The deploy-website skill must not contradict itself about where apps can run…, _section(), test_co_host_apps_are_not_listed_as_not_built(), test_external_platform_table_lists_only_external_platforms()

### Community 201 - "test_version.py"
Cohesion: 0.50
Nodes (3): A-188: release images report their git tag as the version, not the hardcoded…, _reload_version(), test_version_comes_from_the_release_tag()

### Community 202 - "package.json"
Cohesion: 0.40
Nodes (4): name, private, type, version

### Community 204 - "setup-engine.sh"
Cohesion: 0.60
Nodes (4): DEBIAN_FRONTEND, enable_unit(), log(), setup-engine.sh script

### Community 206 - "0012_datetime_microseconds.py"
Cohesion: 0.83
Nodes (3): downgrade(), _set_fsp(), upgrade()

### Community 230 - "scheduler_tick"
Cohesion: 0.33
Nodes (6): prune(), datetime, Session, A-102: deletes refresh tokens a day past expiry and audit rows older than…, scheduler_tick(), test_worker_prunes_once_a_day()

### Community 231 - ".ensure_github_role"
Cohesion: 0.33
Nodes (3): The App Runner instance role `name` (created once, within the boundary) the…, The role one app's workflow assumes (within the boundary): `trust` (its…, Puts the boundary on an existing role that lacks it (made before the boundary…

### Community 251 - "handle"
Cohesion: 0.24
Nodes (10): Access, handle(), mcp_endpoint(), DbSession, JSONResponse, post, Request, Response (+2 more)

### Community 253 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

### Community 254 - "test_source_ops.py"
Cohesion: 0.60
Nodes (4): _ds(), source_ops: local and device-hosted sources share one dispatcher, so the two…, test_export_and_introspect_mix_local_and_device_sources(), test_wrappers_send_the_same_op_locally_and_to_the_device()

### Community 255 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.25
Nodes (8): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, New databases, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

### Community 256 - "check"
Cohesion: 0.33
Nodes (6): check(), database_problem(), describe(), list_databases(), `connections.try_source` for Firestore: the database answers and is in native…, The Firestore databases of the connection's project, with why Deployer can't…

### Community 257 - "id_candidates"
Cohesion: 0.43
Nodes (6): id_candidates(), Possible `_id` values for the string form used in URLs: ObjectId hex, then a…, Document ids in URLs are strings; the resolver must try every `_id` type a user…, test_integer_ids_are_tried_before_the_string_form(), test_object_id_then_string(), test_out_of_range_or_non_numeric_stay_strings()

### Community 258 - "_fake_binlog"
Cohesion: 0.33
Nodes (7): _fake_binlog(), Replaces the binlog reader: `binlog` is [(seq, [rows of one WriteRowsEvent,…, A-011: one bulk transaction used to be read whole (over the RPC size cap, stuck…, A change that fits the RPC cap alone must not be piled onto an almost full…, _read_all(), test_big_row_is_sent_in_a_batch_of_its_own(), test_transaction_bigger_than_a_batch_is_split_across_rounds()

### Community 261 - ".__init__"
Cohesion: 0.47
Nodes (5): latest_versions(), owed_echoes(), Session, Newest `SyncVersion` per (table, key_hash)., MongoDB: versions whose write has not come back through a change stream yet,…

### Community 262 - "Firestore point-in-time recovery and deletes (as built)"
Cohesion: 0.33
Nodes (6): API, Deletes (Backups tab; typed name), Firestore point-in-time recovery and deletes (as built), MCP, Not verified against real clouds, Point-in-time recovery (Backups tab -> Point-in-time recovery)

### Community 263 - "G1 as built: app secrets in a secret store, environment changes without a rollback"
Cohesion: 0.33
Nodes (6): API, dashboard, MCP, Environment changes reach App Runner / Cloud Run apps at once, G1 as built: app secrets in a secret store, environment changes without a rollback, Not verified against real clouds, Permissions added, Secrets in AWS Secrets Manager / Google Secret Manager (opt-in)

### Community 264 - "C2-5 as built: MCP, transfer, project delete"
Cohesion: 0.33
Nodes (6): C2-5 as built: MCP, transfer, project delete, Data tools on cloud databases, Deleting a project, MCP: every tool needs at least its REST route's role, Not verified against real clouds, Transfer (export / import)

### Community 265 - "Settings"
Cohesion: 0.40
Nodes (3): Process configuration, read from environment variables (see…, Settings, BaseSettings

### Community 269 - "G3 as built: a permissions boundary for the roles Deployer creates"
Cohesion: 0.40
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

## Knowledge Gaps
- **531 isolated node(s):** `docker-entrypoint.sh script`, `deployer-api`, `name`, `private`, `version` (+526 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ControlForm` connect `ControlForm` to `shell_runner.py`, `.TestMarkers`, `WizardForm`, `.Rebuild`, `FlatButton`, `.Ask`, `UninstallForm`, `OutputWindow`?**
  _High betweenness centrality (0.260) - this node is a cross-community bridge._
- **Why does `ApiError` connect `ApiError` to `cloud_secrets.py`, `integration/test_query_console.py`, `.__init__`, `source_sync.py`, `oauth.py`, `setup_import`, `device_host.py`, `apps.py`, `is_online`, `utcnow`, `test_github_integration.py`, `rtdb.py`, `.get`, `_replay_binlogs`, `data_browser.py`, `CloudError`, `mcp.py`, `gcp_for`, `services/remote_access.py`, `key_hash`, `Publish`, `get_settings`, `test_device_rpc.py`, `backup_engine.py`, `firestore.py`, `CloudflareClient`, `device_rpc.py`, `services/__init__.py`, `dynamo.py`, `github_actions.py`, `run_queued`, `test_source_sync.py`, `firestore_admin.py`, `routers/backups.py`, `build_export_file`, `Condition`, `models.py`, `schema_ops.py`, `services/transfer.py`, `fake_device`, `deployments.py`, `TempFileResponse`, `_TempArtifact`, `factory`, `dec`, `test_query_log.py`, `source_ops.py`, `_Writer`, `make_project`, `query_console.py`, `query_log.py`, `tests/test_query_console.py`, `test_devices_agent.py`, `DumpScanner`, `connections.py`, `record`, `device_local.py`, `DeviceExecutor`, `saved_queries.py`, `mongo_snapshot`, `test_devices_local.py`, `cloud_deploy.py`, `create_replica`, `test_source_ops.py`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Why does `parseError()` connect `client.ts` to `ControlForm`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Are the 120 inferred relationships involving `ApiError` (e.g. with `ProjectAccess` and `AppCreate`) actually correct?**
  _`ApiError` has 120 INFERRED edges - model-reasoned connections that need verification._
- **What connects `docker-entrypoint.sh script`, `deployer-api`, `name` to the rest of the system?**
  _531 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `CloudAccountsPage.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.04579630895420369 - nodes in this community are weakly interconnected._
- **Should `App.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.037528790136837825 - nodes in this community are weakly interconnected._