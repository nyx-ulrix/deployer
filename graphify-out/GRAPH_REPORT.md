# Graph Report - Deployer  (2026-10-21)

## Corpus Check
- 500 files · ~621,604 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 8591 nodes · 28358 edges · 275 communities (248 shown, 27 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 1827 edges (avg confidence: 0.66)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `26d6c70a`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- deps.py
- States.tsx
- useToast
- types.ts
- DataSource
- AuditLog
- cn
- device_host.py
- record
- FlatButton
- is_online
- client.ts
- utcnow
- cloud_db.py
- rtdb.py
- BackupsTab.tsx
- _job_deploy
- SchemaTab.tsx
- CloudflareSetup.tsx
- data_browser.py
- deploys.ts
- CloudError
- mcp.py
- services/remote_access.py
- test_monitoring.py
- ControlForm
- ApiError
- Publish
- provisioning.py
- write_both
- firestore.py
- run_job
- CloudflareClient
- get_redis
- deployer.sh
- make_app
- WizardForm
- ThemedForm
- errors.py
- dynamo.py
- App
- auth_headers
- test_data_api_keys.py
- test_backups_api.py
- test_source_sync.py
- MCP.md
- README.md
- firestore_admin.py
- routers/backups.py
- terminal.ts
- TempFileResponse
- test_rds_tls.py
- test_projects.py
- schema_ops.py
- executors.py
- CI workflow (ci.yml)
- import_projects
- test_clone_failure_hints
- Deployer HTTP API v1
- IShellLinkW
- backup_crypto.py
- NotebookConsole.tsx
- models.py
- factory
- DeviceExecutor
- common.ps1
- run_queued
- ApiKeysTab.tsx
- docker-compose.yml (production stack)
- test_retention.py
- _call
- test_setup.py
- DockerCli
- ddl_export.py
- source_ops.py
- client
- _Writer
- fixture
- make_project
- aws_statements
- Deployments (push-to-deploy) — phase 4
- query_console.py
- query_log.py
- test_remote_access.py
- tests/test_query_console.py
- set_setting
- Write-DeployerInfo
- UninstallForm
- introspection.py
- FakeCloudflare
- install.ps1
- DeviceAgent
- results.ts
- By section
- Core.cs
- connections.py
- test_cohosting_api.py
- shell_runner.py
- .TestMarkers
- device_worker.py
- get_schema
- PitrFake
- device_local.py
- conventions.py
- useTerminalConsole.ts
- saved_queries.py
- deploy_params
- test_github_actions.py
- Invoke-Update
- .Ask
- CaddyProxyHeaders
- run
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- AwsClient
- backup_engine.py
- .public_ip
- test_devices_local.py
- test_firestore.py
- RowDialog.tsx
- compilerOptions
- App
- test_rtdb.py
- get_source
- OutputWindow
- How the main code paths work
- test_backups_engine.py
- cloud_secrets.py
- FakeDockerCli
- integration/test_query_console.py
- dependencies
- QueryEditor.tsx
- build_export_file
- compilerOptions
- NativeMethods
- test_data_sources.py
- devDependencies
- switch_public_url
- cloud_aws.py
- diff_schemas
- Remote Access & Custom Domains (Cloudflare)
- test_conventions.py
- test_transfer_stream.py
- Logo
- supervisor.sh
- .get
- Path
- DataSource
- ResultsGrid.tsx
- test_mcp.py
- github_repos
- metrics.py
- test_firestore_admin.py
- key_hash
- apiSnippets.ts
- HANDOVER.md
- test_device_rpc.py
- test_backups_pitr.py
- .value
- Data API with API keys
- cancel_job
- LocalExecutor
- API runtime dependencies (requirements.txt)
- test_container_config.py
- query/diff.ts
- Cloud hosting and databases (AWS, Firebase)
- wslplatform.tests.ps1
- SettingsDialog
- _payload
- ThemeProvider.tsx
- C2-3 as built: Cloud Firestore
- Deploy a website with Deployer
- readOnly.ts
- C3 as built: GitHub Actions builds (pushes deploy with the PC off)
- C2-1 as built: cloud databases in AWS (RDS / Aurora)
- C1 as built
- Invoke-StatusJson
- Condition
- .transfer
- run_due
- sync_desired
- test_migration_table_options.py
- main
- apply_changes
- FakeDevice
- test_api_docs_routes.py
- test_release_workflow.py
- scripts
- Invoke-Preflight
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
- test_devices_agent.py
- sample
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
- consoleMode.ts
- C2-4 as built: Firebase Realtime Database
- test_managed_db_connection_cap.py
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
- check
- id_candidates
- _fake_binlog
- get_summary
- _Watchdog
- .__init__
- Firestore point-in-time recovery and deletes (as built)
- G1 as built: app secrets in a secret store, environment changes without a rollback
- C2-5 as built: MCP, transfer, project delete
- Settings
- collect_metrics
- heartbeat
- replica
- G3 as built: a permissions boundary for the roles Deployer creates
- main
- test_ensure_vpc_connector_runs_against_the_real_botocore_models
- test_secrets_manager_calls_match_botocore_models
- @tanstack/react-query
- jsdom

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
- `Guiding rules (self-contained, free by default, one control plane, portable)` --semantically_similar_to--> `Ground rules`  [INFERRED] [semantically similar]
  docs/ARCHITECTURE.md → CONTRIBUTING.md
- `Pick the computer (Windows PC vs Linux server requirements)` --semantically_similar_to--> `Requirements`  [INFERRED] [semantically similar]
  docs/SETUP.md → README.md
- `deployer-deploy.zip release asset` --references--> `docker-compose.yml (production stack)`  [INFERRED]
  .github/workflows/release.yml → deploy/docker-compose.yml
- `pymongo` --calls--> `mongodb service (replica set rs0)`  [INFERRED]
  api/requirements.txt → deploy/docker-compose.yml

## Import Cycles
- 3-file cycle: `api/app/services/device_host.py -> api/app/services/transfer.py -> api/app/services/devices.py -> api/app/services/device_host.py`
- 3-file cycle: `api/app/services/deployments.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 4-file cycle: `api/app/services/cohosting.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py`
- 4-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/device_moves.py -> api/app/services/backups.py`
- 4-file cycle: `api/app/services/cohost_apps.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 4-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 4-file cycle: `api/app/services/deployments.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/device_apps.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/cloud_db.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py -> api/app/services/cloud_db.py`
- 5-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`

## Hyperedges (group relationships)
- **Release pipeline: CI gate, images, setup exe, bundle** — _github_workflows_release_tests, _github_workflows_release_images, _github_workflows_release_setup_exe, github_workflows_release_bundle [EXTRACTED 1.00]
- **MCP billable tools gated by confirm_billing** — docs_mcp_confirm_billing_pattern, docs_mcp_tool_set_app_target, docs_mcp_tool_create_cloud_database, docs_mcp_tool_set_build_location, docs_mcp_tool_set_app_secrets_store, docs_mcp_tool_set_app_internet_access [EXTRACTED 1.00]
- **Secrets encrypted at rest with MASTER_KEY** — docs_platforms_master_key, docs_platforms_table_instance_settings, docs_platforms_table_github_connections, docs_platforms_table_apps, docs_platforms_table_cloud_connections, docs_platforms_table_data_sources [EXTRACTED 1.00]
- **Backup protection layers for a managed database** — docs_backups_snapshots, docs_backups_pitr, docs_backups_safety_snapshots, docs_backups_recently_deleted, docs_backups_platform_backup, docs_backups_verification [EXTRACTED 1.00]
- **Device runtime protocol (control channel, RPC routing, methods, transfers)** — docs_devices_control_channel, docs_devices_rpc_routing, docs_devices_rpc_methods, docs_devices_bulk_transfers [EXTRACTED 1.00]
- **Cloudflare tunnel stack (link, sidecar, supervisor, handshake files, Caddy 8081)** — docs_remote_access_link_step, docs_remote_access_tunnel_sidecar, docs_remote_access_supervisor, docs_remote_access_desired_status_files, docs_remote_access_caddy_8081 [INFERRED 0.85]

## Communities (275 total, 27 thin omitted)

### Community 0 - "deps.py"
Cohesion: 0.05
Nodes (81): api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), load_project_access(), ApiError (+73 more)

### Community 1 - "States.tsx"
Cohesion: 0.04
Nodes (125): isApiError(), isApiStarting(), isDeviceOffline(), api, qk, isJobFinished(), useInstanceSettings(), useJob() (+117 more)

### Community 2 - "useToast"
Cohesion: 0.05
Nodes (89): errorMessage(), invalidateProjectSources(), AppReplica, AppSecrets, DnsRecord, FirestoreBackup, JsonObject, JsonValue (+81 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (132): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+124 more)

### Community 4 - "DataSource"
Cohesion: 0.05
Nodes (83): DataSource, Device, DeviceEnrollment, ProjectMember, A row/document changed on both copies since their last common version (like a…, A version of a row/document the sync applied or confirmed (base for conflict…, SourceReplica, SyncConflict (+75 more)

### Community 5 - "AuditLog"
Cohesion: 0.04
Nodes (108): client_ip(), The peer address. Behind Caddy, main.CaddyProxyHeaders has already set it from…, AuditLog, RefreshToken, change_password(), LinkIn, login(), LoginIn (+100 more)

### Community 6 - "cn"
Cohesion: 0.04
Nodes (121): saveBlob(), useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSyncConflict(), useSyncConflicts(), useSyncHistory() (+113 more)

### Community 7 - "device_host.py"
Cohesion: 0.04
Nodes (136): _detach(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore(), Local administration commands, run inside the api container. python -m app.cli… (+128 more)

### Community 8 - "record"
Cohesion: 0.03
Nodes (173): conflict(), forbidden(), AppReplica, A copy of a co-hosted app running on a co-host device (docs/COHOSTING.md…, _actions_report(), _add_cloud_domain(), add_domain(), AppCreate (+165 more)

### Community 9 - "FlatButton"
Cohesion: 0.03
Nodes (51): Control, FontStyle, GraphicsPath, IButtonControl, IDeviceContext, PaintEventArgs, PaintEventArgs, Graphics (+43 more)

### Community 10 - "is_online"
Cohesion: 0.08
Nodes (52): approve_enrollment(), _can_remove_copy(), deny_enrollment(), _enrollment_for_action(), get_device(), list_devices(), move_data_source(), placement_options() (+44 more)

### Community 11 - "client.ts"
Cohesion: 0.03
Nodes (62): ApiClientOptions, ApiError, buildQuery(), client, codeForStatus(), createApiClient(), DownloadResult, FetchFn (+54 more)

### Community 12 - "utcnow"
Cohesion: 0.03
Nodes (179): Backup, BackupCopy, BackupLogSegment, new_id(), datetime, utcnow(), any_copy(), archive_source_logs() (+171 more)

### Community 13 - "cloud_db.py"
Cohesion: 0.09
Nodes (52): encrypt_json(), _cloud_call(), cloud_out(), connect(), connect_firestore(), connect_rtdb(), connect_tables(), _connection() (+44 more)

### Community 14 - "rtdb.py"
Cohesion: 0.05
Nodes (97): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _json_or_text(), list_documents() (+89 more)

### Community 15 - "BackupsTab.tsx"
Cohesion: 0.04
Nodes (120): useDevices(), usePlacementOptions(), Backup, BackupSchedule, DataSourceKind, Device, DeviceCapabilities, DeviceMetrics (+112 more)

### Community 16 - "_job_deploy"
Cohesion: 0.14
Nodes (21): Removes passwords from driver error messages (and other text: `limit=None`…, redact(), _build(), build_image(), _checkout(), _DeployLog, _docker_failure(), _drop_build() (+13 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.04
Nodes (80): ConventionIssue, Entity, LinkCardinality, ProjectSchema, RelationshipCardinality, SourceSchema, CompareSide, edgeTypes (+72 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.06
Nodes (67): CloudflareZone, Domain, ProviderSettings, PublicUrlRequest, PublicUrlResponse, RemoteAccess, RemoteAccessMode, ConfirmDialog() (+59 more)

### Community 19 - "data_browser.py"
Cohesion: 0.12
Nodes (51): check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document(), delete_row(), encode_value() (+43 more)

### Community 20 - "deploys.ts"
Cohesion: 0.06
Nodes (77): useApp(), useApps(), useDeployment(), useDeployments(), App, AppDetectDraft, AppPreset, AppTarget (+69 more)

### Community 21 - "CloudError"
Cohesion: 0.05
Nodes (35): _body(), CloudError, Any, Exception, An AWS / Google Cloud call failed (docs/CLOUD.md). `message` is the provider's…, _api_error(), GcpClient, _name() (+27 more)

### Community 22 - "mcp.py"
Cohesion: 0.08
Nodes (67): _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result(), _limit(), _mongo() (+59 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.10
Nodes (59): Stores a value. `None` or "" deletes the override. Caller commits., set_value(), _active_hostnames(), add_hostname(), apps_tunnel_name(), _cached_zones(), _client(), connector_state() (+51 more)

### Community 24 - "test_monitoring.py"
Cohesion: 0.19
Nodes (20): active(), deliver(), deliver_async(), evaluate(), One evaluation round. Returns the (event, alert) pairs it sent ("open" /…, Open alerts (pending ones haven't lasted long enough yet), critical first., _minute(), record_request() (+12 more)

### Community 25 - "ControlForm"
Cohesion: 0.07
Nodes (18): ContextMenuStrip, IEnumerable, DateTime, Dictionary, EventHandler, Form, IDictionary, int (+10 more)

### Community 26 - "ApiError"
Cohesion: 0.04
Nodes (142): AdminOrServiceKey, ProjectAccess, ApiError, Raise from handlers/services; rendered as {"error": {code, message, details}}., CloudConnection, Project, A user's own AWS or Firebase/Google Cloud credentials (docs/CLOUD.md "Cloud…, BackupPatch (+134 more)

### Community 27 - "Publish"
Cohesion: 0.09
Nodes (22): cache_control(), cloud_env(), content_type(), _export(), Publish, (relative path with /, absolute path) of the regular files under `root`.…, HTML revalidates every time; fingerprinted assets are immutable; everything…, One deployment's publish step; `artifact` / `url` are the results. (+14 more)

### Community 28 - "provisioning.py"
Cohesion: 0.07
Nodes (67): ensure_database(), Creates an empty managed database + dedicated user on this host; returns the…, database_size(), drop_copy(), provision_target(), Project, Creates an empty database for `ds` on the target host. Returns (database_name,…, cap_mariadb_users() (+59 more)

### Community 29 - "write_both"
Cohesion: 0.12
Nodes (28): _check_value(), cohost_problem(), diff(), _eq(), _field(), get_conflict(), history(), open_conflict_counts() (+20 more)

### Community 30 - "firestore.py"
Cohesion: 0.13
Nodes (45): _and(), _bad(), call(), check_path(), _cursor_in(), _cursor_out(), delete_document(), _doc_id() (+37 more)

### Community 31 - "run_job"
Cohesion: 0.11
Nodes (29): Runs the job in a thread of this process (tests replace this with `_run`)., _run(), _spawn(), claim(), _error_text(), heartbeat_key(), BaseException, SessionFactory (+21 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.06
Nodes (26): CloudflareClient, CloudflareError, _cname_body(), Any, ApiError, Exception, Thin Cloudflare API v4 client (docs/REMOTE_ACCESS.md). Only the calls Deployer…, A DNS-only record a cloud target asks for (docs/CLOUD.md "Custom domains"):… (+18 more)

### Community 33 - "get_redis"
Cohesion: 0.08
Nodes (51): get_redis(), dump_source(), DataSource, Path, Writes the source's data entry (transfer.py format) to a local gzip JSON file., restore_into(), call(), CallListener (+43 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (66): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_compose() (+58 more)

### Community 35 - "make_app"
Cohesion: 0.05
Nodes (71): instance_role_name(), `deployer-<slug>-<8 chars of id>`: S3/ECR/App Runner/CloudFront/Cloud Run-safe,…, `deployer-app-<slug>-<id8>`: the App Runner instance role (IAM role names are…, Firebase Hosting site id (globally unique, <= 30 chars)., resource_name(), site_id(), Test hook: `client(config)` returns `factory(config)` (None restores the real…, set_factory() (+63 more)

### Community 36 - "WizardForm"
Cohesion: 0.08
Nodes (17): SetupOptions, bool, Color, Control, DateTime, double, EventArgs, EventHandler (+9 more)

### Community 37 - "ThemedForm"
Cohesion: 0.07
Nodes (19): float, Form, Bitmap, Control, Panel, ThemedForm, Action, bool (+11 more)

### Community 38 - "errors.py"
Cohesion: 0.03
Nodes (120): Dependency factory for routes with a `project_id` path parameter. Usage:…, require_role(), install_error_handlers(), not_found(), FastAPI, role_rank(), api_key_config(), api_key_out() (+112 more)

### Community 39 - "dynamo.py"
Cohesion: 0.11
Nodes (60): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), connection_info(), create_backups() (+52 more)

### Community 40 - "App"
Cohesion: 0.08
Nodes (48): artifact_for(), audience(), builds_on_github(), dispatch(), enqueue_setup(), _merge(), out(), Any (+40 more)

### Community 41 - "auth_headers"
Cohesion: 0.04
Nodes (78): create_invite(), Project, User, Adds an invite (caller commits). Returns (invite, raw token)., auth_headers(), make_user(), _root_mysql(), test_managed_lifecycle_and_roundtrip() (+70 more)

### Community 42 - "test_data_api_keys.py"
Cohesion: 0.07
Nodes (22): create_app(), lifespan(), FastAPI, _check_redis(), health(), get, Response, fixture (+14 more)

### Community 43 - "test_backups_api.py"
Cohesion: 0.07
Nodes (46): local_copy(), perform_verify(), prune_all(), _iso(), datetime, Backup API and orchestration against a fake executor (no database servers or…, A-037: platform snapshots can be downloaded by the instance owner and restored…, Backup copies and restores only go to devices that may serve the project… (+38 more)

### Community 44 - "test_source_sync.py"
Cohesion: 0.19
Nodes (26): _drain(), One sync round before a forced write. Connection trouble aborts the write…, One round for one replica. Returns stats, or None when nothing ran (offline,…, sync_round(), _conflicts(), fixture, parametrize, Co-hosting sync engine (docs/COHOSTING.md) with in-process fakes for both… (+18 more)

### Community 45 - "MCP.md"
Cohesion: 0.09
Nodes (58): CI job: Linux installer (install, CLI, update, uninstall), Notes for AI agents (skill copy, MCP, graphify), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Billable tools need confirm_billing true after the user agrees, Connecting, Destructive tools: dry run, then exact name plus confirm_delete (+50 more)

### Community 46 - "README.md"
Cohesion: 0.05
Nodes (77): Platform data model (UUID-keyed MariaDB tables), Keep-alive hardening of the sign-in task, The 2026-10-05/06 outage (wsl.exe blocked, loop exited), docs/PLATFORMS.md - Platforms and accounts this project uses, Cloudflare tunnel and DNS, Cloudflare API token (four permissions), Connect GitHub (push-to-deploy) and webhooks, Docker Engine inside the deployer WSL distro (default runtime) (+69 more)

### Community 47 - "firestore_admin.py"
Cohesion: 0.08
Nodes (56): backup_delete_summary(), backup_out(), bucket_location(), _call(), clone_spec(), collection_ids(), create_schedule(), database_delete_summary() (+48 more)

### Community 48 - "routers/backups.py"
Cohesion: 0.12
Nodes (46): backup_schema(), create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup(), _download_name() (+38 more)

### Community 49 - "terminal.ts"
Cohesion: 0.11
Nodes (37): MongoQueryResponse, QueryRequest, SqlStatementResult, RowJson(), pretty(), MongoResults(), View, ViewToggle() (+29 more)

### Community 50 - "TempFileResponse"
Cohesion: 0.12
Nodes (30): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), list_transfers(), _my_transfer_job(), _owned_projects(), projects_export() (+22 more)

### Community 51 - "test_rds_tls.py"
Cohesion: 0.12
Nodes (21): _connect_args(), friendly_error(), _hint(), BaseException, A-106: one plain sentence on the likely cause of a connection error, or None…, A-106: a connection error as a plain hint followed by the (redacted) driver…, try_sql(), test_connection_errors_get_a_plain_hint_and_keep_the_driver_text() (+13 more)

### Community 52 - "test_projects.py"
Cohesion: 0.08
Nodes (31): _cloud_cleanup(), create_project(), delete_project(), get_project(), list_projects(), _provisioning(), CurrentUser, DbSession (+23 more)

### Community 53 - "schema_ops.py"
Cohesion: 0.14
Nodes (27): build_create_table(), check_collection_name(), check_identifier(), check_type(), _constraint_name(), create_collection(), create_table(), drop_collection() (+19 more)

### Community 54 - "executors.py"
Cohesion: 0.07
Nodes (22): BackupExecutor, DeviceExecutorUnavailable, local_executor(), Any, datetime, IO, ProgressFn, Protocol (+14 more)

### Community 55 - "CI workflow (ci.yml)"
Cohesion: 0.11
Nodes (27): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: Windows installer checks and DeployerSetup.exe, MongoDB 5.0 to 8.0 upgrade path test, Integration tests may not be skipped, Checks to run before opening a PR (CI runs the same) (+19 more)

### Community 56 - "import_projects"
Cohesion: 0.16
Nodes (25): _api_key_secret(), _app_model(), _cleanup(), dict_to_model(), _external_source(), _fail(), _gunzip(), import_instance() (+17 more)

### Community 57 - "test_clone_failure_hints"
Cohesion: 0.67
Nodes (3): parametrize, A-060: the commonest clone failures end with a plain next step, not only git's…, test_clone_failure_hints()

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.08
Nodes (51): Deployer HTTP API v1, Project API keys (dpl_role_random), Auth endpoints (signup, login, refresh, OAuth), Data sources endpoints and DataSourceInput, Error envelope and common error codes, Export and import endpoints, Health and setup endpoints, Instance settings and users endpoints (+43 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.14
Nodes (3): IntPtr, StringBuilder, IShellLinkW

### Community 60 - "backup_crypto.py"
Cohesion: 0.06
Nodes (49): backup_key(), DecryptingReader, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material(), iter_decrypt() (+41 more)

### Community 61 - "NotebookConsole.tsx"
Cohesion: 0.12
Nodes (44): QueryRun, SavedQuery, newId(), attachSaved(), CELL_PERSIST_MAX, closeTab(), detachSaved(), EMPTY_NOTEBOOK (+36 more)

### Community 62 - "models.py"
Cohesion: 0.02
Nodes (283): get_settings(), SECURITY.md "Query console": loads the Settings, then drops the secrets from…, seal_process(), _b64d(), _b64e(), decrypt_json(), decrypt_secret(), decrypt_with_passphrase() (+275 more)

### Community 63 - "factory"
Cohesion: 0.07
Nodes (59): _job_archive(), _job_copy(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify(), config_of() (+51 more)

### Community 64 - "DeviceExecutor"
Cohesion: 0.10
Nodes (13): copy_artifact(), DeviceExecutor, Any, IO, Path, PathLike, Stores bytes (already encrypted) at `ref` in the device's backup store. Returns…, `backups.register_copy_target` hook: copies an encrypted artifact between… (+5 more)

### Community 65 - "common.ps1"
Cohesion: 0.09
Nodes (42): Add-DeployerFirewallRule(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerArgument(), ConvertTo-DeployerRuntimePath(), ConvertTo-DeployerWslPath(), Disable-DeployerLanAccess() (+34 more)

### Community 66 - "run_queued"
Cohesion: 0.09
Nodes (60): Scheduler tick: every IP_REFRESH_EVERY_S, follow this PC's public IP on every…, refresh_pc_ips(), Test hook: runs queued jobs in creation order in this thread, including jobs…, run_queued(), connection(), base(), create(), _project_with_cloud_things() (+52 more)

### Community 67 - "ApiKeysTab.tsx"
Cohesion: 0.05
Nodes (62): hasLiveReplica(), useCohostEligibility(), useDataSources(), useDataSourcesWithReplicas(), useSchema(), CloudRestoredFrom, DataSource, BackupsTab() (+54 more)

### Community 68 - "docker-compose.yml (production stack)"
Cohesion: 0.13
Nodes (45): CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), Dashboard SPA HTML entry (index.html), /src/main.tsx module entrypoint, Pre-paint theme bootstrap (localStorage deployer.theme), docker-compose.yml (production stack), Compose service: api, backend network (internal, no internet) (+37 more)

### Community 69 - "test_retention.py"
Cohesion: 0.31
Nodes (13): policy(), Backup, BackupPolicy, datetime, GFS retention and log-segment pruning with a compressed clock (pure functions…, seg(), snap(), test_chain_stops_at_the_restore_gap_marker() (+5 more)

### Community 70 - "_call"
Cohesion: 0.38
Nodes (7): _call(), delete_file(), dispatch_workflow(), put_file(), One API call that must answer one of `ok`; anything else is a GitHubError with…, Creates or updates `path` on `branch`; returns the commit sha (None when the…, _repo_path()

### Community 71 - "test_setup.py"
Cohesion: 0.08
Nodes (18): login(), A-003: the forgotten-password recovery run on the Deployer PC (deployer reset-…, _refresh(), test_change_password(), test_logout_revokes(), test_refresh_cookie_secure_follows_request_scheme(), test_refresh_expired(), test_refresh_rotates_and_detects_reuse() (+10 more)

### Community 72 - "DockerCli"
Cohesion: 0.07
Nodes (24): DockerCli, DockerError, _git_env(), parse_size(), _percent(), RuntimeError, (sha, first line of the commit message) of HEAD., Copies `path` out of `image` into the new directory `dest` (docs/CLOUD.md: a… (+16 more)

### Community 73 - "ddl_export.py"
Cohesion: 0.09
Nodes (44): cloud_engine(), The adapter module of an engine reached only through its cloud connection, with…, build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source() (+36 more)

### Community 74 - "source_ops.py"
Cohesion: 0.16
Nodes (42): get_mongo_db(), check_status(), connection_info(), create_collection(), create_table(), delete_document(), delete_row(), drop_collection() (+34 more)

### Community 75 - "client"
Cohesion: 0.10
Nodes (22): (label, zero-argument call) in dependency order; GitHub Actions' workflow /…, teardown_steps(), client(), BaseTransport, Test hook: route the real client's HTTP through this transport., set_transport(), _cel(), _google_identity() (+14 more)

### Community 76 - "_Writer"
Cohesion: 0.14
Nodes (24): _batches(), _dumps(), _from_canonical(), _import_backup_keys(), _json_default(), _mysql_columns(), Any, DataSource (+16 more)

### Community 77 - "fixture"
Cohesion: 0.18
Nodes (12): Redis, Test hook: replace the process-wide client (None resets to a lazily created…, set_redis(), _clean_state(), client(), fake_redis(), migration_db(), _no_dns() (+4 more)

### Community 78 - "make_project"
Cohesion: 0.08
Nodes (61): DeviceProjectGrant, _key(), SessionFactory, Brings the app's copies in line with its live deployment: a row per eligible…, Every scheduler tick: catch up every co-hosted app, then reconcile each online…, replicate(), sweep(), create_move_job() (+53 more)

### Community 79 - "aws_statements"
Cohesion: 0.11
Nodes (19): aws_statements(), Test hook: every statement of every AWS policy (never shown as one policy, IAM…, requirements(), _actions(), _resources(), test_boundary_document_caps_roles_to_deployer_resources(), test_deployer_user_may_only_write_roles_that_carry_the_boundary(), test_policy_covers_databases_and_scopes_the_firewall() (+11 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.05
Nodes (36): API (`/v1/projects/{pid}`), Co-hosting: live two-way database copies and failover websites, Dashboard (for whoever builds it), Database sync (phase 1 - built), Honest limits (phase 2), Honest limits (shown in the dashboard where they matter), Merge model (conflicts), Roles (+28 more)

### Community 81 - "query_console.py"
Cohesion: 0.08
Nodes (37): _call_shell(), _clamp(), _connect_uri(), _enter_read_only(), _error_text(), _first_keyword(), _first_line(), _is_blank() (+29 more)

### Community 82 - "query_log.py"
Cohesion: 0.07
Nodes (43): QueryRun, One console/editor run. The only place query text is stored (audit logs keep…, delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), datetime, DbSession (+35 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.09
Nodes (42): parametrize, test_delete_app_when_cloudflare_fails(), test_apps_tunnel_created_once_cname_moves_and_ingress(), add_host(), assert_no_secrets(), desired(), link(), Remote access endpoints (docs/REMOTE_ACCESS.md) with a fake Cloudflare API and… (+34 more)

### Community 84 - "tests/test_query_console.py"
Cohesion: 0.07
Nodes (46): mongo_uri_password(), _canceller(), Engine, Splits a script into statements (`;` inside strings and comments is respected).…, Why a viewer may not run this script, naming the word that tripped the check…, A callable that stops the statement running on `conn` from another thread (None…, Runs a SQL script; see the module docstring and docs/QUERY_CONSOLE.md for the…, run_sql() (+38 more)

### Community 85 - "set_setting"
Cohesion: 0.14
Nodes (26): set_setting(), test_login_and_signup_share_a_per_ip_limit(), test_providers(), test_signup_when_allowed(), hosted(), fixture, _callback(), _error_of() (+18 more)

### Community 86 - "Write-DeployerInfo"
Cohesion: 0.18
Nodes (38): Assert-Admin(), Get-Context(), Get-OnOffArgument(), Initialize-Engine(), Invoke-Autostart(), Invoke-Backup(), Invoke-Compose(), Invoke-Config() (+30 more)

### Community 87 - "UninstallForm"
Cohesion: 0.06
Nodes (23): StringBuilder, ScriptOutput, ScriptRunner, Dictionary, string, Integration, ShellLinkCoClass, ButtonStyle (+15 more)

### Community 88 - "introspection.py"
Cohesion: 0.09
Nodes (42): get_sql_engine(), match_entity(), `user_id` / `userId` -> `user`; nested paths use the last segment. `id` / `_id`…, Returns the entity that a `<singular>_id` (or `<singular>Id`) field refers to,…, reference_base(), analyze_documents(), apply_mongo_indexes(), approximate_row_counts() (+34 more)

### Community 89 - "FakeCloudflare"
Cohesion: 0.13
Nodes (11): BaseTransport, Test hook: route every client through this transport (None restores the…, set_transport(), fake_cf(), FakeProviders, fake_cf(), FakeCloudflare, fixture (+3 more)

### Community 90 - "install.ps1"
Cohesion: 0.11
Nodes (32): Get-InstallerArgumentString(), Get-SystemFacts(), Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Register-ResumeAfterReboot() (+24 more)

### Community 91 - "DeviceAgent"
Cohesion: 0.14
Nodes (14): _connector(), _describe(), DeviceAgent, Any, Event, Exception, Runs one call before its deadline, or raises `device_busy` without running it.…, A plain-words reason the connection failed, and whether the main Deployer… (+6 more)

### Community 92 - "results.ts"
Cohesion: 0.11
Nodes (27): QueryResponse, SqlQueryResponse, JsonTree(), Node(), CellOutput(), CellResult, response, addPrimaryKeyQuery() (+19 more)

### Community 93 - "By section"
Cohesion: 0.06
Nodes (35): 10. Dashboard data features: databases, data browser, schema, query notebook/terminal, backups, devices, co-hosting, jobs, deploys, 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 3. Query console, query log, saved queries, 4. Backups, PITR, jobs, worker, export/import (+27 more)

### Community 94 - "Core.cs"
Cohesion: 0.09
Nodes (16): bool, double, int, List, string, AppInfo, CheckResult, DeployerCli (+8 more)

### Community 95 - "connections.py"
Cohesion: 0.07
Nodes (64): validation_error(), _key_param(), check_data_source(), _config_hosts(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate (+56 more)

### Community 96 - "test_cohosting_api.py"
Cohesion: 0.11
Nodes (34): fan_out_schema_change(), `table.create|drop` / `collection.create|drop` done on the main server: repeat…, mark_online(), add_version(), conflicted(), fixture, parametrize, Co-hosting API (docs/COHOSTING.md): member flag, eligibility, replicas, the… (+26 more)

### Community 97 - "shell_runner.py"
Cohesion: 0.08
Nodes (34): _as_uid(), _child_env(), _clean_up_slot(), _field(), _kill(), main(), make_server(), mongosh_command() (+26 more)

### Community 98 - ".TestMarkers"
Cohesion: 0.15
Nodes (8): Ports, Control, Dictionary, int, List, string, StringBuilder, SelfTest

### Community 99 - "device_worker.py"
Cohesion: 0.11
Nodes (21): See module docstring., register_copy_target(), Installs the device executor factory and copy target (idempotent)., Removes the hooks installed by `register()` (API shutdown)., register(), unregister(), agent_task(), install() (+13 more)

### Community 100 - "get_schema"
Cohesion: 0.15
Nodes (29): create_collection(), create_link(), create_table(), delete_link(), _drop(), drop_collection(), drop_table(), export_schema() (+21 more)

### Community 101 - "PitrFake"
Cohesion: 0.12
Nodes (9): Any, Test hook: `client(config)` returns `factory(config)` (None restores the real…, set_factory(), aws(), fixture, aws(), PitrFake, fixture (+1 more)

### Community 102 - "device_local.py"
Cohesion: 0.17
Nodes (28): device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to() (+20 more)

### Community 103 - "conventions.py"
Cohesion: 0.14
Nodes (26): check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural(), _issue() (+18 more)

### Community 104 - "useTerminalConsole.ts"
Cohesion: 0.14
Nodes (31): useSourceSchema(), addHistoryEntry(), HISTORY_LIMIT, HistoryEntry, historyKey(), isEntry(), loadHistory(), DEFAULT_PREFS (+23 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.19
Nodes (28): _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query(), get_version(), list_saved_queries() (+20 more)

### Community 106 - "deploy_params"
Cohesion: 0.14
Nodes (24): cohost_devices(), copy_problem(), deploy_params(), device_env(), device_problem(), eligible_devices(), _main_secrets(), App (+16 more)

### Community 107 - "test_github_actions.py"
Cohesion: 0.11
Nodes (46): provider_id(), `deployer-gha-<slug>-<id8>` (IAM role names are <= 64 characters)., The role's name from the app's slug and id alone (a teardown knows it after the…, `gh-<id8>`: the app's workload identity provider in the shared pool., (label, call) removing what the setup made; the shared OIDC provider / pool…, Removes the `deployer-gha-*` roles (tagged managed-by=deployer) / `gh-*`…, role_name(), role_name_for() (+38 more)

### Community 108 - "Invoke-Update"
Cohesion: 0.12
Nodes (28): Invoke-Start(), Invoke-Update(), Start-Stack(), Get-BuildSource(), Get-LocalDeploySource(), Resolve-Source(), Write-CheckResult(), ConvertTo-DeployerStateTable() (+20 more)

### Community 109 - ".Ask"
Cohesion: 0.06
Nodes (19): DeployerSetup, FormClosingEventArgs, Dictionary, InstallLocator, Action, Color, DialogResult, int (+11 more)

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
Nodes (39): Data browser (SQL rows, MongoDB documents), Schema endpoints, SchemaLink and ConventionIssue, Database Planning Conventions, Conventions panel (advisory warnings), Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle), ERD crow's-foot notation (+31 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (6): Register-DeployerTask(), Test-DeployerDockerDesktopCrashedSince(), Test-DeployerWslDistroDiskMissing(), Get-ChildItem(), Get-ItemProperty(), Register-ScheduledTask()

### Community 115 - "AwsClient"
Cohesion: 0.06
Nodes (32): AwsClient, _code(), Exception, (`pending` | `available` | `failed` | `deleting` | `deleted`, AWS's failure…, Deletes the VPC's NAT gateway, waits until AWS has removed it (bounded) and…, Deletes the private subnets; the deleted connector's network interfaces hold…, A DynamoDB gateway endpoint in the VPC (free, created once, shared): an App…, One DynamoDB API call by its AWS name (`Query`, `PutItem`, `CreateTable`...)… (+24 more)

### Community 116 - "backup_engine.py"
Cohesion: 0.11
Nodes (50): ArtifactWriter, check_db_name(), compare_counts(), _index_path(), _latest_oplog_ts(), _load_index(), _managed_user_for(), mariadb_archive_logs() (+42 more)

### Community 118 - "test_devices_local.py"
Cohesion: 0.09
Nodes (21): http_host_allowed(), insecure_primary_allowed(), Returns the normalized origin (`scheme://host[:port]`) or raises 422…, validate_primary_url(), fake_primary(), FakePrimary, fixture, parametrize (+13 more)

### Community 119 - "test_firestore.py"
Cohesion: 0.16
Nodes (19): base(), connect(), docs_url(), _fail(), FakeFirestore, gcp(), fixture, Cloud Firestore engine, phase C2-3 (docs/CLOUD.md): a Firebase project's… (+11 more)

### Community 120 - "RowDialog.tsx"
Cohesion: 0.09
Nodes (29): DiffChange, Field, FieldDiff, SchemaDiffEntity, AttributeChange, CHANGE_LABELS, CHANGE_ORDER, DiffSummary (+21 more)

### Community 121 - "compilerOptions"
Cohesion: 0.07
Nodes (26): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+18 more)

### Community 122 - "App"
Cohesion: 0.13
Nodes (25): add_domain(), check_domain(), _client_for(), cloud_url(), _create_cf_records(), _delete_cf_records(), enqueue_teardown(), go_live() (+17 more)

### Community 123 - "test_rtdb.py"
Cohesion: 0.17
Nodes (18): base(), connect(), _fail(), FakeRtdb, gcp(), fixture, Firebase Realtime Database engine, phase C2-4 (docs/CLOUD.md): a Firebase…, FakeCloud for the hosting calls, plus an in-memory Realtime Database behind… (+10 more)

### Community 124 - "get_source"
Cohesion: 0.22
Nodes (25): cohosting_eligibility(), create_replica(), delete_replica(), get_conflict(), list_conflicts(), list_replicas(), DataSource, DbSession (+17 more)

### Community 125 - "OutputWindow"
Cohesion: 0.13
Nodes (12): bool, Color, FormClosedEventArgs, Panel, string, TextBox, LogWindow, OutputWindow (+4 more)

### Community 126 - "How the main code paths work"
Cohesion: 0.08
Nodes (24): 1. Signing in, 2. A data API request with an API key, 3. Running a query in the console or notebook, 4. Push-to-deploy, 5. Backups and point-in-time recovery, 6. A co-hosting sync round, 7. Deploying to the cloud, 8. Installing, updating and staying up (+16 more)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.09
Nodes (25): binlog_name_with_seq(), binlog_seq(), count_insert_rows(), _count_row_tuples(), DumpScanner, Number of `(...)` row tuples in a fragment of an extended INSERT (strings…, (table, rows) for the first line of an extended INSERT in a mariadb-dump, else…, Collects the consistent point and exact row counts from mariadb-dump output… (+17 more)

### Community 128 - "cloud_secrets.py"
Cohesion: 0.17
Nodes (20): cleanup(), enabled(), out(), App, App secrets in AWS Secrets Manager / Google Secret Manager (docs/CLOUD.md…, Deletes the secrets the live version no longer references - after the rollout,…, Records what is in the store. `enabled` is re-read from the row first: an admin…, Keeps `stored` (what is in the store now) so switching off still deletes them… (+12 more)

### Community 129 - "FakeDockerCli"
Cohesion: 0.11
Nodes (7): Test hook: replace the process-wide client (None resets to the real CLI)., set_docker(), FakeDockerCli, Records the call sequence; `fail_at = <step>` makes that step raise;…, docker(), _symlink(), test_build_image_refuses_symlinks_out_of_the_checkout()

### Community 130 - "integration/test_query_console.py"
Cohesion: 0.12
Nodes (26): MySQL / MariaDB: the master user must use TLS. RDS for PostgreSQL 15+ already…, _require_tls(), build_sql_engine(), Engine, mariadb(), mongo(), fixture, Query console against real servers (docs/QUERY_CONSOLE.md). - SQL: a throwaway… (+18 more)

### Community 131 - "dependencies"
Cohesion: 0.09
Nodes (23): @codemirror/autocomplete, @codemirror/lang-javascript, @codemirror/lang-sql, @codemirror/language, @dagrejs/dagre, dependencies, @codemirror/autocomplete, @codemirror/lang-javascript (+15 more)

### Community 132 - "QueryEditor.tsx"
Cohesion: 0.12
Nodes (18): COLLECTION_METHODS, ConsoleAction, CURSOR_METHODS, DB_METHODS, editorKeys, EditorMode, editorTheme(), isIdentifier() (+10 more)

### Community 133 - "build_export_file"
Cohesion: 0.15
Nodes (23): projects_import(), projects_import_job(), Form, ProjectCreator, Upload, then a job: the file is checked and decrypted here (a wrong passphrase…, _read_projects_upload(), _save_upload(), setup_import() (+15 more)

### Community 134 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+13 more)

### Community 135 - "NativeMethods"
Cohesion: 0.11
Nodes (14): DllImport, bool, EventArgs, KeyEventArgs, CheckOption, int, IntPtr, MEMORYSTATUSEX (+6 more)

### Community 136 - "test_data_sources.py"
Cohesion: 0.11
Nodes (6): fake_connect(), fixture, Route tests for data sources, schema, links and the SQL data browser. External…, sqlite_engine(), test_create_external_sql_source(), test_update_external_source_in_place()

### Community 137 - "devDependencies"
Cohesion: 0.10
Nodes (21): devDependencies, eslint, @eslint/js, eslint-plugin-react-hooks, @types/node, @types/react, typescript, typescript-eslint (+13 more)

### Community 138 - "switch_public_url"
Cohesion: 0.33
Nodes (14): add_hostname(), get_remote_access(), link(), DbSession, delete, get, InstanceOwner, post (+6 more)

### Community 139 - "cloud_aws.py"
Cohesion: 0.10
Nodes (19): client(), free_blocks(), _nat_alive(), nat_name(), _ours(), _public_subnet(), The AWS calls behind the AWS hosting targets (docs/CLOUD.md), one small method…, Removes the private route table (its subnet associations first). (+11 more)

### Community 140 - "diff_schemas"
Cohesion: 0.22
Nodes (18): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), Any, Diff two `SourceSchema` dicts (docs/BACKUPS.md "Version history",… (+10 more)

### Community 141 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.25
Nodes (18): Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Caddy :8081 tunnel-only listener, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes (+10 more)

### Community 142 - "test_conventions.py"
Cohesion: 0.44
Nodes (17): check_conventions(), entity(), field(), _link(), mongo_source(), rules(), sql_source(), test_errored_sources_are_skipped() (+9 more)

### Community 143 - "test_transfer_stream.py"
Cohesion: 0.13
Nodes (16): PathLike, A source's `data` entry parsed lazily from `fh`: `tables` / `collections` and…, Restores a gzip JSON `data` entry (write_source_data) into a source on this…, read_data_entry(), restore_file(), _dump(), fake_engine(), FakeConn (+8 more)

### Community 144 - "Logo"
Cohesion: 0.33
Nodes (5): Icon, AppIcon, Bitmap, Color, Logo

### Community 145 - "supervisor.sh"
Cohesion: 0.32
Nodes (15): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), pid_alive(), read_desired(), supervisor.sh script (+7 more)

### Community 146 - ".get"
Cohesion: 0.14
Nodes (16): check_changes(), ext(), _merge_warnings(), _mongo_change(), Any, ApiError, BSON value/document -> canonical extended JSON (plain JSON types)., Validates the shape of changes received over RPC (values are bound, names are… (+8 more)

### Community 147 - "Path"
Cohesion: 0.09
Nodes (38): BackupEngineError, _check_exit(), _fetch_binlog(), _load_dump(), mariadb_defaults_file(), _mongo_build_oplog(), mongo_config_file(), _mongo_load_archive() (+30 more)

### Community 148 - "DataSource"
Cohesion: 0.19
Nodes (20): collection_entity(), collection_ids(), composite_indexes(), connection_info(), _count(), database_of(), display(), _documents() (+12 more)

### Community 149 - "ResultsGrid.tsx"
Cohesion: 0.22
Nodes (16): BOM, Cell, csvField(), exportCsv(), exportFilename(), exportJson(), ExportTable, rowsToObjects() (+8 more)

### Community 150 - "test_mcp.py"
Cohesion: 0.08
Nodes (21): make_source(), providers(), fixture, sqlite_engine(), test_external_sources_have_no_backups(), env(), fixture, MCP server for AI agents (docs/MCP.md): JSON-RPC over POST… (+13 more)

### Community 151 - "github_repos"
Cohesion: 0.19
Nodes (13): github_connect(), github_repos(), github_status(), CurrentUser, DbSession, ge, get, le (+5 more)

### Community 152 - "metrics.py"
Cohesion: 0.19
Nodes (19): _avg(), container_problem(), containers(), current_host(), _hist(), host_points(), metrics(), p95() (+11 more)

### Community 153 - "test_firestore_admin.py"
Cohesion: 0.25
Nodes (18): base(), connected(), gcp(), fixture, Job, Firestore databases, managed exports and scheduled backups (docs/CLOUD.md…, run_job(), test_backup_schedules_backups_and_restore() (+10 more)

### Community 154 - "key_hash"
Cohesion: 0.19
Nodes (9): key_hash(), FakeSide, FakeStore, Crash between apply and position update: the replay changes nothing and opens…, Each round waits at a barrier for the other: this only passes when they run…, test_device_side_speaks_rpc_and_drops_unexpected_fields(), test_prune_forgets_old_agreed_versions_but_not_conflicted_keys(), test_reapplying_a_batch_is_a_no_op() (+1 more)

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.09
Nodes (35): Release workflow (release.yml), Optional code signing with signtool, Release job: build and push GHCR images, Pre-release tags never become latest, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09) (+27 more)

### Community 157 - "test_device_rpc.py"
Cohesion: 0.18
Nodes (16): _fresh(), _hello(), Primary-side device RPC: Redis pub/sub routing, the control WebSocket and…, Polls `predicate` (the server handles socket messages on its own threads, so…, test_call_fails_when_connection_replaced(), test_call_offline_device(), test_call_roundtrip_and_errors(), test_call_timeout() (+8 more)

### Community 158 - "test_backups_pitr.py"
Cohesion: 0.15
Nodes (22): ensure_mongo_replica_set(), Initiates the single-node replica set `rs0` if needed. Returns a short status…, _redact(), _secrets(), dispose_all(), Test hook: drop every cached engine/client (like the provisioning…, _iso(), _pause() (+14 more)

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
Cohesion: 0.36
Nodes (7): text(), DIFF_MAX_LINES, DiffLine, diffStats(), lineDiff(), lines(), render()

### Community 166 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.20
Nodes (10): AWS policy split as built: purpose-sized managed policies, C2 - cloud databases (what is left), Cloud hosting and databases (AWS, Firebase), Code, API, dashboard, Deleting a cloud database over the API and MCP (as built), Not verified against real clouds, Not verified against real clouds, Principles (+2 more)

### Community 167 - "wslplatform.tests.ps1"
Cohesion: 0.15
Nodes (3): Initialize-WslPlatform(), Get-WindowsOptionalFeature(), Test-Reboot()

### Community 168 - "SettingsDialog"
Cohesion: 0.29
Nodes (4): Action, Func, SettingsDialog, Action

### Community 169 - "_payload"
Cohesion: 0.43
Nodes (7): _export_handler(), _payload(), test_export_fails_when_device_offline(), test_instance_import_offline_device_restores_on_main(), test_instance_import_onto_connected_device(), test_projects_import_checks_device_eligibility(), _wipe()

### Community 170 - "ThemeProvider.tsx"
Cohesion: 0.23
Nodes (10): labels, next, ThemeToggle(), initialMode(), subscribe(), ThemeProvider(), THEME_STORAGE_KEY, ThemeContext (+2 more)

### Community 171 - "C2-3 as built: Cloud Firestore"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project, API, Apps on Cloud Run, Browsing, editing, querying, C2-3 as built: Cloud Firestore, Data model, MCP, Not verified against real clouds (+1 more)

### Community 172 - "Deploy a website with Deployer"
Cohesion: 0.17
Nodes (12): Cloud targets (AWS / Firebase through Deployer), Co-host PCs (the same app on other PCs, with failover), Connecting an AI agent (MCP), Deploy a website with Deployer, Do / don't, Feature status (check before promising anything), Hard rule: always ask which platform, People, sign-in and co-hosting (+4 more)

### Community 173 - "readOnly.ts"
Cohesion: 0.38
Nodes (9): checkMongoReadOnly(), checkReadOnly(), checkSqlReadOnly(), firstKeyword(), MONGO_WRITE_NAMES, MONGO_WRITE_RE, ReadOnlyCheck, splitSqlStatements() (+1 more)

### Community 174 - "C3 as built: GitHub Actions builds (pushes deploy with the PC off)"
Cohesion: 0.18
Nodes (11): API, C3 as built: GitHub Actions builds (pushes deploy with the PC off), Dashboard, MCP, Not verified against real clouds, Permissions added, Reports, Deploy now, runs, Switching back, teardown (+3 more)

### Community 175 - "C2-1 as built: cloud databases in AWS (RDS / Aurora)"
Cohesion: 0.22
Nodes (9): API, Apps, C2-1 as built: cloud databases in AWS (RDS / Aurora), Data model, MCP, Networking (the trade-off), Not verified against real clouds, Permissions added (now in the `DeployerDatabases` policy, shown in Settings -> Cloud accounts) (+1 more)

### Community 176 - "C1 as built"
Cohesion: 0.22
Nodes (9): API, C1 as built, Cloud connections, Custom domains, Dashboard, MCP, Not verified against real clouds, Targets (`apps.target`) (+1 more)

### Community 177 - "Invoke-StatusJson"
Cohesion: 0.12
Nodes (9): Invoke-StatusJson(), Get-DeployerComposeServices(), Get-DeployerHealth(), Get-DeployerNonPrivateNetworks(), Read-DeployerState(), Test-DeployerTaskRegistered(), Wait-DeployerHealth(), Write-DeployerNetworkProfileWarning() (+1 more)

### Community 178 - "Condition"
Cohesion: 0.26
Nodes (15): _api_rule(), _backup_rules(), _cloud_cleanup_rule(), Condition, conditions(), _container_rules(), _fmt_age(), _fmt_gb() (+7 more)

### Community 179 - ".transfer"
Cohesion: 0.16
Nodes (11): _dt(), datetime, SyncConflict, Applies `side`'s changes to the other copy (`target`)., test_skipped_views_and_triggers_warn_at_export_and_import(), inline_jobs(), fixture, A-043: a payload too big to unpack in memory is refused with a clear 413, not… (+3 more)

### Community 180 - "run_due"
Cohesion: 0.16
Nodes (11): _failed(), prune_versions(), Event, One pass over the replicas due for a round, up to ROUND_WORKERS at a time.…, Forgets keys whose copies have agreed for `days` (no newer version, no open…, Background task of the worker: rounds every 2 s while this worker leads the…, record_error(), run_due() (+3 more)

### Community 181 - "sync_desired"
Cohesion: 0.21
Nodes (13): fix_state_ownership(), Path, Atomically writes desired.json (0600). Returns False (and remembers the error)…, A-082: hands the shared volume back to uid 10001 (the API and the sidecar) when…, Writes desired.json only when it differs from the stored settings., Re-creates desired.json after a volume reset. Silently skipped outside the…, _read_json(), read_status() (+5 more)

### Community 182 - "test_migration_table_options.py"
Cohesion: 0.25
Nodes (6): head_db_url(), fixture, Migration checks: every migration table gets the utf8mb4 options, and head…, A scratch database upgraded to head: SQLite always, and a throwaway database on…, `create_all` builds the test schema, so a model change without a migration…, test_migrations_match_the_models()

### Community 183 - "main"
Cohesion: 0.28
Nodes (13): acquire_leadership(), _guard(), _load_plugins(), main(), mongo_replset_loop(), Event, Redis, Thread (+5 more)

### Community 184 - "apply_changes"
Cohesion: 0.20
Nodes (9): apply_changes(), _norm(), _project(), Canonical form for comparing versions read from a binlog and from a SELECT., SQL rows are compared on the version's columns (a copy may have extra columns)., Applies changes in order; returns one outcome per change: `{"result":…, MongoDB: `change` is the echo of a write the sync made on `side` (consumed…, row_hash() (+1 more)

### Community 186 - "test_api_docs_routes.py"
Cohesion: 0.52
Nodes (6): _documented(), _norm(), _paths(), Every endpoint the docs name must exist in the router (A-189). Checked: `|…, _routes(), test_documented_endpoints_exist()

### Community 187 - "test_release_workflow.py"
Cohesion: 0.33
Nodes (6): _permissions(), A-149: the release workflow is read-only by default; only the jobs that publish…, Every `permissions:` block at this indent, as {scope: level}., A-190: a tag that fails CI publishes nothing, and an RC never becomes `latest`., test_images_wait_for_ci_and_prereleases_skip_latest(), test_release_workflow_permissions_are_per_job()

### Community 188 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 189 - "Invoke-Preflight"
Cohesion: 0.48
Nodes (5): Invoke-Preflight(), Get-DeployerAppPortUsers(), Test-DeployerAppPort(), Get-NetTCPConnection(), Get-Process()

### Community 192 - "dec"
Cohesion: 0.23
Nodes (9): dec(), enc(), enc_row(), _q(), One binlog row image pair -> change dicts (a primary key update becomes delete…, SQL value -> JSON-safe value (tagged for types JSON can't carry)., row_changes(), test_primary_key_update_becomes_delete_and_insert() (+1 more)

### Community 193 - "exports_dir"
Cohesion: 0.67
Nodes (4): export_path(), exports_dir(), Path, Finished export files of the API process; `prune_exports` deletes them after…

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

### Community 230 - "test_devices_agent.py"
Cohesion: 0.24
Nodes (9): read_status(), fixture, The device agent against a real uvicorn server (WebSocket client,…, A-050: a call that waited out its timeout for a slot is answered device_busy…, server(), test_agent_connects_serves_calls_and_detaches(), test_agent_reports_rejection(), test_agent_skips_calls_whose_deadline_passed_and_keeps_short_calls_free() (+1 more)

### Community 231 - "sample"
Cohesion: 0.20
Nodes (9): _iso(), Event, One sample of the host and the containers (worker only: it has the Docker…, Worker background task: `sample()` every SAMPLE_EVERY_S., sample(), sample_loop(), FakeDocker, test_docker_stats_parses_ps_inspect_and_stats() (+1 more)

### Community 251 - "handle"
Cohesion: 0.27
Nodes (10): Access, handle(), mcp_endpoint(), DbSession, JSONResponse, post, Request, Response (+2 more)

### Community 252 - "consoleMode.ts"
Cohesion: 0.31
Nodes (8): DEFAULT_QUERY_CONSOLE_MODE, listeners, loadQueryConsoleMode(), QUERY_CONSOLE_MODE_KEY, QUERY_CONSOLE_MODES, QueryConsoleMode, saveQueryConsoleMode(), subscribe()

### Community 253 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

### Community 254 - "test_managed_db_connection_cap.py"
Cohesion: 0.39
Nodes (5): FakeConn, _patch_engine(), A-025: managed MariaDB users get a connection cap, so one app can't use up the…, test_existing_managed_users_are_capped_and_others_left_alone(), test_new_managed_user_is_created_with_the_cap()

### Community 255 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.25
Nodes (8): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, New databases, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

### Community 256 - "check"
Cohesion: 0.29
Nodes (7): _firebase_listing(), check(), database_problem(), describe(), list_databases(), `connections.try_source` for Firestore: the database answers and is in native…, The Firestore databases of the connection's project, with why Deployer can't…

### Community 257 - "id_candidates"
Cohesion: 0.43
Nodes (6): id_candidates(), Possible `_id` values for the string form used in URLs: ObjectId hex, then a…, Document ids in URLs are strings; the resolver must try every `_id` type a user…, test_integer_ids_are_tried_before_the_string_form(), test_object_id_then_string(), test_out_of_range_or_non_numeric_stay_strings()

### Community 258 - "_fake_binlog"
Cohesion: 0.33
Nodes (7): _fake_binlog(), Replaces the binlog reader: `binlog` is [(seq, [rows of one WriteRowsEvent,…, A-011: one bulk transaction used to be read whole (over the RPC size cap, stuck…, A change that fits the RPC cap alone must not be piled onto an almost full…, _read_all(), test_big_row_is_sent_in_a_batch_of_its_own(), test_transaction_bigger_than_a_batch_is_split_across_rounds()

### Community 259 - "get_summary"
Cohesion: 0.47
Nodes (6): get_metrics(), get_summary(), list_alerts(), get, InstanceOwner, visible()

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

### Community 266 - "collect_metrics"
Cohesion: 0.40
Nodes (5): collect_metrics(), _cpu_percent(), disk_space(), (free, total, label) of whichever disk has less free space: `/` (the Docker…, _uptime()

### Community 268 - "replica"
Cohesion: 0.40
Nodes (5): fixture, replica(), _sql(), test_mariadb_two_way_sync(), test_mongodb_two_way_sync()

### Community 269 - "G3 as built: a permissions boundary for the roles Deployer creates"
Cohesion: 0.40
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

## Knowledge Gaps
- **531 isolated node(s):** `docker-entrypoint.sh script`, `deployer-api`, `name`, `private`, `version` (+526 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **27 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ControlForm` connect `ControlForm` to `shell_runner.py`, `.TestMarkers`, `ThemedForm`, `FlatButton`, `.Ask`, `UninstallForm`, `OutputWindow`?**
  _High betweenness centrality (0.260) - this node is a cross-community bridge._
- **Why does `ApiError` connect `ApiError` to `deps.py`, `integration/test_query_console.py`, `DataSource`, `AuditLog`, `build_export_file`, `device_host.py`, `record`, `_Watchdog`, `is_online`, `utcnow`, `cloud_db.py`, `rtdb.py`, `_job_deploy`, `.get`, `Path`, `data_browser.py`, `CloudError`, `mcp.py`, `services/remote_access.py`, `key_hash`, `Publish`, `provisioning.py`, `write_both`, `firestore.py`, `test_device_rpc.py`, `CloudflareClient`, `get_redis`, `errors.py`, `dynamo.py`, `App`, `auth_headers`, `test_backups_api.py`, `test_source_sync.py`, `firestore_admin.py`, `routers/backups.py`, `TempFileResponse`, `Condition`, `test_projects.py`, `schema_ops.py`, `run_due`, `import_projects`, `FakeDevice`, `models.py`, `factory`, `DeviceExecutor`, `dec`, `source_ops.py`, `_Writer`, `make_project`, `query_console.py`, `query_log.py`, `tests/test_query_console.py`, `DeviceAgent`, `connections.py`, `test_cohosting_api.py`, `get_schema`, `device_local.py`, `test_devices_agent.py`, `saved_queries.py`, `backup_engine.py`, `test_devices_local.py`, `App`, `get_source`, `test_backups_engine.py`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Why does `parseError()` connect `client.ts` to `useToast`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Are the 120 inferred relationships involving `ApiError` (e.g. with `ProjectAccess` and `AppCreate`) actually correct?**
  _`ApiError` has 120 INFERRED edges - model-reasoned connections that need verification._
- **What connects `docker-entrypoint.sh script`, `deployer-api`, `name` to the rest of the system?**
  _531 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `deps.py` be split into smaller, more focused modules?**
  _Cohesion score 0.047879616963064295 - nodes in this community are weakly interconnected._
- **Should `States.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.04082259054634745 - nodes in this community are weakly interconnected._