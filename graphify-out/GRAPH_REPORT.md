# Graph Report - Deployer  (2026-10-20)

## Corpus Check
- 495 files · ~598,097 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 8328 nodes · 27522 edges · 267 communities (246 shown, 21 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 1755 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c32827df`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Publish
- cn
- device_executor.py
- deploys.ts
- DbSession
- types.ts
- services/devices.py
- FlatButton
- client.ts
- firestore_admin.py
- data_browser.py
- metrics.py
- AwsClient
- record
- States.tsx
- services/remote_access.py
- eligibility.ts
- auth.py
- services/cloud.py
- test_devices_local.py
- firestore.py
- ControlForm
- services/jobs.py
- mcp.py
- WizardForm
- make_app
- User
- cloud_deploy.py
- BackupsTab.tsx
- CloudError
- github.py
- get_sessionmaker
- test_setup.py
- notebook.ts
- get_settings
- services/backups.py
- test_data_sources.py
- routers/backups.py
- github_actions.py
- .Rebuild
- terminal.ts
- utcnow
- get_source
- dynamo.py
- conventions.py
- NotebookConsole.tsx
- rtdb.py
- connections.py
- SchemaTab.tsx
- members.py
- test_source_sync.py
- useToast
- DockerCli
- ddl_export.py
- make_user
- ProjectAccess
- OutputWindow
- common.ps1
- data_sources.py
- services/transfer.py
- CloudflareClient
- source_sync.py
- crowsfoot.ts
- factory
- CloudflareSetup.tsx
- install.ps1
- source_ops.py
- test_device_rpc.py
- test_remote_access.py
- IShellLinkW
- saved_queries.py
- deployer.ps1
- crypto.py
- DeviceExecutor
- test_auth.py
- models.py
- test_apps_api.py
- test_cloud_boundary.py
- run_queued
- cloud_db.py
- useTerminalConsole.ts
- Usability for non-experts
- get_schema
- device_agent.py
- introspection.py
- backup_engine.py
- .Ask
- .TestMarkers
- Handover
- App
- get_redis
- tests/test_query_console.py
- handle
- device_local.py
- Backups, Versions & Recovery
- deployments.py
- device_apps.py
- LocalExecutor
- run
- MessageDialog
- api_key_config
- test_dynamo.py
- C1 as built
- ._c
- mongo_snapshot
- shell_runner.py
- shared_fixtures.py
- test_firestore.py
- _wrap
- Any
- cloud_secrets.py
- auth_headers
- RowDialog.tsx
- compilerOptions
- deps.py
- query_console.py
- test_github_actions.py
- test_rtdb.py
- test_mcp.py
- test_oauth.py
- run_query
- UninstallForm
- FakeCloudflare
- Domain
- _run_tool
- FakeAdmin
- backup_crypto.py
- FakeDockerCli
- integration/test_query_console.py
- dependencies
- results.ts
- NativeMethods
- Path
- set_setting
- QueryEditor.tsx
- compilerOptions
- instance_settings.py
- devDependencies
- ApiError
- integrations.py
- diff_schemas
- test_firestore_admin.py
- rate_limit.py
- cloud_aws.py
- CI job: Installer (PowerShell checks, dry run, DeployerSetup.exe)
- database_options
- write_both
- DataSource
- viewer
- supervisor.sh
- Host Devices
- Deployer
- SourceReplica
- eslint
- README.md
- Remote Access & Custom Domains (Cloudflare)
- SqlStore
- run_mongosh
- SettingsDialog
- C3 as built: GitHub Actions builds (pushes deploy with the PC off)
- Deployer HTTP API v1
- Query Console
- test_backups_engine.py
- apiSnippets.ts
- main.py
- test_query_log.py
- Compose service: dashboard (static nginx)
- _replay_binlogs
- C2-2 as built: DynamoDB
- API runtime dependencies (requirements.txt)
- Query Editor (Supabase-style) & Query Log
- Deploy a website with Deployer
- By section
- consoleMode.ts
- docker-compose.yml (production stack)
- Data API with API keys
- Deployments (push-to-deploy) — phase 4
- wslplatform.tests.ps1
- C2-3 as built: Cloud Firestore
- test_container_config.py
- C2-4 as built: Firebase Realtime Database
- device_host.py
- C2-1 as built: cloud databases in AWS (RDS / Aurora)
- lan.tests.ps1
- C2-5 as built: MCP, transfer, project delete
- Contributing to Deployer
- Co-hosting: live two-way database copies and failover websites
- test_transfer_devices.py
- test_cloud_policies.py
- Invoke-Update
- mongo.tests.ps1
- FakeDevice
- test_api_docs_routes.py
- test_release_workflow.py
- scripts
- Monitoring and alerts
- sql_read_only_refusal
- Release job: build and push GHCR images (api, dashboard, tunnel)
- keepalive.tests.ps1
- _clean_up_slot
- 0010_cohost_apps.py
- test_dead_code.py
- test_fixture_layout.py
- test_migration_table_options.py
- test_query_docs.py
- test_skill_doc.py
- test_version.py
- package.json
- setup-engine.sh
- .__init__
- 0011_cloud.py
- 0012_datetime_microseconds.py
- test_migrations_mariadb.py
- test_ci_workflow.py
- test_docs_index.py
- test_roadmap_doc.py
- tsconfig.json
- docker-entrypoint.sh
- @tanstack/react-query
- eslint-plugin-react-refresh
- globals
- tailwindcss
- @tailwindcss/vite
- @types/react-dom
- entrypoint.sh
- upgrade.sh
- Cloud hosting and databases (AWS, Firebase)
- role_name
- .delete_nat_gateway
- deployer-api
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
- .ensure_github_role
- C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway)
- Invoke-Preflight
- .create_service
- .ensure_vpc_connector
- check
- Firestore point-in-time recovery and deletes (as built)
- G1 as built: app secrets in a secret store, environment changes without a rollback
- G3 as built: a permissions boundary for the roles Deployer creates

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
- `deployer-deploy.zip release asset` --references--> `docker-compose.yml (production stack)`  [INFERRED]
  .github/workflows/release.yml → deploy/docker-compose.yml
- `pymongo` --calls--> `Compose service: mongodb (profile mongodb, replica set rs0)`  [INFERRED]
  api/requirements.txt → deploy/docker-compose.yml
- `PowerShell parse and ASCII-only check` --implements--> `PowerShell conventions`  [INFERRED]
  .github/workflows/ci.yml → CONTRIBUTING.md
- `Release job: build and push GHCR images (api, dashboard, tunnel)` --references--> `Compose service: api`  [INFERRED]
  .github/workflows/release.yml → deploy/docker-compose.yml
- `Release job: build and push GHCR images (api, dashboard, tunnel)` --references--> `Compose service: dashboard (static nginx)`  [INFERRED]
  .github/workflows/release.yml → deploy/docker-compose.yml

## Import Cycles
- 3-file cycle: `api/app/services/deployments.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 3-file cycle: `api/app/services/device_host.py -> api/app/services/transfer.py -> api/app/services/devices.py -> api/app/services/device_host.py`
- 4-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 4-file cycle: `api/app/services/deployments.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 4-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/device_moves.py -> api/app/services/backups.py`
- 4-file cycle: `api/app/services/cohost_apps.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 4-file cycle: `api/app/services/cohosting.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py`
- 5-file cycle: `api/app/services/cloud_db.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py -> api/app/services/cloud_db.py`
- 5-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/device_apps.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`

## Hyperedges (group relationships)
- **Backup protection layers for a managed database** — docs_backups_snapshots, docs_backups_pitr, docs_backups_safety_snapshots, docs_backups_recently_deleted, docs_backups_platform_backup, docs_backups_verification [EXTRACTED 1.00]
- **Device runtime protocol (control channel, RPC routing, methods, transfers)** — docs_devices_control_channel, docs_devices_rpc_routing, docs_devices_rpc_methods, docs_devices_bulk_transfers [EXTRACTED 1.00]
- **Cloudflare tunnel stack (link, sidecar, supervisor, handshake files, Caddy 8081)** — docs_remote_access_link_step, docs_remote_access_tunnel_sidecar, docs_remote_access_supervisor, docs_remote_access_desired_status_files, docs_remote_access_caddy_8081 [INFERRED 0.85]
- **Tag-triggered release pipeline (images, setup exe, bundle)** — github_workflows_release_images, github_workflows_release_setup_exe, github_workflows_release_bundle [EXTRACTED 1.00]

## Communities (267 total, 21 thin omitted)

### Community 0 - "Publish"
Cohesion: 0.10
Nodes (19): cache_control(), cloud_env(), content_type(), _export(), Publish, (relative path with /, absolute path) of the regular files under `root`.…, HTML revalidates every time; fingerprinted assets are immutable; everything…, One deployment's publish step; `artifact` / `url` are the results. (+11 more)

### Community 1 - "cn"
Cohesion: 0.04
Nodes (106): isDeviceOffline(), useSyncConflict(), useSyncConflicts(), useSyncHistory(), SyncConflict, SyncSide, AlertBadge(), GoogleIcon() (+98 more)

### Community 2 - "device_executor.py"
Cohesion: 0.08
Nodes (27): Backups on host devices: the `BackupExecutor` for device-hosted databases…, Installs the device executor factory and copy target (idempotent)., Removes the hooks installed by `register()` (API shutdown)., register(), unregister(), _device_removed(), Gives write access back to main-server copies whose move stopped without doing…, Drops old copies whose keep period ended. Offline devices are retried an hour… (+19 more)

### Community 3 - "deploys.ts"
Cohesion: 0.06
Nodes (77): useApp(), useApps(), useDeployment(), useDeployments(), App, AppDetectDraft, AppPreset, AppTarget (+69 more)

### Community 4 - "DbSession"
Cohesion: 0.07
Nodes (74): AdminOrServiceKey, _audit(), _billing(), check_connection(), _confirm_delete(), connect_database(), connection_databases(), create_connection() (+66 more)

### Community 5 - "types.ts"
Cohesion: 0.02
Nodes (137): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+129 more)

### Community 6 - "services/devices.py"
Cohesion: 0.06
Nodes (86): random_token(), not_found(), approve_enrollment(), _authenticate(), _deny(), deny_enrollment(), device_connect(), download_transfer() (+78 more)

### Community 7 - "FlatButton"
Cohesion: 0.04
Nodes (47): Control, FontStyle, GraphicsPath, IButtonControl, IDeviceContext, PaintEventArgs, PaintEventArgs, Graphics (+39 more)

### Community 8 - "client.ts"
Cohesion: 0.03
Nodes (62): ApiClientOptions, ApiError, buildQuery(), client, codeForStatus(), createApiClient(), DownloadResult, FetchFn (+54 more)

### Community 9 - "firestore_admin.py"
Cohesion: 0.08
Nodes (57): backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids(), create_schedule() (+49 more)

### Community 10 - "data_browser.py"
Cohesion: 0.10
Nodes (57): check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document(), delete_row(), encode_value() (+49 more)

### Community 11 - "metrics.py"
Cohesion: 0.06
Nodes (57): KeyRoutesCORS, CORS for browsers calling the data API with a bearer key. Any origin but no…, active(), alert_out(), deliver(), deliver_async(), evaluate(), _iso() (+49 more)

### Community 12 - "AwsClient"
Cohesion: 0.12
Nodes (8): AwsClient, Deletes every object under `prefix` ("" = the whole bucket). Returns the count., Disables the distribution, waits until CloudFront has rolled that out (up to 30…, This PC's public IPv4 address as AWS sees it (AWS's own checkip service, no…, V-02: the real AwsClient body against botocore's service models (Stubber…, test_ensure_vpc_connector_runs_against_the_real_botocore_models(), The real AwsClient methods against botocore's service models (a wrong parameter…, test_secrets_manager_calls_match_botocore_models()

### Community 13 - "record"
Cohesion: 0.06
Nodes (99): forbidden(), AppReplica, A copy of a co-hosted app running on a co-host device (docs/COHOSTING.md…, _actions_report(), _add_cloud_domain(), add_domain(), AppCreate, AppFields (+91 more)

### Community 14 - "States.tsx"
Cohesion: 0.05
Nodes (121): isApiStarting(), api, qk, hasLiveReplica(), useDataSourcesWithReplicas(), useInstanceSettings(), useProject(), useProjects() (+113 more)

### Community 15 - "services/remote_access.py"
Cohesion: 0.08
Nodes (78): conflict(), ApiError, Maps a Cloudflare failure to the documented Deployer error codes., to_api_error(), tunnel_cname_target(), Stores a value. `None` or "" deletes the override. Caller commits., set_value(), _active_hostnames() (+70 more)

### Community 16 - "eligibility.ts"
Cohesion: 0.07
Nodes (52): usePlacementOptions(), DatabaseLocation, DataSourceKind, Device, DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode (+44 more)

### Community 17 - "auth.py"
Cohesion: 0.08
Nodes (66): sha256_hex(), client_ip(), The peer address. Behind Caddy, main.CaddyProxyHeaders has already set it from…, change_password(), LinkIn, login(), LoginIn, logout() (+58 more)

### Community 18 - "services/cloud.py"
Cohesion: 0.17
Nodes (22): encrypt_json(), _bad(), check_connection(), create_connection(), delete_connection(), get_connection(), list_connections(), normalize_aws() (+14 more)

### Community 19 - "test_devices_local.py"
Cohesion: 0.09
Nodes (26): dispatch(), Returns the normalized origin (`scheme://host[:port]`) or raises 422…, validate_primary_url(), test_device_apps_tunnel_token(), A-050: a call that waited out its timeout for a slot is answered device_busy…, test_agent_skips_calls_whose_deadline_passed_and_keeps_short_calls_free(), fake_primary(), FakePrimary (+18 more)

### Community 20 - "firestore.py"
Cohesion: 0.13
Nodes (45): _and(), _bad(), call(), check_path(), _cursor_in(), _cursor_out(), delete_document(), _doc_id() (+37 more)

### Community 21 - "ControlForm"
Cohesion: 0.06
Nodes (22): ContextMenuStrip, IEnumerable, bool, DateTime, Dictionary, EventHandler, Form, IDictionary (+14 more)

### Community 22 - "services/jobs.py"
Cohesion: 0.06
Nodes (58): cancel_key(), claim(), _clamp(), _error_text(), finish(), handler_for(), HandlerSpec, heartbeat() (+50 more)

### Community 23 - "mcp.py"
Cohesion: 0.09
Nodes (67): _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result(), _limit(), _mongo() (+59 more)

### Community 24 - "WizardForm"
Cohesion: 0.07
Nodes (22): SetupOptions, bool, Color, Control, DateTime, double, EventArgs, EventHandler (+14 more)

### Community 25 - "make_app"
Cohesion: 0.07
Nodes (66): encrypt_secret(), Deployment, env_prefix(), rollback(), rotate_webhook_secret(), make_app(), new_token(), App (+58 more)

### Community 26 - "User"
Cohesion: 0.10
Nodes (45): User, UserIdentity, identity_out(), OAuthApp, begin(), _browser_matches(), CallbackResult, clear_browser_cookie() (+37 more)

### Community 27 - "cloud_deploy.py"
Cohesion: 0.08
Nodes (44): add_domain(), check_domain(), _client_for(), cloud_url(), _connection(), _create_cf_records(), _delete_cf_records(), enqueue_domain_check() (+36 more)

### Community 28 - "BackupsTab.tsx"
Cohesion: 0.04
Nodes (90): saveBlob(), isJobFinished(), useDevices(), useJob(), Backup, BackupCopy, BackupSchedule, BackupTrigger (+82 more)

### Community 29 - "CloudError"
Cohesion: 0.06
Nodes (32): CloudError, Exception, An AWS / Google Cloud call failed (docs/CLOUD.md). `message` is the provider's…, _api_error(), GcpClient, _name(), Any, One Firestore REST call under `projects/<project>/`… (+24 more)

### Community 30 - "github.py"
Cohesion: 0.09
Nodes (46): GitHubConnection, A user's GitHub OAuth token for repository access (docs/DEPLOYMENTS.md "Connect…, _setup(), _api(), apps_using(), _call(), _check_token_status(), delete_file() (+38 more)

### Community 31 - "get_sessionmaker"
Cohesion: 0.13
Nodes (31): _detach(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore(), Local administration commands, run inside the api container. python -m app.cli… (+23 more)

### Community 32 - "test_setup.py"
Cohesion: 0.11
Nodes (10): test_disabling_lists_api_keys_to_rotate_per_project(), test_health_reports_degraded_when_a_required_service_is_down(), test_instance_settings_requires_instance_owner(), test_instance_users(), test_is_initialized_false_without_users(), test_is_initialized_is_the_single_setup_check(), test_oauth_cli(), test_only_owner_creates_projects_by_default() (+2 more)

### Community 33 - "notebook.ts"
Cohesion: 0.13
Nodes (38): QueryRun, SavedQuery, newId(), attachSaved(), CELL_PERSIST_MAX, closeTab(), detachSaved(), EMPTY_NOTEBOOK (+30 more)

### Community 34 - "get_settings"
Cohesion: 0.04
Nodes (98): get_settings(), Process configuration, read from environment variables (see…, Settings, dispose_all(), invalidate(), Test hook: drop every cached engine/client (like the provisioning…, drop_copy(), provision_target() (+90 more)

### Community 35 - "services/backups.py"
Cohesion: 0.03
Nodes (178): BackupCopy, BackupLogSegment, BackupPolicy, new_id(), PathLike, sha256_file(), any_copy(), archive_source_logs() (+170 more)

### Community 36 - "test_data_sources.py"
Cohesion: 0.10
Nodes (8): fake_connect(), fixture, Route tests for data sources, schema, links and the SQL data browser. External…, sqlite_engine(), test_create_external_sql_source(), test_internal_network_is_refused_for_non_owners(), test_managed_connection_hint_says_database_access_is_needed(), test_update_external_source_in_place()

### Community 37 - "routers/backups.py"
Cohesion: 0.07
Nodes (68): Backup, backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup() (+60 more)

### Community 38 - "github_actions.py"
Cohesion: 0.08
Nodes (58): artifact_for(), audience(), builds_on_github(), cancel_setup(), _cel(), check_can_build(), dispatch(), enqueue_removal() (+50 more)

### Community 39 - ".Rebuild"
Cohesion: 0.08
Nodes (19): float, Form, Bitmap, Control, Panel, ThemedForm, Action, bool (+11 more)

### Community 40 - "terminal.ts"
Cohesion: 0.13
Nodes (31): MongoQueryResponse, SqlStatementResult, QueryPrefs, docsToTable(), outputLines(), statementLabel(), asciiTable(), bracketsBalanced() (+23 more)

### Community 41 - "utcnow"
Cohesion: 0.05
Nodes (74): datetime, utcnow(), Any, _record_heartbeat(), _api_rule(), _backup_rules(), _cloud_cleanup_rule(), Condition (+66 more)

### Community 42 - "get_source"
Cohesion: 0.22
Nodes (27): cohosting_eligibility(), create_replica(), delete_replica(), get_conflict(), _key_param(), list_conflicts(), list_replicas(), DataSource (+19 more)

### Community 43 - "dynamo.py"
Cohesion: 0.11
Nodes (60): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), connection_info(), create_backups() (+52 more)

### Community 44 - "conventions.py"
Cohesion: 0.13
Nodes (43): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+35 more)

### Community 45 - "NotebookConsole.tsx"
Cohesion: 0.04
Nodes (88): useCohostEligibility(), useDataSources(), useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSchema(), useSourceSchema() (+80 more)

### Community 46 - "rtdb.py"
Cohesion: 0.06
Nodes (92): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _json_or_text(), list_documents() (+84 more)

### Community 47 - "connections.py"
Cohesion: 0.08
Nodes (55): build_mongo_client(), build_sql_engine(), check_status(), cloud_engine(), _connect_args(), connection_info(), display_for(), _fingerprint() (+47 more)

### Community 48 - "SchemaTab.tsx"
Cohesion: 0.07
Nodes (49): ConventionIssue, ProjectSchema, SourceSchema, CompareSide, edgeTypes, nodeTypes, ReadOnlyErd(), CONVENTION_RULES (+41 more)

### Community 49 - "members.py"
Cohesion: 0.10
Nodes (39): keys_to_rotate(), A-024: the project's live keys this person created or saw the secret of (reveal…, accept_invite(), create_invite(), get_invite(), _get_member(), InviteCreate, list_invites() (+31 more)

### Community 50 - "test_source_sync.py"
Cohesion: 0.10
Nodes (42): One round for one replica. Returns stats, or None when nothing ran (offline,…, One pass over the replicas due for a round, up to ROUND_WORKERS at a time.…, run_due(), sync_round(), _conflicts(), _fake_binlog(), FakeSide, FakeStore (+34 more)

### Community 51 - "useToast"
Cohesion: 0.04
Nodes (104): errorMessage(), invalidateProjectSources(), AppReplica, AppSecrets, DnsRecord, FirestoreBackup, JsonObject, JsonValue (+96 more)

### Community 52 - "DockerCli"
Cohesion: 0.06
Nodes (31): DockerCli, DockerError, _git_env(), parse_size(), _percent(), RuntimeError, The worker's Docker / git interface for app deployments (docs/DEPLOYMENTS.md).…, (sha, first line of the commit message) of HEAD. (+23 more)

### Community 53 - "ddl_export.py"
Cohesion: 0.10
Nodes (42): build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources(), export_sql_source() (+34 more)

### Community 54 - "make_user"
Cohesion: 0.09
Nodes (58): DeviceProjectGrant, make_project(), make_user(), device_source(), fake_device(), make_device(), fixture, env() (+50 more)

### Community 55 - "ProjectAccess"
Cohesion: 0.17
Nodes (25): ProjectAccess, CloudConnection, A user's own AWS or Firebase/Google Cloud credentials (docs/CLOUD.md "Cloud…, AwsCredentials, CloudBackupCreate, CloudDatabaseConnect, CloudDatabaseCreate, CloudRestore (+17 more)

### Community 56 - "OutputWindow"
Cohesion: 0.11
Nodes (12): Color, FormClosedEventArgs, Panel, string, TextBox, LogWindow, OutputWindow, ServiceInfo (+4 more)

### Community 57 - "common.ps1"
Cohesion: 0.09
Nodes (46): Add-DeployerUserPath(), ConvertTo-DeployerArgument(), ConvertTo-DeployerWslPath(), Copy-DeployerFiles(), Disable-DeployerLanAccess(), Enable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes() (+38 more)

### Community 58 - "data_sources.py"
Cohesion: 0.12
Nodes (37): validation_error(), check_data_source(), _config_hosts(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate, delete_data_source() (+29 more)

### Community 59 - "services/transfer.py"
Cohesion: 0.04
Nodes (133): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job(), _owned_projects() (+125 more)

### Community 60 - "CloudflareClient"
Cohesion: 0.06
Nodes (22): CloudflareClient, CloudflareError, _cname_body(), Any, Exception, Thin Cloudflare API v4 client (docs/REMOTE_ACCESS.md). Only the calls Deployer…, A DNS-only record a cloud target asks for (docs/CLOUD.md "Custom domains"):…, Verifies the token and probes each required permission with harmless read… (+14 more)

### Community 61 - "source_sync.py"
Cohesion: 0.05
Nodes (61): check_changes(), _dt(), _dumps_token(), enc(), ensure_mariadb_settings(), ext(), _failed(), latest_versions() (+53 more)

### Community 62 - "crowsfoot.ts"
Cohesion: 0.14
Nodes (19): LinkCardinality, RelationshipCardinality, Cardinality, describeEnds(), edgeEnds, EndMarker, MARKER_LABEL, MARKER_NOTATION (+11 more)

### Community 63 - "factory"
Cohesion: 0.06
Nodes (66): _job_archive(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify(), _create_firestore_steps(), _create_steps() (+58 more)

### Community 64 - "CloudflareSetup.tsx"
Cohesion: 0.06
Nodes (70): CloudflareZone, ProviderName, ProviderSettings, PublicUrlResponse, RemoteAccess, RemoteAccessMode, CopyButton(), CopyField() (+62 more)

### Community 65 - "install.ps1"
Cohesion: 0.11
Nodes (31): Get-InstallerArgumentString(), Get-SystemFacts(), Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Register-ResumeAfterReboot() (+23 more)

### Community 66 - "source_ops.py"
Cohesion: 0.15
Nodes (43): check_status(), connection_info(), create_collection(), create_table(), delete_document(), delete_row(), drop_collection(), drop_table() (+35 more)

### Community 67 - "test_device_rpc.py"
Cohesion: 0.18
Nodes (16): _fresh(), _hello(), Primary-side device RPC: Redis pub/sub routing, the control WebSocket and…, Polls `predicate` (the server handles socket messages on its own threads, so…, test_call_fails_when_connection_replaced(), test_call_offline_device(), test_call_roundtrip_and_errors(), test_call_timeout() (+8 more)

### Community 68 - "test_remote_access.py"
Cohesion: 0.11
Nodes (38): add_host(), assert_no_secrets(), desired(), link(), parametrize, Remote access endpoints (docs/REMOTE_ACCESS.md) with a fake Cloudflare API and…, A-056: an app's hostname is neither listed here, nor usable as the public URL,…, A-184: docs/REMOTE_ACCESS.md's `Domain` type lists exactly the fields the API… (+30 more)

### Community 69 - "IShellLinkW"
Cohesion: 0.14
Nodes (3): IntPtr, StringBuilder, IShellLinkW

### Community 70 - "saved_queries.py"
Cohesion: 0.07
Nodes (54): Append-only history of a saved query's text (docs/QUERY_EDITOR.md "Phase 2 —…, SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query() (+46 more)

### Community 71 - "deployer.ps1"
Cohesion: 0.16
Nodes (37): Assert-Admin(), Get-Context(), Get-OnOffArgument(), Initialize-Engine(), Invoke-Autostart(), Invoke-Compose(), Invoke-KeepAwake(), Invoke-Lan() (+29 more)

### Community 72 - "crypto.py"
Cohesion: 0.20
Nodes (16): _b64d(), _b64e(), decrypt_with_passphrase(), _derive(), encrypt_stream_with_passphrase(), encrypt_with_passphrase(), _passphrase_key(), Any (+8 more)

### Community 73 - "DeviceExecutor"
Cohesion: 0.09
Nodes (16): copy_artifact(), DeviceExecutor, Any, IO, Path, PathLike, Stores bytes (already encrypted) at `ref` in the device's backup store. Returns…, `backups.register_copy_target` hook: copies an encrypted artifact between… (+8 more)

### Community 74 - "test_auth.py"
Cohesion: 0.08
Nodes (24): CaddyProxyHeaders, _is_ip(), X-Forwarded-For / -Proto count only on connections from the `caddy` container…, login(), A-003: the forgotten-password recovery run on the Deployer PC (deployer reset-…, _refresh(), test_change_password(), test_forwarded_headers_count_only_from_caddy() (+16 more)

### Community 75 - "models.py"
Cohesion: 0.04
Nodes (121): Base, Dependency factory for routes with a `project_id` path parameter. Usage:…, require_role(), ApiKey, AuditLog, DataSource, Device, DeviceEnrollment (+113 more)

### Community 76 - "test_apps_api.py"
Cohesion: 0.23
Nodes (15): create(), parametrize, Apps API: CRUD + roles, slug/port allocation, env reveal audit, webhook,…, sign(), test_app_hostnames(), test_create_list_get_and_roles(), test_database_access_is_admin_only(), test_delete_app_when_cloudflare_fails() (+7 more)

### Community 77 - "test_cloud_boundary.py"
Cohesion: 0.24
Nodes (12): _actions(), docs/CLOUD.md "G3": the `deployer-boundary` permissions boundary. The IAM calls…, real_client(), _resources(), role(), test_boundary_document_caps_roles_to_deployer_resources(), test_deployer_user_may_only_write_roles_that_carry_the_boundary(), test_ensure_boundary_creates_once_and_notices_an_outdated_copy() (+4 more)

### Community 78 - "run_queued"
Cohesion: 0.06
Nodes (77): decrypt_json(), `deployer-<slug>-<8 chars of id>`: S3/ECR/App Runner/CloudFront/Cloud Run-safe,…, resource_name(), Test hook: runs queued jobs in creation order in this thread, including jobs…, run_queued(), A-125: every snapshot kind shares _record_snapshot, so a result without a point…, test_platform_snapshot_records_like_a_source_snapshot(), test_pre_drop_safety_snapshot() (+69 more)

### Community 79 - "cloud_db.py"
Cohesion: 0.07
Nodes (65): _cloud_cleanup(), Project, The project's databases and apps with resources Deployer created in a cloud…, client(), config_of(), app_databases(), _backup_status(), _cloud_call() (+57 more)

### Community 80 - "useTerminalConsole.ts"
Cohesion: 0.11
Nodes (38): addHistoryEntry(), HISTORY_LIMIT, HistoryEntry, historyKey(), isEntry(), loadHistory(), DEFAULT_PREFS, draftKey() (+30 more)

### Community 81 - "Usability for non-experts"
Cohesion: 0.20
Nodes (10): Journey 1: Install on an old PC, Journey 2: First run and owner account, Journey 3: Create a project, a table and some rows, Journey 4: Invite a friend, Journey 5: Deploy a website, Journey 6: Put it on the internet or the LAN, Journey 7: Backups and recovery, Journey 8: Day-to-day running (+2 more)

### Community 82 - "get_schema"
Cohesion: 0.15
Nodes (29): create_collection(), create_link(), create_table(), delete_link(), _drop(), drop_collection(), drop_table(), export_schema() (+21 more)

### Community 83 - "device_agent.py"
Cohesion: 0.10
Nodes (23): _connector(), _describe(), DeviceAgent, _load_link(), Any, Event, Exception, Device agent: the host device's outbound connection to the main Deployer… (+15 more)

### Community 84 - "introspection.py"
Cohesion: 0.10
Nodes (41): match_entity(), `user_id` / `userId` -> `user`; nested paths use the last segment. `id` / `_id`…, Returns the entity that a `<singular>_id` (or `<singular>Id`) field refers to,…, reference_base(), analyze_documents(), apply_mongo_indexes(), approximate_row_counts(), bson_type_name() (+33 more)

### Community 85 - "backup_engine.py"
Cohesion: 0.20
Nodes (19): ensure_mongo_replica_set(), _latest_oplog_ts(), mongo_archive_logs(), _mongo_client(), _mongo_collections(), _mongo_replay(), mongo_restore(), mongo_row_counts() (+11 more)

### Community 86 - ".Ask"
Cohesion: 0.11
Nodes (9): FormClosingEventArgs, Dictionary, InstallLocator, bool, Exception, Program, IWin32Window, STAThread (+1 more)

### Community 87 - ".TestMarkers"
Cohesion: 0.06
Nodes (27): bool, double, int, string, StringBuilder, AppInfo, CheckResult, DeployerCli (+19 more)

### Community 88 - "Handover"
Cohesion: 0.15
Nodes (13): Everyday commands, For AI agents, Handover, Known limits (documented, not bugs), Needs the owner, Next steps, The 2026-10-05/06 outage, for reference, The owner's PC (+5 more)

### Community 89 - "App"
Cohesion: 0.10
Nodes (25): App, HostDockerCli, Same commands; the health probe runs inside the container (the test host is not…, test_static_site_end_to_end(), b64(), connect(), docker(), fake_token() (+17 more)

### Community 90 - "get_redis"
Cohesion: 0.06
Nodes (65): get_redis(), drop_copies_on_device(), dump_source(), _forget_lock(), Any, DataSource, Path, Thread (+57 more)

### Community 91 - "tests/test_query_console.py"
Cohesion: 0.11
Nodes (31): _canceller(), Engine, A callable that stops the statement running on `conn` from another thread (None…, Runs a SQL script; see the module docstring and docs/QUERY_CONSOLE.md for the…, run_sql(), mongo_config(), Query console (docs/QUERY_CONSOLE.md): SQL runner on sqlite, mongosh runner…, The API process (PID 1 of its container, same uid as mongosh) must not expose… (+23 more)

### Community 92 - "handle"
Cohesion: 0.24
Nodes (10): Access, handle(), mcp_endpoint(), DbSession, JSONResponse, post, Request, Response (+2 more)

### Community 93 - "device_local.py"
Cohesion: 0.17
Nodes (28): device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to() (+20 more)

### Community 94 - "Backups, Versions & Recovery"
Cohesion: 0.22
Nodes (18): Error envelope and common error codes, Backups, Versions & Recovery, Backups API, Backup data model (jobs, backup_policies, backups, segments, copies), Backup storage and encryption (chunked AES-256-GCM, HKDF), Backups error codes, Jobs (long-running operations), Point-in-time recovery (binlog and oplog replay) (+10 more)

### Community 95 - "deployments.py"
Cohesion: 0.05
Nodes (93): decrypt_secret(), get_docker(), deploy_params(), Deployment, (`apps.deploy` params, repo token or None). The token is sent only with…, Removes passwords from driver error messages (and other text: `limit=None`…, redact(), allocate_port() (+85 more)

### Community 96 - "device_apps.py"
Cohesion: 0.19
Nodes (24): _allocate_port(), _app_id(), _bad(), _caddy_name(), _check_deploy(), _clone_and_build(), _database_env(), fingerprint() (+16 more)

### Community 97 - "LocalExecutor"
Cohesion: 0.06
Nodes (20): backup_root(), BackupExecutor, local_executor(), LocalExecutor, datetime, IO, Path, ProgressFn (+12 more)

### Community 98 - "run"
Cohesion: 0.13
Nodes (28): detect(), _detect_dir(), _dirs(), env_keys(), _find_module(), _join(), Pattern, _python_deps() (+20 more)

### Community 99 - "MessageDialog"
Cohesion: 0.08
Nodes (19): DeployerSetup, Icon, Action, bool, Color, DialogResult, EventArgs, int (+11 more)

### Community 100 - "api_key_config"
Cohesion: 0.23
Nodes (18): api_key_config(), api_key_out(), create_api_key(), generate_secret(), list_api_keys(), _project_key(), Admin, ApiKey (+10 more)

### Community 101 - "test_dynamo.py"
Cohesion: 0.04
Nodes (56): Any, Test hook: `client(config)` returns `factory(config)` (None restores the real…, set_factory(), aws_statements(), Test hook: every statement of every AWS policy (never shown as one policy, IAM…, aws(), fixture, aws() (+48 more)

### Community 102 - "C1 as built"
Cohesion: 0.22
Nodes (9): API, C1 as built, Cloud connections, Custom domains, Dashboard, MCP, Not verified against real clouds, Targets (`apps.target`) (+1 more)

### Community 103 - "._c"
Cohesion: 0.11
Nodes (9): _code(), Exception, Deletes a role Deployer made (its one inline policy first); also the GitHub…, The secret `name` holds `value`: created once, a new version only when the…, By ARN or name; at once (no recovery window), so the name can be used again…, The account's IAM identity provider for GitHub Actions tokens (one per account,…, `{arn, current}` of the account's `deployer-boundary` managed policy…, `{status, host, port}`, None once the instance is gone. (+1 more)

### Community 104 - "mongo_snapshot"
Cohesion: 0.40
Nodes (8): ArtifactWriter, mariadb_archive_logs(), _mariadb_log_bin_enabled(), _mariadb_size_estimate(), mariadb_snapshot(), mongo_snapshot(), _now(), gzip -> encrypt -> `<path>.partial`, renamed into place by `commit()`.

### Community 105 - "shell_runner.py"
Cohesion: 0.12
Nodes (24): _as_uid(), _child_env(), _field(), _kill(), main(), make_server(), mongosh_command(), _ms() (+16 more)

### Community 106 - "shared_fixtures.py"
Cohesion: 0.08
Nodes (31): add_source(), docker(), fake_cf(), FakeProviders, make_source(), project_setup(), providers(), DataSource (+23 more)

### Community 107 - "test_firestore.py"
Cohesion: 0.16
Nodes (20): base(), connect(), docs_url(), _fail(), FakeFirestore, gcp(), fixture, Cloud Firestore engine, phase C2-3 (docs/CLOUD.md): a Firebase project's… (+12 more)

### Community 108 - "_wrap"
Cohesion: 0.07
Nodes (12): A DynamoDB gateway endpoint in the VPC (free, created once, shared): an App…, One DynamoDB API call by its AWS name (`Query`, `PutItem`, `CreateTable`...)…, Names of the account's `deployer-gha-*` roles that carry Deployer's tag (the…, botocore errors -> CloudError with AWS's code and message (no request data, no…, Bucket policy: only this CloudFront distribution (through its OAC) may read…, `{status, records: [{type, name, value}]}` (records appear a few seconds after…, (registry host, username, password) for `docker login --password-stdin`., PENDING | IN_PROGRESS | SUCCEEDED | FAILED | ROLLBACK_IN_PROGRESS |… (+4 more)

### Community 109 - "Any"
Cohesion: 0.17
Nodes (24): check_db_name(), compare_counts(), ensure_database(), _managed_user_for(), _mariadb_clear(), _mariadb_create_db(), mariadb_current_point(), _mariadb_drop_db() (+16 more)

### Community 110 - "cloud_secrets.py"
Cohesion: 0.13
Nodes (24): cleanup(), enabled(), out(), App, App secrets in AWS Secrets Manager / Google Secret Manager (docs/CLOUD.md…, Deletes the secrets the live version no longer references - after the rollout,…, Records what is in the store. `enabled` is re-read from the row first: an admin…, Keeps `stored` (what is in the store now) so switching off still deletes them… (+16 more)

### Community 111 - "auth_headers"
Cohesion: 0.07
Nodes (52): fan_out_schema_change(), `table.create|drop` / `collection.create|drop` done on the main server: repeat…, mark_online(), create_invite(), Project, User, Adds an invite (caller commits). Returns (invite, raw token)., auth_headers() (+44 more)

### Community 112 - "RowDialog.tsx"
Cohesion: 0.08
Nodes (31): isApiError(), DiffChange, Field, FieldDiff, SchemaDiffEntity, AttributeChange, CHANGE_LABELS, CHANGE_ORDER (+23 more)

### Community 113 - "compilerOptions"
Cohesion: 0.07
Nodes (26): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+18 more)

### Community 114 - "deps.py"
Cohesion: 0.13
Nodes (25): api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), load_project_access(), ApiError (+17 more)

### Community 115 - "query_console.py"
Cohesion: 0.12
Nodes (23): _enter_read_only(), _error_text(), _first_keyword(), _is_blank(), _is_timeout(), _leading_keyword(), _ms(), _names_re() (+15 more)

### Community 116 - "test_github_actions.py"
Cohesion: 0.16
Nodes (35): workflow_path(), aws(), by_run(), cloud_app(), committed(), connect_github(), contents_path(), gcp() (+27 more)

### Community 117 - "test_rtdb.py"
Cohesion: 0.19
Nodes (16): base(), connect(), _fail(), FakeRtdb, Firebase Realtime Database engine, phase C2-4 (docs/CLOUD.md): a Firebase…, FakeCloud for the hosting calls, plus an in-memory Realtime Database behind…, test_browse_lazily_query_and_write_by_path(), test_cloud_run_app_gets_its_realtime_database() (+8 more)

### Community 118 - "test_mcp.py"
Cohesion: 0.14
Nodes (6): MCP server for AI agents (docs/MCP.md): JSON-RPC over POST…, The `minimum` (or another argument, e.g. `service_keys`) of the route's…, _route_role(), test_app_tools(), test_every_tool_needs_at_least_its_routes_role(), test_tools_list_depends_on_role()

### Community 119 - "test_oauth.py"
Cohesion: 0.19
Nodes (20): _callback(), _error_of(), _link_state(), parametrize, A callback URL started in another browser (login CSRF / forced linking) is…, _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error() (+12 more)

### Community 120 - "run_query"
Cohesion: 0.33
Nodes (6): BaseModel, post, Request, QueryRequest, run_query(), QueryRunner

### Community 121 - "UninstallForm"
Cohesion: 0.08
Nodes (15): Dictionary, string, Integration, ShellLinkCoClass, bool, FormClosedEventArgs, FormClosingEventArgs, Func (+7 more)

### Community 122 - "FakeCloudflare"
Cohesion: 0.20
Nodes (8): BaseTransport, Test hook: route every client through this transport (None restores the…, set_transport(), fake_cf(), FakeCloudflare, fixture, Minimal stateful stand-in for the parts of the Cloudflare API that Deployer…, MockTransport

### Community 123 - "Domain"
Cohesion: 0.23
Nodes (23): Domain, add_hostname(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, BaseModel (+15 more)

### Community 124 - "_run_tool"
Cohesion: 0.17
Nodes (18): BackupEngineError, _check_exit(), _fetch_binlog(), _mongo_load_archive(), mongo_verify(), _mongorestore(), open_artifact_plain(), IO (+10 more)

### Community 125 - "FakeAdmin"
Cohesion: 0.12
Nodes (16): BaseTransport, Test hook: route the real client's HTTP through this transport., set_transport(), The real GcpClient against a mock transport: paths, bodies, the unchanged-value…, test_secret_manager_rest_shapes(), _ok(), Request, Response (+8 more)

### Community 126 - "backup_crypto.py"
Cohesion: 0.06
Nodes (48): _master_key(), backup_key(), DecryptingReader, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material() (+40 more)

### Community 127 - "FakeDockerCli"
Cohesion: 0.13
Nodes (4): FakeDockerCli, Records the call sequence; `fail_at = <step>` makes that step raise;…, _symlink(), test_build_image_refuses_symlinks_out_of_the_checkout()

### Community 128 - "integration/test_query_console.py"
Cohesion: 0.15
Nodes (22): mariadb(), mongo(), fixture, Query console against real servers (docs/QUERY_CONSOLE.md). - SQL: a throwaway…, A-001: what code that gets past the name filter can see. It runs in the query-…, run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results() (+14 more)

### Community 129 - "dependencies"
Cohesion: 0.09
Nodes (23): @codemirror/autocomplete, @codemirror/lang-javascript, @codemirror/lang-sql, @codemirror/language, @dagrejs/dagre, dependencies, @codemirror/autocomplete, @codemirror/lang-javascript (+15 more)

### Community 130 - "results.ts"
Cohesion: 0.17
Nodes (22): SqlQueryResponse, Node(), CellOutput(), addPrimaryKeyQuery(), base64Size(), CellKind, describeQueryError(), ejsonLeaf() (+14 more)

### Community 131 - "NativeMethods"
Cohesion: 0.16
Nodes (10): DllImport, int, IntPtr, MEMORYSTATUSEX, NativeMethods, RECT, MarshalAs, MEMORYSTATUSEX (+2 more)

### Community 132 - "Path"
Cohesion: 0.18
Nodes (14): _index_path(), _load_index(), mariadb_defaults_file(), mongo_config_file(), mongo_root_uri(), _option_value(), private_tmpdir(), Path (+6 more)

### Community 133 - "set_setting"
Cohesion: 0.11
Nodes (19): set_setting(), test_login_and_signup_share_a_per_ip_limit(), test_providers(), test_signup_when_allowed(), hosted(), fixture, docs/MONITORING.md: `api_key_rate_limit` requests per minute per key; 429 with…, test_per_key_rate_limit() (+11 more)

### Community 134 - "QueryEditor.tsx"
Cohesion: 0.08
Nodes (28): labels, next, ThemeToggle(), initialMode(), subscribe(), ThemeProvider(), COLLECTION_METHODS, CURSOR_METHODS (+20 more)

### Community 135 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+13 more)

### Community 136 - "instance_settings.py"
Cohesion: 0.09
Nodes (50): get_settings_(), list_all_projects(), list_audit(), list_users(), BaseModel, DbSession, get, InstanceOwner (+42 more)

### Community 137 - "devDependencies"
Cohesion: 0.10
Nodes (21): devDependencies, @eslint/js, eslint-plugin-react-hooks, jsdom, @types/node, @types/react, typescript, typescript-eslint (+13 more)

### Community 138 - "ApiError"
Cohesion: 0.09
Nodes (46): ApiError, Raise from handlers/services; rendered as {"error": {code, message, details}}., dismiss_alert(), get_metrics(), get_summary(), list_alerts(), BaseModel, DbSession (+38 more)

### Community 139 - "integrations.py"
Cohesion: 0.18
Nodes (16): github_connect(), github_disconnect(), github_repos(), github_status(), CurrentUser, DbSession, delete, ge (+8 more)

### Community 140 - "diff_schemas"
Cohesion: 0.22
Nodes (18): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), Any, Diff two `SourceSchema` dicts (docs/BACKUPS.md "Version history",… (+10 more)

### Community 141 - "test_firestore_admin.py"
Cohesion: 0.18
Nodes (22): The Google REST calls behind the Firebase hosting targets and databases…, Test hook: `client(config)` returns `factory(config)` (None restores the real…, set_factory(), base(), connected(), gcp(), fixture, Job (+14 more)

### Community 142 - "rate_limit.py"
Cohesion: 0.16
Nodes (17): create_enrollment(), _lookup_rate_limit(), User, check_login(), clear_login(), hit(), login_email_key(), login_key() (+9 more)

### Community 143 - "cloud_aws.py"
Cohesion: 0.13
Nodes (16): free_blocks(), _nat_alive(), nat_name(), _ours(), _public_subnet(), The AWS calls behind the AWS hosting targets (docs/CLOUD.md), one small method…, Deletes the private subnets; the deleted connector's network interfaces hold…, The Name tag of every NAT resource of a VPC, and the private subnets' VPC… (+8 more)

### Community 144 - "CI job: Installer (PowerShell checks, dry run, DeployerSetup.exe)"
Cohesion: 0.40
Nodes (5): PowerShell parse and ASCII-only check, install.ps1 -DryRun progress markers (##deployer:), CI job: Installer (PowerShell checks, dry run, DeployerSetup.exe), DeployerSetup.exe self-test (renders every page), Development

### Community 145 - "database_options"
Cohesion: 0.67
Nodes (3): database_options(), Where a database can live, in plain language, and the sizes / cost of a new AWS…, options()

### Community 146 - "write_both"
Cohesion: 0.10
Nodes (35): _check_value(), cohost_problem(), diff(), _drain(), _eq(), _field(), open_conflict_counts(), pause_device_replicas() (+27 more)

### Community 147 - "DataSource"
Cohesion: 0.19
Nodes (20): collection_entity(), collection_ids(), composite_indexes(), connection_info(), _count(), database_of(), display(), _documents() (+12 more)

### Community 148 - "viewer"
Cohesion: 0.67
Nodes (3): gcp(), fixture, viewer()

### Community 149 - "supervisor.sh"
Cohesion: 0.32
Nodes (15): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), pid_alive(), read_desired(), supervisor.sh script (+7 more)

### Community 150 - "Host Devices"
Cohesion: 0.17
Nodes (22): Data sources endpoints and DataSourceInput, Health and setup endpoints, redis (OAuth state, rate limits, job queue, device RPC), worker (jobs and scheduler), Host Devices, Bulk data transfers endpoints, Device control channel (WebSocket, heartbeat, backoff), Device data model (devices, enrollments, grants) (+14 more)

### Community 151 - "Deployer"
Cohesion: 0.11
Nodes (18): Container runtime choices, Deploy an app, Deployer, Deployer Control, Documentation, Features, First run: the setup wizard, Google and GitHub sign-in (your own OAuth apps) (+10 more)

### Community 152 - "SourceReplica"
Cohesion: 0.09
Nodes (28): A row/document changed on both copies since their last common version (like a…, A version of a row/document the sync applied or confirmed (base for conflict…, SourceReplica, SyncConflict, SyncVersion, BaseModel, ReplicaCreate, ResolveInput (+20 more)

### Community 154 - "README.md"
Cohesion: 0.14
Nodes (14): Connecting, JSON-RPC errors, Limits, MCP server for AI agents, Roles and security, Tools, Checked and found OK, Findings (+6 more)

### Community 155 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.22
Nodes (19): Roadmap (phases 1-7), Deploy pipeline (Vercel functions), deferred, Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Caddy :8081 tunnel-only listener, Remote access data model (settings, domains) (+11 more)

### Community 156 - "SqlStore"
Cohesion: 0.12
Nodes (12): dec(), enc_row(), prune_versions(), Event, _q(), Forgets keys whose copies have agreed for `days` (no newer version, no open…, Background task of the worker: rounds every 2 s while this worker leads the…, Root connection to one database; one short transaction per change (row locked… (+4 more)

### Community 157 - "run_mongosh"
Cohesion: 0.09
Nodes (20): _call_shell(), _clamp(), _connect_uri(), _first_line(), parse_shell_output(), Any, DataSource, Calls `cancel` once when a statement outlives `seconds`, unless it finished… (+12 more)

### Community 158 - "SettingsDialog"
Cohesion: 0.22
Nodes (5): Action, Func, SettingsDialog, Shell, Action

### Community 159 - "C3 as built: GitHub Actions builds (pushes deploy with the PC off)"
Cohesion: 0.18
Nodes (11): API, C3 as built: GitHub Actions builds (pushes deploy with the PC off), Dashboard, MCP, Not verified against real clouds, Permissions added, Reports, Deploy now, runs, Switching back, teardown (+3 more)

### Community 160 - "Deployer HTTP API v1"
Cohesion: 0.17
Nodes (21): Deployer HTTP API v1, Auth endpoints (signup, login, refresh, OAuth), Export and import endpoints, Instance settings and users endpoints, Members and invites endpoints, OAuth callback redirect flow, Projects endpoints, Role hierarchy viewer<developer<admin<owner (+13 more)

### Community 161 - "Query Console"
Cohesion: 0.23
Nodes (16): Data browser (SQL rows, MongoDB documents), Query Console, Query API endpoint, Concurrency, timeout and output limits, Connection invalidated after every run, Dashboard Query tab, CodeMirror editor and toolbar, In-band query errors vs HTTP errors (+8 more)

### Community 163 - "test_backups_engine.py"
Cohesion: 0.12
Nodes (17): binlog_name_with_seq(), binlog_seq(), _mongo_build_oplog(), parse_binlog(), parse_mongodump_counts(), DEFINER -> the target's user; database name -> target. Data (INSERT) lines are…, Event-header scan of a raw binlog file: databases touched and first/last event…, Namespace-renamed copy of an oplog entry without collection UUIDs; None if… (+9 more)

### Community 164 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 166 - "main.py"
Cohesion: 0.05
Nodes (49): SECURITY.md "Query console": loads the Settings, then drops the secrets from…, seal_process(), get_engine(), Engine, install_error_handlers(), FastAPI, create_app(), lifespan() (+41 more)

### Community 167 - "test_query_log.py"
Cohesion: 0.06
Nodes (49): delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), datetime, DbSession, delete, ge (+41 more)

### Community 168 - "Compose service: dashboard (static nginx)"
Cohesion: 0.22
Nodes (10): Dashboard SPA HTML entry (index.html), /src/main.tsx module entrypoint, Pre-paint theme bootstrap (localStorage deployer.theme), Compose service: dashboard (static nginx), docker-compose.dev.yml (development overrides), Dev override: api with uvicorn --reload and bind mounts, Dev override: worker bind mount without reloader, CI workflow (+2 more)

### Community 171 - "_replay_binlogs"
Cohesion: 0.13
Nodes (20): count_insert_rows(), _count_row_tuples(), DumpScanner, _load_dump(), name_rewriter(), ProgressFn, Number of `(...)` row tuples in a fragment of an extended INSERT (strings…, (table, rows) for the first line of an extended INSERT in a mariadb-dump, else… (+12 more)

### Community 172 - "C2-2 as built: DynamoDB"
Cohesion: 0.18
Nodes (11): Add database -> In your AWS account -> NoSQL, API, Apps on App Runner, Backups (Backups tab), Browsing, editing, querying, C2-2 as built: DynamoDB, Data model, MCP (+3 more)

### Community 173 - "API runtime dependencies (requirements.txt)"
Cohesion: 0.21
Nodes (13): API runtime dependencies (requirements.txt), alembic, argon2-cffi (password hashing), cryptography, API dev and test dependencies (requirements-dev.txt), fakeredis, pytest, ruff (+5 more)

### Community 174 - "Query Editor (Supabase-style) & Query Log"
Cohesion: 0.17
Nodes (24): Project API keys (dpl_role_random), Schema endpoints, SchemaLink and ConventionIssue, Platform data model (MariaDB deployer DB), Database Planning Conventions, Conventions panel (advisory warnings), Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle) (+16 more)

### Community 175 - "Deploy a website with Deployer"
Cohesion: 0.15
Nodes (12): Cloud targets (AWS / Firebase through Deployer), Co-host PCs (the same app on other PCs, with failover), Connecting an AI agent (MCP), Deploy a website with Deployer, Do / don't, Feature status (check before promising anything), Hard rule: always ask which platform, People, sign-in and co-hosting (+4 more)

### Community 177 - "By section"
Cohesion: 0.08
Nodes (25): 10. Dashboard data features: databases, data browser, schema, query notebook/terminal, backups, devices, co-hosting, jobs, deploys, 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 3. Query console, query log, saved queries, 4. Backups, PITR, jobs, worker, export/import (+17 more)

### Community 178 - "consoleMode.ts"
Cohesion: 0.31
Nodes (8): DEFAULT_QUERY_CONSOLE_MODE, listeners, loadQueryConsoleMode(), QUERY_CONSOLE_MODE_KEY, QUERY_CONSOLE_MODES, QueryConsoleMode, saveQueryConsoleMode(), subscribe()

### Community 179 - "docker-compose.yml (production stack)"
Cohesion: 0.42
Nodes (12): docker-compose.yml (production stack), Compose service: api, backend network (internal, no internet), Compose service: caddy (reverse proxy, published port), Compose service: mariadb, Memory limits sized for 4 GB PCs, Compose service: mongodb (profile mongodb, replica set rs0), MongoDB behind a compose profile (AVX-dependent) (+4 more)

### Community 180 - "Data API with API keys"
Cohesion: 0.14
Nodes (14): Calling from a browser, Config file, Data API with API keys, Databases in the cloud (AWS / Firebase), Documents (MongoDB sources), DynamoDB tables, Errors, Firestore collections (+6 more)

### Community 181 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.17
Nodes (12): API (`/v1/projects/{pid}`), Co-hosted apps (docs/COHOSTING.md "Websites on both PCs"), Connect a Git repository, Dashboard — project tab **Deploys**, Data model (migration `0006_apps_deployments`), Database access, Deployments (push-to-deploy) — phase 4, Hosting targets (docs/CLOUD.md) (+4 more)

### Community 184 - "wslplatform.tests.ps1"
Cohesion: 0.15
Nodes (3): Initialize-WslPlatform(), Get-WindowsOptionalFeature(), Test-Reboot()

### Community 185 - "C2-3 as built: Cloud Firestore"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project, API, Apps on Cloud Run, Browsing, editing, querying, C2-3 as built: Cloud Firestore, Data model, MCP, Not verified against real clouds (+1 more)

### Community 186 - "test_container_config.py"
Cohesion: 0.23
Nodes (12): A-153: container settings have one source of truth (compose / Caddy), not…, A-001: mongosh (full Node.js for developers and service keys) runs only in the…, A-019: apps (and apps with database access) never share a network with the API,…, A-044: the dashboard imports through /projects/import/jobs; Caddy's 64 MB cap…, L-01: a long migration (0012 rebuilds every DATETIME table) must not run inside…, read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through() (+4 more)

### Community 188 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

### Community 189 - "device_host.py"
Cohesion: 0.08
Nodes (57): _apps_method(), CallContext, capabilities(), collect_metrics(), _cpu_percent(), disk_space(), download_file(), error_payload() (+49 more)

### Community 190 - "C2-1 as built: cloud databases in AWS (RDS / Aurora)"
Cohesion: 0.22
Nodes (9): API, Apps, C2-1 as built: cloud databases in AWS (RDS / Aurora), Data model, MCP, Networking (the trade-off), Not verified against real clouds, Permissions added (now in the `DeployerDatabases` policy, shown in Settings -> Cloud accounts) (+1 more)

### Community 193 - "lan.tests.ps1"
Cohesion: 0.20
Nodes (3): Get-DeployerNonPrivateNetworks(), Write-DeployerNetworkProfileWarning(), Get-NetConnectionProfile()

### Community 194 - "C2-5 as built: MCP, transfer, project delete"
Cohesion: 0.33
Nodes (6): C2-5 as built: MCP, transfer, project delete, Data tools on cloud databases, Deleting a project, MCP: every tool needs at least its REST route's role, Not verified against real clouds, Transfer (export / import)

### Community 195 - "Contributing to Deployer"
Cohesion: 0.32
Nodes (7): Checks (run before opening a PR - CI runs the same), Commits and pull requests, Contributing to Deployer, Development setup, Ground rules, Layout, PowerShell conventions

### Community 197 - "Co-hosting: live two-way database copies and failover websites"
Cohesion: 0.22
Nodes (9): API (`/v1/projects/{pid}`), Co-hosting: live two-way database copies and failover websites, Dashboard (for whoever builds it), Database sync (phase 1 - built), Honest limits (phase 2), Honest limits (shown in the dashboard where they matter), Merge model (conflicts), Roles (+1 more)

### Community 198 - "test_transfer_devices.py"
Cohesion: 0.29
Nodes (12): _export_handler(), fake_provision(), _payload(), fixture, Exports/imports with host devices: device tables, device-hosted data streamed…, test_export_fails_when_device_offline(), test_instance_export_includes_device_tables_and_device_data(), test_instance_import_offline_device_restores_on_main() (+4 more)

### Community 199 - "test_cloud_policies.py"
Cohesion: 0.22
Nodes (8): requirements(), The Deployer AWS permissions as separate managed policies, each comfortably…, _size(), test_every_policy_leaves_room_under_the_iam_limit(), test_split_kept_exactly_the_previous_permissions(), test_google_requirements_include_firestore_backups(), test_google_requirements_include_firestore(), test_google_requirements_include_the_realtime_database()

### Community 201 - "Invoke-Update"
Cohesion: 0.14
Nodes (31): Invoke-Backup(), Invoke-Config(), Invoke-Device(), Invoke-Restore(), Invoke-Update(), Get-BuildSource(), Get-LocalDeploySource(), Resolve-Source() (+23 more)

### Community 203 - "FakeDevice"
Cohesion: 0.20
Nodes (6): FakeDevice, Subscribes to a device's call channel like a socket holder and answers with…, device_process(), fixture, A connected device whose RPCs run `device_host.dispatch` in this process., servers()

### Community 204 - "test_api_docs_routes.py"
Cohesion: 0.52
Nodes (6): _documented(), _norm(), _paths(), Every endpoint the docs name must exist in the router (A-189). Checked: `|…, _routes(), test_documented_endpoints_exist()

### Community 205 - "test_release_workflow.py"
Cohesion: 0.33
Nodes (6): _permissions(), A-149: the release workflow is read-only by default; only the jobs that publish…, Every `permissions:` block at this indent, as {scope: level}., A-190: a tag that fails CI publishes nothing, and an RC never becomes `latest`., test_images_wait_for_ci_and_prereleases_skip_latest(), test_release_workflow_permissions_are_per_job()

### Community 206 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 207 - "Monitoring and alerts"
Cohesion: 0.29
Nodes (7): Alerts, API, API key rate limit, Monitoring and alerts, Not covered (yet), Webhook, What is collected

### Community 208 - "sql_read_only_refusal"
Cohesion: 0.27
Nodes (10): mongo_read_only_refusal(), Why a viewer may not run this script, naming the word that tripped the check…, Why a viewer may not run this code, naming the matched write name (None =…, sql_read_only_refusal(), parametrize, test_mongo_read_only_accepts(), test_mongo_read_only_refuses(), test_read_only_refusals_name_the_word() (+2 more)

### Community 209 - "Release job: build and push GHCR images (api, dashboard, tunnel)"
Cohesion: 0.47
Nodes (6): Release workflow (v* tags), Release job: deploy bundle and GitHub release, deployer-deploy.zip release asset, Release job: build and push GHCR images (api, dashboard, tunnel), Optional Windows code signing (signtool), Release job: DeployerSetup.exe build, self-test, sign, checksum

### Community 210 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (6): Register-DeployerTask(), Test-DeployerDockerDesktopCrashedSince(), Test-DeployerWslDistroDiskMissing(), Get-ChildItem(), Get-ItemProperty(), Register-ScheduledTask()

### Community 211 - "_clean_up_slot"
Cohesion: 0.22
Nodes (10): _clean_up_slot(), The live (non-zombie) processes whose real, effective, saved or fs uid is the…, Kills every process of the slot uid (a script may have left one running to…, _slot_pids(), _fake_proc(), V-01: the slot's processes are found in /proc (no shell is started to kill…, V-01, in the API image as root (the CI unit suite): a process of a slot uid is…, test_clean_up_slot_kills_a_real_process() (+2 more)

### Community 213 - "0010_cohost_apps.py"
Cohesion: 0.60
Nodes (3): _columns(), _create_app_replicas(), upgrade()

### Community 214 - "test_dead_code.py"
Cohesion: 0.47
Nodes (5): A-191: every top-level constant, function and class in app/ is referenced in…, test_a_name_used_only_by_tests_is_dead(), test_no_unreferenced_top_level_names(), _top_level_names(), Module

### Community 215 - "test_fixture_layout.py"
Cohesion: 0.50
Nodes (4): _is_fixture(), A-192: shared fixtures live in conftest.py or its plugin modules, never…, test_no_fixture_is_imported_from_a_test_module(), FunctionDef

### Community 216 - "test_migration_table_options.py"
Cohesion: 0.25
Nodes (6): head_db_url(), fixture, Migration checks: every migration table gets the utf8mb4 options, and head…, A scratch database upgraded to head: SQLite always, and a throwaway database on…, `create_all` builds the test schema, so a model change without a migration…, test_migrations_match_the_models()

### Community 217 - "test_query_docs.py"
Cohesion: 0.50
Nodes (3): The query docs describe the shipped Terminal/Notebook modes, not superseded…, _read(), test_query_docs_describe_modes_without_plans()

### Community 218 - "test_skill_doc.py"
Cohesion: 0.60
Nodes (4): The deploy-website skill must not contradict itself about where apps can run…, _section(), test_co_host_apps_are_not_listed_as_not_built(), test_external_platform_table_lists_only_external_platforms()

### Community 220 - "test_version.py"
Cohesion: 0.50
Nodes (3): A-188: release images report their git tag as the version, not the hardcoded…, _reload_version(), test_version_comes_from_the_release_tag()

### Community 221 - "package.json"
Cohesion: 0.40
Nodes (4): name, private, type, version

### Community 223 - "setup-engine.sh"
Cohesion: 0.60
Nodes (4): DEBIAN_FRONTEND, enable_unit(), log(), setup-engine.sh script

### Community 226 - "0012_datetime_microseconds.py"
Cohesion: 0.83
Nodes (3): downgrade(), _set_fsp(), upgrade()

### Community 262 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.20
Nodes (10): AWS policy split as built: purpose-sized managed policies, C2 - cloud databases (what is left), Cloud hosting and databases (AWS, Firebase), Code, API, dashboard, Deleting a cloud database over the API and MCP (as built), Not verified against real clouds, Not verified against real clouds, Principles (+2 more)

### Community 264 - "role_name"
Cohesion: 0.17
Nodes (13): _aws_identity(), aws_policy(), provider_id(), `deployer-gha-<slug>-<id8>` (IAM role names are <= 64 characters)., The role's name from the app's slug and id alone (a teardown knows it after the…, `gh-<id8>`: the app's workload identity provider in the shared pool., What one app's workflow may do: update exactly that app's resources., (label, call) removing what the setup made; the shared OIDC provider / pool… (+5 more)

### Community 271 - ".delete_nat_gateway"
Cohesion: 0.25
Nodes (5): (`pending` | `available` | `failed` | `deleting` | `deleted`, AWS's failure…, Deletes the VPC's NAT gateway, waits until AWS has removed it (bounded) and…, Removes the private route table (its subnet associations first)., An EC2 delete for which already gone is fine (two teardowns of the same VPC,…, _unless_gone()

### Community 274 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.25
Nodes (8): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, New databases, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

### Community 275 - ".ensure_github_role"
Cohesion: 0.33
Nodes (3): The App Runner instance role `name` (created once, within the boundary) the…, The role one app's workflow assumes (within the boundary): `trust` (its…, Puts the boundary on an existing role that lacks it (made before the boundary…

### Community 276 - "C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway)"
Cohesion: 0.29
Nodes (7): API, MCP, dashboard, C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway), Not verified against real clouds, Permissions added (`DeployerDatabases` and `DeployerHosting`, shown in Settings -> Cloud accounts), Shared, reference-counted, removed with the last user, What it is, What the deploy makes (`cloud_deploy.Publish.nat_connector`, `cloud_aws.ensure_nat_network`)

### Community 277 - "Invoke-Preflight"
Cohesion: 0.48
Nodes (5): Invoke-Preflight(), Get-DeployerAppPortUsers(), Test-DeployerAppPort(), Get-NetTCPConnection(), Get-Process()

### Community 280 - "check"
Cohesion: 0.33
Nodes (6): check(), database_problem(), describe(), list_databases(), `connections.try_source` for Firestore: the database answers and is in native…, The Firestore databases of the connection's project, with why Deployer can't…

### Community 281 - "Firestore point-in-time recovery and deletes (as built)"
Cohesion: 0.33
Nodes (6): API, Deletes (Backups tab; typed name), Firestore point-in-time recovery and deletes (as built), MCP, Not verified against real clouds, Point-in-time recovery (Backups tab -> Point-in-time recovery)

### Community 282 - "G1 as built: app secrets in a secret store, environment changes without a rollback"
Cohesion: 0.33
Nodes (6): API, dashboard, MCP, Environment changes reach App Runner / Cloud Run apps at once, G1 as built: app secrets in a secret store, environment changes without a rollback, Not verified against real clouds, Permissions added, Secrets in AWS Secrets Manager / Google Secret Manager (opt-in)

### Community 284 - "G3 as built: a permissions boundary for the roles Deployer creates"
Cohesion: 0.40
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

## Knowledge Gaps
- **520 isolated node(s):** `docker-entrypoint.sh script`, `deployer-api`, `name`, `private`, `version` (+515 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ControlForm` connect `ControlForm` to `FlatButton`, `.Rebuild`, `shell_runner.py`, `.Ask`, `.TestMarkers`, `OutputWindow`?**
  _High betweenness centrality (0.288) - this node is a cross-community bridge._
- **Why does `ApiError` connect `ApiError` to `Publish`, `integration/test_query_console.py`, `device_executor.py`, `DbSession`, `services/devices.py`, `instance_settings.py`, `firestore_admin.py`, `data_browser.py`, `record`, `rate_limit.py`, `services/remote_access.py`, `auth.py`, `services/cloud.py`, `write_both`, `test_devices_local.py`, `firestore.py`, `services/jobs.py`, `mcp.py`, `SourceReplica`, `make_app`, `User`, `cloud_deploy.py`, `SqlStore`, `CloudError`, `github.py`, `get_sessionmaker`, `run_mongosh`, `get_settings`, `services/backups.py`, `routers/backups.py`, `github_actions.py`, `main.py`, `test_query_log.py`, `utcnow`, `get_source`, `_replay_binlogs`, `dynamo.py`, `rtdb.py`, `connections.py`, `members.py`, `test_source_sync.py`, `make_user`, `ProjectAccess`, `data_sources.py`, `services/transfer.py`, `CloudflareClient`, `device_host.py`, `source_sync.py`, `factory`, `source_ops.py`, `test_device_rpc.py`, `saved_queries.py`, `test_transfer_devices.py`, `DeviceExecutor`, `test_auth.py`, `models.py`, `FakeDevice`, `cloud_db.py`, `get_schema`, `device_agent.py`, `backup_engine.py`, `App`, `get_redis`, `tests/test_query_console.py`, `device_local.py`, `deployments.py`, `.__init__`, `device_apps.py`, `mongo_snapshot`, `Any`, `auth_headers`, `deps.py`, `query_console.py`, `run_query`, `_run_tool`?**
  _High betweenness centrality (0.181) - this node is a cross-community bridge._
- **Why does `parseError()` connect `client.ts` to `ControlForm`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 120 inferred relationships involving `ApiError` (e.g. with `ProjectAccess` and `AppCreate`) actually correct?**
  _`ApiError` has 120 INFERRED edges - model-reasoned connections that need verification._
- **What connects `docker-entrypoint.sh script`, `deployer-api`, `name` to the rest of the system?**
  _520 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Publish` be split into smaller, more focused modules?**
  _Cohesion score 0.10252100840336134 - nodes in this community are weakly interconnected._
- **Should `cn` be split into smaller, more focused modules?**
  _Cohesion score 0.03954248366013072 - nodes in this community are weakly interconnected._