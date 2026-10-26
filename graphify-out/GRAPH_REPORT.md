# Graph Report - deployer  (2026-10-26)

## Corpus Check
- 513 files · ~632,435 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9443 nodes · 33620 edges · 229 communities (208 shown, 21 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3259 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `40628e43`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- client.ts
- Button
- types.ts
- source_sync.py
- auth.py
- Badge
- device_host.py
- apps.py
- FlatButton
- Device
- react
- services/backups.py
- get_connection
- rtdb.py
- DevicesPage.tsx
- docs/PLATFORMS.md - Platforms and accounts this project uses
- SchemaTab.tsx
- CloudflareSetup.tsx
- ApiError
- deploys.ts
- GcpClient
- mcp.py
- record
- metrics.py
- ControlForm
- routers/cloud.py
- cloud_deploy.py
- get_settings
- cn
- firestore.py
- Job
- CloudflareClient
- errors.py
- deployer.sh
- run_queued
- WizardForm
- ThemedForm
- services/__init__.py
- json.ts
- App
- deployer_cli.py
- terminal.ts
- utcnow
- test_source_sync.py
- MCP.md
- README.md
- re
- routers/backups.py
- test_backups_pitr.py
- post
- useTerminalConsole.ts
- models.py
- Color
- executors.py
- docs/ARCHITECTURE.md - Deployer Architecture
- services/transfer.py
- BackupLogSegment
- Deployer HTTP API v1
- IShellLinkW
- test_backup_crypto.py
- NotebookConsole.tsx
- deployments.py
- cloud_db.py
- check_ref
- common.ps1
- connection
- toast-context.ts
- docker-compose.yml
- environment
- data.py
- results.ts
- DockerCli
- sqlalchemy
- DataSource
- test_firestore_admin.py
- device_apps.py
- services
- test_devices_management.py
- QueryEditor.tsx
- Deployments (push-to-deploy) — phase 4
- query_console.py
- test_query_log.py
- test_remote_access.py
- tests/test_query_console.py
- AuditLog
- deployer.ps1
- UninstallForm
- caddy
- options
- install.ps1
- DeviceAgent
- Path
- Usability for non-experts
- DumpScanner
- connections.py
- migrate
- shell_runner.py
- .TestMarkers
- with
- schema.py
- DecryptingReader
- device_local.py
- conventions.py
- DeviceExecutor
- saved_queries.py
- client.test.ts
- test_github_actions.py
- query-shell
- .Ask
- RtdbView.tsx
- test_repo_detect.py
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- AwsClient
- mongo_snapshot
- .set_aliases
- CallContext
- rtdb_read
- with
- compilerOptions
- FakeDevice
- test_rtdb.py
- get_source
- ScriptRunner
- How the main code paths work
- test_backups_engine.py
- test_cli_client.py
- FakeDockerCli
- integration/test_query_console.py
- package.json
- Get-DeployerSource
- mongodb
- compilerOptions
- tunnel
- decrypt_json
- worker
- ThemeProvider.tsx
- CloudError
- schema_diff.py
- Remote Access & Custom Domains (Cloudflare)
- MarkerKind
- test_transfer_stream.py
- Core.cs
- supervisor.sh
- read_mongo_changes
- tempfile
- images
- CheckRow
- test_apps_api.py
- oauth.py
- _call_tool
- test_mysql_canceller_kills_the_query_from_a_private_pool
- FakeSide
- apiSnippets.ts
- HANDOVER.md
- SourceReplica
- backup_engine.py
- readOnly.ts
- Data API with API keys
- cancel_job
- LocalExecutor
- services
- test_container_config.py
- query/diff.ts
- Cloud hosting and databases (AWS, Firebase)
- wslplatform.tests.ps1
- volumes
- steps
- bundle
- C2-3 as built: Cloud Firestore
- Deploy a website with Deployer
- images
- SetupOptions
- test_managed_db_connection_cap.py
- api
- lan.tests.ps1
- jobs
- SyncConflict
- healthcheck
- redis
- steps
- WizardPage
- apply_changes
- test_cohost_apps.py
- test_api_docs_routes.py
- DeviceSide
- cli
- Monitoring and alerts
- mariadb
- mongodb-upgrade-6
- SqlStore
- mongodb-upgrade-8
- test_dead_code.py
- C2-2 as built: DynamoDB
- Invoke-Preflight
- test_sweep_leftovers_removes_stale_partials_and_temp_databases
- x-mongodb-upgrade
- test_query_docs.py
- test_skill_doc.py
- test_version.py
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_ensure_vpc_connector_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- services/cli_tokens.py
- tsconfig.json
- Invoke-DeployerNative
- runtime.tests.ps1
- docker-entrypoint.sh
- entrypoint.sh
- upgrade.sh
- ci.yml
- release.yml
- deployer-api
- handle
- C2-4 as built: Firebase Realtime Database
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
- install_error_handlers
- Settings
- main

## God Nodes (most connected - your core abstractions)
1. `ApiError` - 523 edges
2. `DataSource` - 378 edges
3. `Button` - 219 edges
4. `App` - 217 edges
5. `utcnow()` - 193 edges
6. `cn()` - 156 edges
7. `useToast()` - 154 edges
8. `Alert()` - 150 edges
9. `errorMessage()` - 148 edges
10. `Job` - 147 edges

## Surprising Connections (you probably didn't know these)
- `Cloud connections` --references--> `encrypt_json()`  [INFERRED]
  docs/CLOUD.md → api/app/crypto.py
- `Data model` --references--> `encrypt_json()`  [INFERRED]
  docs/CLOUD.md → api/app/crypto.py
- `Co-hosted apps (docs/COHOSTING.md "Websites on both PCs")` --references--> `deploy()`  [INFERRED]
  docs/DEPLOYMENTS.md → api/app/routers/apps.py
- `How it works` --references--> `logout()`  [INFERRED]
  docs/CLI.md → api/app/routers/auth.py
- `MCP` --references--> `firestore_import()`  [INFERRED]
  docs/CLOUD.md → api/app/routers/cloud.py

## Import Cycles
- 3-file cycle: `api/app/services/deployments.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 3-file cycle: `api/app/services/device_host.py -> api/app/services/transfer.py -> api/app/services/devices.py -> api/app/services/device_host.py`
- 4-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 4-file cycle: `api/app/services/deployments.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py`
- 4-file cycle: `api/app/services/cohosting.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py`
- 4-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/device_moves.py -> api/app/services/backups.py`
- 4-file cycle: `api/app/services/cohost_apps.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/cloud_db.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py -> api/app/services/cloud_db.py`
- 5-file cycle: `api/app/services/cloud_deploy.py -> api/app/services/github_actions.py -> api/app/services/jobs.py -> api/app/services/transfer.py -> api/app/services/deployments.py -> api/app/services/cloud_deploy.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`
- 5-file cycle: `api/app/services/cli_tokens.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cli_tokens.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/device_apps.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/cohost_apps.py -> api/app/services/devices.py -> api/app/services/device_host.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/cohost_apps.py`
- 5-file cycle: `api/app/services/backups.py -> api/app/services/source_ops.py -> api/app/services/cohosting.py -> api/app/services/source_sync.py -> api/app/worker.py -> api/app/services/backups.py`

## Hyperedges (group relationships)
- **MCP billable tools gated by confirm_billing** — docs_mcp_confirm_billing_pattern, docs_mcp_tool_set_app_target, docs_mcp_tool_create_cloud_database, docs_mcp_tool_set_build_location, docs_mcp_tool_set_app_secrets_store, docs_mcp_tool_set_app_internet_access [EXTRACTED 1.00]
- **Secrets encrypted at rest with MASTER_KEY** — docs_platforms_master_key, docs_platforms_table_instance_settings, docs_platforms_table_github_connections, docs_platforms_table_apps, docs_platforms_table_cloud_connections, docs_platforms_table_data_sources [EXTRACTED 1.00]
- **Backup protection layers for a managed database** — docs_backups_snapshots, docs_backups_pitr, docs_backups_safety_snapshots, docs_backups_recently_deleted, docs_backups_platform_backup, docs_backups_verification [EXTRACTED 1.00]
- **Device runtime protocol (control channel, RPC routing, methods, transfers)** — docs_devices_control_channel, docs_devices_rpc_routing, docs_devices_rpc_methods, docs_devices_bulk_transfers [EXTRACTED 1.00]
- **Cloudflare tunnel stack (link, sidecar, supervisor, handshake files, Caddy 8081)** — docs_remote_access_link_step, docs_remote_access_tunnel_sidecar, docs_remote_access_supervisor, docs_remote_access_desired_status_files, docs_remote_access_caddy_8081 [INFERRED 0.85]

## Communities (229 total, 21 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.08
Nodes (15): SettingsDialog, Autostart, KeepAwake, Lan, Port, InputBox, Invalid, Rule (+7 more)

### Community 1 - "client.ts"
Cohesion: 0.07
Nodes (40): ApiClientOptions, client, DownloadResult, FetchFn, isApiStarting(), QueryValue, RequestOptions, SessionListener (+32 more)

### Community 2 - "Button"
Cohesion: 0.05
Nodes (184): refresh(), errorMessage(), invalidateProjectSources(), useProjects(), useProviders(), useSetupStatus(), CloudDatabaseOptions, DatabaseLocation (+176 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (170): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+162 more)

### Community 4 - "source_sync.py"
Cohesion: 0.05
Nodes (29): cohost_problem(), pause_device_replicas(), ext(), _failed(), _merge_warnings(), _mongo_change(), MongoStore, _named() (+21 more)

### Community 5 - "auth.py"
Cohesion: 0.03
Nodes (70): _find_user(), main(), _oauth_set(), _oauth_write(), _platform_list(), _platform_restore(), _read_json_stdin(), _reset_password() (+62 more)

### Community 6 - "Badge"
Cohesion: 0.06
Nodes (96): useDevices(), useInstanceSettings(), useSyncConflict(), useSyncConflicts(), useSyncHistory(), ConflictField, ReplicaStatus, SyncSide (+88 more)

### Community 7 - "device_host.py"
Cohesion: 0.08
Nodes (41): _apps_method(), clear_link(), collect_metrics(), _cpu_percent(), database_size(), device_mode(), disk_space(), download_file() (+33 more)

### Community 8 - "apps.py"
Cohesion: 0.04
Nodes (81): conflict(), _actions_report(), add_domain(), AppCreate, AppFields, AppUpdate, _audit_cohost(), _audit_database_access() (+73 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (27): CheckOption, CheckColor, Checked, Description, ChoiceCard, Badge, BadgeColor, Checked (+19 more)

### Community 10 - "Device"
Cohesion: 0.04
Nodes (94): not_found(), Device, DeviceEnrollment, DeviceProjectGrant, role_rank(), create_replica(), approve_enrollment(), _authenticate() (+86 more)

### Community 11 - "react"
Cohesion: 0.04
Nodes (147): isDeviceOffline(), api, qk, hasLiveReplica(), isJobFinished(), useCohostEligibility(), useDataSourcesWithReplicas(), useJob() (+139 more)

### Community 12 - "services/backups.py"
Cohesion: 0.05
Nodes (61): BackupCopy, any_copy(), _artifact_host(), backup_out(), backups_out(), _columns(), copies_by_artifact(), _copy_destination() (+53 more)

### Community 13 - "get_connection"
Cohesion: 0.08
Nodes (20): github_disconnect(), github_repos(), github_status(), _api(), apps_using(), _call(), _check_token_status(), delete_hook() (+12 more)

### Community 14 - "rtdb.py"
Cohesion: 0.07
Nodes (40): analyze_documents(), visit(), apply_mongo_indexes(), bson_type_name(), _compile_type(), introspect_mongo(), introspect_mongo_collection(), mongo_indexes() (+32 more)

### Community 15 - "DevicesPage.tsx"
Cohesion: 0.08
Nodes (39): DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability, ManagedEngine, ApprovalForm(), ApproveDevicePage() (+31 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.23
Nodes (18): docs/PLATFORMS.md - Platforms and accounts this project uses, Cloudflare tunnel and DNS, Cloudflare API token (four permissions), Connect GitHub (push-to-deploy) and webhooks, Docker Engine inside the deployer WSL distro (default runtime), Sign in with GitHub (OAuth app), Google Cloud sign-in client (Sign in with Google), MASTER_KEY (AES-256-GCM key in .env) (+10 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.05
Nodes (84): saveBlob(), useSchema(), ConventionIssue, LinkCardinality, RelationshipCardinality, SourceSchema, EmptyState(), BackupsTab() (+76 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.06
Nodes (70): isApiError(), CloudflareZone, Domain, ProviderName, ProviderSettings, PublicUrlRequest, PublicUrlResponse, RemoteAccess (+62 more)

### Community 19 - "ApiError"
Cohesion: 0.05
Nodes (77): ApiError, bad(), check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document() (+69 more)

### Community 20 - "deploys.ts"
Cohesion: 0.06
Nodes (83): useApp(), useApps(), useDataSources(), useDeployment(), useDeployments(), App, AppDetectDraft, AppPatch (+75 more)

### Community 21 - "GcpClient"
Cohesion: 0.06
Nodes (8): _api_error(), GcpClient, _name(), _secret_id(), handle(), test_real_google_client_binding_and_provider_requests(), handle(), test_real_google_client_lists_providers_members_and_the_live_version()

### Community 22 - "mcp.py"
Cohesion: 0.10
Nodes (54): _confirmed(), Ctx, _limit(), _mongo(), _p(), _sql(), t_app_logs(), t_cloud_database_options() (+46 more)

### Community 23 - "record"
Cohesion: 0.04
Nodes (90): _oauth_status(), get_settings_(), list_all_projects(), list_audit(), list_users(), settings_out(), SettingsUpdate, update_settings() (+82 more)

### Community 24 - "metrics.py"
Cohesion: 0.05
Nodes (52): get_metrics(), get_summary(), list_alerts(), active(), _api_rule(), _cloud_cleanup_rule(), Condition, conditions() (+44 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (19): ControlForm, IsBusy, State, RunState, Busy, Checking, NotResponding, Running (+11 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.06
Nodes (58): _audit(), AwsCredentials, _billing(), check_connection(), CloudBackupCreate, CloudDatabaseConnect, CloudDatabaseCreate, CloudRestore (+50 more)

### Community 27 - "cloud_deploy.py"
Cohesion: 0.04
Nodes (38): Domain, _add_cloud_domain(), add_domain(), cache_control(), check_domain(), _client_for(), cloud_env(), content_type() (+30 more)

### Community 28 - "get_settings"
Cohesion: 0.07
Nodes (43): get_settings(), _check_mongodb(), _mongo_client(), ensure_database(), dispose_all(), m_provision(), drop_copy(), provision_target() (+35 more)

### Community 29 - "cn"
Cohesion: 0.09
Nodes (44): QueryTab, AlertBadge(), AppLayout(), AuthShell(), navClass(), noop(), render(), Where() (+36 more)

### Community 30 - "firestore.py"
Cohesion: 0.08
Nodes (41): _and(), _bad(), call(), check_path(), collection_entity(), collection_ids(), _count(), _cursor_in() (+33 more)

### Community 31 - "Job"
Cohesion: 0.08
Nodes (30): Job, ensure_mongo_replica_set(), claim(), _error_text(), run_job(), acquire_leadership(), _guard(), _load_plugins() (+22 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.05
Nodes (20): CloudflareClient, CloudflareError, _cname_body(), set_transport(), _err(), fake_cf(), FakeCloudflare, _ok() (+12 more)

### Community 33 - "errors.py"
Cohesion: 0.02
Nodes (89): get_db(), get_sessionmaker(), get_redis(), identity_out(), iso(), replicas_out(), _load_link(), read_status() (+81 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "run_queued"
Cohesion: 0.04
Nodes (87): Deployment, set_docker(), instance_role_name(), resource_name(), site_id(), set_enabled(), state_of(), apps_dir() (+79 more)

### Community 36 - "WizardForm"
Cohesion: 0.11
Nodes (12): Card, BorderColor, Fill, Radius, TextBlock, RightAlign, SingleLine, TextColor (+4 more)

### Community 37 - "ThemedForm"
Cohesion: 0.13
Nodes (4): AppIcon, ThemedForm, IsForcedScale, ResetPasswordDialog

### Community 38 - "services/__init__.py"
Cohesion: 0.04
Nodes (39): seal_process(), api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), ProjectAccess (+31 more)

### Community 39 - "json.ts"
Cohesion: 0.08
Nodes (48): alert_out(), mute(), aws_for(), backup_name(), _backup_out(), _bad(), call(), check() (+40 more)

### Community 40 - "App"
Cohesion: 0.04
Nodes (70): App, cloud_url(), enqueue_teardown(), apps_tunnel_token(), copy_problem(), deploy_params(), device_env(), _main_secrets() (+62 more)

### Community 41 - "deployer_cli.py"
Cohesion: 0.11
Nodes (35): all_apps(), Api, api_from_config(), app_path(), _app_status(), _apply_hint(), ask_secret(), CliError (+27 more)

### Community 42 - "terminal.ts"
Cohesion: 0.11
Nodes (43): MongoQueryResponse, SqlStatementResult, BOM, Cell, csvField(), exportCsv(), exportFilename(), exportJson() (+35 more)

### Community 43 - "utcnow"
Cohesion: 0.05
Nodes (54): Backup, BackupPolicy, utcnow(), _backup_rules(), expire_project_backups(), prune_all(), settle(), snapshot_ref() (+46 more)

### Community 44 - "test_source_sync.py"
Cohesion: 0.11
Nodes (24): sync_round(), _conflicts(), _fake_binlog(), gtid(), __init__(), _read_all(), _replica(), _seed() (+16 more)

### Community 45 - "MCP.md"
Cohesion: 0.09
Nodes (55): Notes for AI agents (skill copy, MCP, graphify), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits, Per-project MCP server (POST /v1/projects/<id>/mcp) (+47 more)

### Community 46 - "README.md"
Cohesion: 0.05
Nodes (65): Commands, Google sign-in for your apps, How it works, Sign in, The `deployer` command line (no browser, no sudo), Linux support work: install.sh, deployer.sh, linux-installer CI, Linux server platform (alternative to Windows PC), docs/SETUP.md - Setting up Deployer (+57 more)

### Community 47 - "re"
Cohesion: 0.05
Nodes (43): backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids(), create_schedule() (+35 more)

### Community 48 - "routers/backups.py"
Cohesion: 0.09
Nodes (33): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+25 more)

### Community 49 - "test_backups_pitr.py"
Cohesion: 0.09
Nodes (37): validation_error(), sha256_file(), archive_source_logs(), _bucket_keys(), consistent_at(), _discard_new_source(), logs_prefix(), ordered_segments() (+29 more)

### Community 50 - "post"
Cohesion: 0.08
Nodes (27): dismiss_alert(), cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job() (+19 more)

### Community 51 - "useTerminalConsole.ts"
Cohesion: 0.11
Nodes (37): addHistoryEntry(), HISTORY_LIMIT, HistoryEntry, historyKey(), isEntry(), loadHistory(), DEFAULT_PREFS, draftKey() (+29 more)

### Community 52 - "models.py"
Cohesion: 0.03
Nodes (100): Base, get_engine(), load_project_access(), ApiKey, InstanceSetting, Project, ProjectInvite, ProjectMember (+92 more)

### Community 53 - "Color"
Cohesion: 0.07
Nodes (25): Logo, Glyphs, IconBadge, Color, Kind, Soft, IconKind, Check (+17 more)

### Community 54 - "executors.py"
Cohesion: 0.05
Nodes (12): progress(), perform_snapshot(), register_copy_target(), _schema_snapshot(), unregister(), BackupExecutor, DeviceExecutorUnavailable, executor_for() (+4 more)

### Community 55 - "docs/ARCHITECTURE.md - Deployer Architecture"
Cohesion: 0.11
Nodes (20): Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Ground rules, Layout, PowerShell conventions (+12 more)

### Community 56 - "services/transfer.py"
Cohesion: 0.04
Nodes (63): _b64d(), _b64e(), decrypt_secret(), decrypt_with_passphrase(), _derive(), encrypt_secret(), encrypt_stream_with_passphrase(), encrypt_with_passphrase() (+55 more)

### Community 57 - "BackupLogSegment"
Cohesion: 0.11
Nodes (25): BackupLogSegment, new_id(), contiguous(), _covers(), covers_anchor(), _follows(), _gap_marker(), gfs_keep() (+17 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.09
Nodes (44): Deployer HTTP API v1, Auth endpoints (signup, login, refresh, OAuth), Data sources endpoints and DataSourceInput, Error envelope and common error codes, Export and import endpoints, Health and setup endpoints, Instance settings and users endpoints, Members and invites endpoints (+36 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.09
Nodes (5): IShellLinkW, ShellLinkCoClass, MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "test_backup_crypto.py"
Cohesion: 0.07
Nodes (31): body(), backup_key(), BackupCryptoError, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material() (+23 more)

### Community 61 - "NotebookConsole.tsx"
Cohesion: 0.12
Nodes (45): useSourceSchema(), SavedQuery, newId(), attachSaved(), CELL_PERSIST_MAX, closeTab(), detachSaved(), EMPTY_NOTEBOOK (+37 more)

### Community 62 - "deployments.py"
Cohesion: 0.04
Nodes (73): get_docker(), _job_archive(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify(), _backup_status() (+65 more)

### Community 63 - "cloud_db.py"
Cohesion: 0.04
Nodes (64): encrypt_json(), CloudConnection, _cloud_cleanup(), client(), _bad(), check_connection(), config_of(), create_connection() (+56 more)

### Community 64 - "check_ref"
Cohesion: 0.16
Nodes (5): run_device_job(), run_executor_call(), _TempArtifact, m_jobs_run(), check_ref()

### Community 65 - "common.ps1"
Cohesion: 0.07
Nodes (45): Invoke-Update(), Get-SystemFacts(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerArgument(), ConvertTo-DeployerRuntimePath(), ConvertTo-DeployerStateTable() (+37 more)

### Community 66 - "connection"
Cohesion: 0.05
Nodes (68): aws_statements(), connection(), aws(), base(), create(), KwFake, with_kwargs(), _project_with_cloud_things() (+60 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.03
Nodes (58): useProject(), Role, ToastApi, ToastContext, ToastItem, ToastTone, icons, { api } (+50 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.07
Nodes (51): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: Windows installer checks and DeployerSetup.exe, CI job: API image + integration tests (MariaDB, MongoDB, Docker), CI job: Linux installer (install, CLI, update, uninstall) (+43 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.16
Nodes (20): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), list_subcollections(), _mongo_source() (+12 more)

### Community 71 - "results.ts"
Cohesion: 0.16
Nodes (22): SqlQueryResponse, CellOutput(), CellResult, response, addPrimaryKeyQuery(), base64Size(), CellKind, describeQueryError() (+14 more)

### Community 72 - "DockerCli"
Cohesion: 0.06
Nodes (23): DockerCli, on(), _kill(), _watch(), DockerError, _git_env(), parse_size(), _percent() (+15 more)

### Community 73 - "sqlalchemy"
Cohesion: 0.04
Nodes (44): build_bundle(), _now_text(), render_sql_script(), topo_sort_tables(), approximate_row_counts(), build_sql_entities(), introspect_sql(), raw_sql_tables() (+36 more)

### Community 74 - "DataSource"
Cohesion: 0.06
Nodes (55): DataSource, create_collection(), create_table(), cloud_engine(), get_mongo_db(), get_sql_engine(), _comment_safe(), _commented() (+47 more)

### Community 75 - "test_firestore_admin.py"
Cohesion: 0.07
Nodes (42): requirements(), base(), connected(), FakeAdmin, gcp(), run_job(), test_backup_schedules_backups_and_restore(), test_create_a_named_firestore_database() (+34 more)

### Community 76 - "device_apps.py"
Cohesion: 0.18
Nodes (18): _allocate_port(), _app_id(), _bad(), _caddy_name(), _check_deploy(), _clone_and_build(), _database_env(), fingerprint() (+10 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "test_devices_management.py"
Cohesion: 0.08
Nodes (28): device_source(), add_source(), docker(), fake_cf(), fake_mongosh(), FakeProviders, make_source(), project_setup() (+20 more)

### Community 79 - "QueryEditor.tsx"
Cohesion: 0.13
Nodes (20): DataSourceKind, COLLECTION_METHODS, ConsoleAction, CURSOR_METHODS, cursorLine(), DB_METHODS, editorKeys, EditorMode (+12 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.12
Nodes (23): provider(), static(), target(), local(), API, C1 as built, Cloud connections, Custom domains (+15 more)

### Community 81 - "query_console.py"
Cohesion: 0.06
Nodes (30): redact(), _call_shell(), _clamp(), _connect_uri(), _enter_read_only(), _error_text(), _first_keyword(), _first_line() (+22 more)

### Community 82 - "test_query_log.py"
Cohesion: 0.05
Nodes (33): QueryRun, delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), QueryRequest, run_query(), delete_before() (+25 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.08
Nodes (37): fix_state_ownership(), add_host(), assert_no_secrets(), desired(), link(), test_add_hostname_dns_failure_rolls_back_ingress(), test_add_hostname_existing_record(), test_add_hostname_new() (+29 more)

### Community 84 - "tests/test_query_console.py"
Cohesion: 0.07
Nodes (35): mongo_read_only_refusal(), run_sql(), _timeout_statement(), mongo_config(), _fake_proc(), run_fake(), test_mongo_read_only_accepts(), test_mongo_read_only_refuses() (+27 more)

### Community 85 - "AuditLog"
Cohesion: 0.05
Nodes (38): CaddyProxyHeaders, _is_ip(), AuditLog, prune(), create_access_token(), test_prune(), _refresh(), test_change_password() (+30 more)

### Community 86 - "deployer.ps1"
Cohesion: 0.15
Nodes (44): Assert-Admin(), Get-Context(), Get-OnOffArgument(), Initialize-Engine(), Invoke-Autostart(), Invoke-Backup(), Invoke-Compose(), Invoke-Config() (+36 more)

### Community 87 - "UninstallForm"
Cohesion: 0.08
Nodes (10): ProcessResult, ScriptOutput, Integration, StartMenuDir, Phase, Confirm, Done, Failed (+2 more)

### Community 88 - "caddy"
Cohesion: 0.10
Nodes (22): internal, internal, command, depends_on, entrypoint, image, mem_limit, networks (+14 more)

### Community 89 - "options"
Cohesion: 0.16
Nodes (21): logging, logging, logging, driver, options, logging, logging, logging (+13 more)

### Community 90 - "install.ps1"
Cohesion: 0.13
Nodes (33): Get-InstallerArgumentString(), Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Register-ResumeAfterReboot(), Request-Reboot() (+25 more)

### Community 91 - "DeviceAgent"
Cohesion: 0.07
Nodes (16): _detach(), _connector(), process_redirect(), _describe(), DeviceAgent, run_agent(), _send(), write_status() (+8 more)

### Community 92 - "Path"
Cohesion: 0.16
Nodes (16): BackupEngineError, compare_counts(), _fetch_binlog(), _index_path(), _load_index(), mariadb_archive_logs(), mariadb_defaults_file(), mongo_config_file() (+8 more)

### Community 93 - "Usability for non-experts"
Cohesion: 0.09
Nodes (21): Checklist, Critical, Deployer audit - 2026-09-28, Executive summary, High, Journey 1: Install on an old PC, Journey 2: First run and owner account, Journey 3: Create a project, a table and some rows (+13 more)

### Community 94 - "DumpScanner"
Cohesion: 0.17
Nodes (9): count_insert_rows(), _count_row_tuples(), DumpScanner, test_count_insert_rows_ignores_parens_inside_strings(), test_dump_scanner_collects_point_and_counts(), _scan(), test_count_insert_rows_first_line_only(), test_multi_line_extended_insert_as_written_by_mariadb_11() (+1 more)

### Community 95 - "connections.py"
Cohesion: 0.04
Nodes (61): check_data_source(), _config_hosts(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate, delete_data_source(), _ensure_name_free() (+53 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "shell_runner.py"
Cohesion: 0.07
Nodes (19): _as_uid(), _child_env(), _clean_up_slot(), _field(), _kill(), main(), make_server(), do_POST() (+11 more)

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (7): CheckResult, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "schema.py"
Cohesion: 0.08
Nodes (27): api_key_config(), api_key_out(), ApiKeyCreate, create_api_key(), generate_secret(), list_api_keys(), _project_key(), reveal_api_key() (+19 more)

### Community 101 - "DecryptingReader"
Cohesion: 0.13
Nodes (7): DecryptingReader, feed(), rewrite_dump_line(), _encrypted(), test_decrypting_reader_is_a_context_manager(), test_open_artifact_plain_uncompressed_closes_file_on_exit(), test_rewrite_dump_line()

### Community 102 - "device_local.py"
Cohesion: 0.13
Nodes (19): device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to() (+11 more)

### Community 103 - "conventions.py"
Cohesion: 0.10
Nodes (45): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+37 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.16
Nodes (21): SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query() (+13 more)

### Community 106 - "client.test.ts"
Cohesion: 0.16
Nodes (14): ApiError, buildQuery(), codeForStatus(), createApiClient(), download(), emit(), request(), send() (+6 more)

### Community 107 - "test_github_actions.py"
Cohesion: 0.08
Nodes (42): set_factory(), set_factory(), role_name(), workflow_path(), aws(), aws(), FakeCloud, gcp() (+34 more)

### Community 108 - "query-shell"
Cohesion: 0.11
Nodes (18): cap_add, cap_drop, command, cpus, entrypoint, extra_hosts, image, init (+10 more)

### Community 109 - ".Ask"
Cohesion: 0.07
Nodes (21): AppInfo, DefaultInstallDir, ExePath, PowerShellExe, Ref, Repo, RepoUrl, TroubleshootingUrl (+13 more)

### Community 110 - "RtdbView.tsx"
Cohesion: 0.27
Nodes (14): JsonValue, childPath(), cleanRtdbPath(), isBranch(), isRtdbKey(), parentPath(), preview(), Actions (+6 more)

### Community 111 - "test_repo_detect.py"
Cohesion: 0.12
Nodes (21): detect(), _detect_dir(), has(), src(), _dirs(), env_keys(), _find_module(), _join() (+13 more)

### Community 112 - "FakeDynamo"
Cohesion: 0.09
Nodes (5): aws(), FakeDynamo, _missing(), PitrFake, viewer()

### Community 113 - "Query Console"
Cohesion: 0.10
Nodes (35): Project API keys (dpl_role_random), Data browser (SQL rows, MongoDB documents), Schema endpoints, SchemaLink and ConventionIssue, Platform data model (UUID-keyed MariaDB tables), Database Planning Conventions, Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle) (+27 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (3): Register-DeployerTask(), ConvertTo-DeployerWslPath(), Register-ScheduledTask()

### Community 115 - "AwsClient"
Cohesion: 0.05
Nodes (10): AwsClient, _code(), nat_name(), _unless_gone(), _wrap(), test_nat_network_runs_against_the_real_botocore_models(), test_secrets_manager_calls_match_botocore_models(), Not verified against real clouds (+2 more)

### Community 116 - "mongo_snapshot"
Cohesion: 0.15
Nodes (12): ArtifactWriter, _latest_oplog_ts(), mariadb_snapshot(), mongo_archive_logs(), mongo_snapshot(), _oldest_oplog_ts(), _oplog_available(), feed() (+4 more)

### Community 118 - "CallContext"
Cohesion: 0.06
Nodes (33): CallContext, dispatch(), validate_primary_url(), bad(), device_process(), download(), upload(), deploy_params() (+25 more)

### Community 119 - "rtdb_read"
Cohesion: 0.22
Nodes (4): _json_or_text(), list_documents(), list_rows(), rtdb_read()

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "FakeDevice"
Cohesion: 0.15
Nodes (4): CallListener, fake_device(), factory(), FakeDevice

### Community 123 - "test_rtdb.py"
Cohesion: 0.11
Nodes (19): base(), connect(), _fail(), FakeRtdb, by(), gcp(), test_browse_lazily_query_and_write_by_path(), test_cloud_run_app_gets_its_realtime_database() (+11 more)

### Community 124 - "get_source"
Cohesion: 0.12
Nodes (25): SyncVersion, cohosting_eligibility(), delete_replica(), get_conflict(), _key_param(), list_conflicts(), list_replicas(), _replica() (+17 more)

### Community 125 - "ScriptRunner"
Cohesion: 0.09
Nodes (8): LogWindow, ToolbarHeight, OutputWindow, ToolbarHeight, Payload, ScriptRunner, Cancelled, IsRunning

### Community 126 - "How the main code paths work"
Cohesion: 0.40
Nodes (5): 7. Deploying to the cloud, 8. Installing, updating and staying up, `deployer update`, How the main code paths work, The sign-in task and keep-alive

### Community 127 - "test_backups_engine.py"
Cohesion: 0.13
Nodes (11): binlog_name_with_seq(), binlog_seq(), _mongo_build_oplog(), parse_binlog(), parse_mongodump_counts(), rename_oplog_entry(), _event(), test_binlog_names() (+3 more)

### Community 128 - "test_cli_client.py"
Cohesion: 0.21
Nodes (6): _login(), approve_once(), test_app_lookup(), test_env_commands_never_print_secrets(), test_google_oauth_saves_both_values_on_each_app(), test_login_saves_a_private_token_and_whoami_uses_it()

### Community 129 - "FakeDockerCli"
Cohesion: 0.11
Nodes (4): FakeDockerCli, docker(), env(), TokenDocker

### Community 130 - "integration/test_query_console.py"
Cohesion: 0.16
Nodes (19): mariadb(), mongo(), run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results(), test_mariadb_multi_statement_script(), test_mariadb_read_only_session(), test_mariadb_session_state_does_not_leak() (+11 more)

### Community 131 - "package.json"
Cohesion: 0.04
Nodes (62): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+54 more)

### Community 132 - "Get-DeployerSource"
Cohesion: 0.12
Nodes (12): Get-BuildSource(), Get-LocalDeploySource(), Remove-InstallerTempFiles(), Resolve-Source(), Copy-DeployerFiles(), Get-DeployerSource(), Invoke-DeployerRobocopy(), Resolve-DeployerRef() (+4 more)

### Community 133 - "mongodb"
Cohesion: 0.15
Nodes (13): MONGO_INITDB_ROOT_PASSWORD, MONGO_INITDB_ROOT_USERNAME, command, entrypoint, environment, image, mem_limit, networks (+5 more)

### Community 134 - "compilerOptions"
Cohesion: 0.11
Nodes (17): compilerOptions, allowImportingTsExtensions, lib, module, moduleDetection, moduleResolution, noEmit, noFallthroughCasesInSwitch (+9 more)

### Community 135 - "tunnel"
Cohesion: 0.15
Nodes (13): TUNNEL_TRANSPORT_PROTOCOL, tunnel, cap_drop, depends_on, environment, image, mem_limit, networks (+5 more)

### Community 136 - "decrypt_json"
Cohesion: 0.04
Nodes (36): decrypt_json(), ejson(), index_key_and_options(), mongo_collection_specs(), mysql_table_order(), show_create_table(), skipped_objects(), sql_create_statements() (+28 more)

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "ThemeProvider.tsx"
Cohesion: 0.26
Nodes (9): labels, next, initialMode(), subscribe(), ThemeProvider(), THEME_STORAGE_KEY, ThemeContext, ThemeContextValue (+1 more)

### Community 139 - "CloudError"
Cohesion: 0.09
Nodes (14): CloudError, free_blocks(), _nat_alive(), _ours(), _public_subnet(), inner(), run(), test_nat_helpers() (+6 more)

### Community 140 - "schema_diff.py"
Cohesion: 0.22
Nodes (13): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), entity(), field() (+5 more)

### Community 141 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.25
Nodes (17): Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes, Link step (find or create tunnel, fetch connector token) (+9 more)

### Community 142 - "MarkerKind"
Cohesion: 0.17
Nodes (11): Marker, MarkerKind, Check, Done, Error, None, Other, RebootRequired (+3 more)

### Community 143 - "test_transfer_stream.py"
Cohesion: 0.09
Nodes (13): _JsonReader, read_data_entry(), restore_file(), _stream_parts(), _dump(), fake_engine(), FakeConn, materialize() (+5 more)

### Community 144 - "Core.cs"
Cohesion: 0.15
Nodes (4): DeployerSetup, DeployerCli, Internet, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 146 - "read_mongo_changes"
Cohesion: 0.06
Nodes (20): m_sync_mongo_apply(), m_sync_mongo_changes(), m_sync_position(), m_sync_sql_apply(), m_sync_sql_changes(), _sync_database(), _sync_limit(), _sync_offset() (+12 more)

### Community 147 - "tempfile"
Cohesion: 0.14
Nodes (13): _check_exit(), _load_dump(), _mongo_load_archive(), _mongorestore(), name_rewriter(), open_artifact_plain(), _replay_binlogs(), _run_mariadb_client() (+5 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "CheckRow"
Cohesion: 0.17
Nodes (12): CheckRow, Detail, SingleLine, State, TextLeft, Title, CheckStatus, Fail (+4 more)

### Community 150 - "test_apps_api.py"
Cohesion: 0.06
Nodes (30): create(), env(), sign(), test_app_hostnames(), test_create_list_get_and_roles(), test_database_access_is_admin_only(), test_delete_app_when_cloudflare_fails(), test_deploy_cancel_rollback_and_delete() (+22 more)

### Community 151 - "oauth.py"
Cohesion: 0.06
Nodes (39): GitHubConnection, github_connect(), save_connection(), OAuthApp, begin(), _browser_matches(), CallbackResult, clear_browser_cookie() (+31 more)

### Community 152 - "_call_tool"
Cohesion: 0.25
Nodes (7): _call_tool(), _check_args(), _dispatch(), _error_result(), RpcError, _text_result(), _visible()

### Community 154 - "FakeSide"
Cohesion: 0.10
Nodes (6): WriteRejected, FakeSide, FakeStore, test_reapplying_a_batch_is_a_no_op(), test_rounds_of_different_copies_run_side_by_side(), changes()

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.10
Nodes (30): Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09), For AI agents, Full codebase audit (198 findings, all ticked) (+22 more)

### Community 157 - "SourceReplica"
Cohesion: 0.08
Nodes (34): SourceReplica, fan_out_schema_change(), mark_online(), make_device(), replica(), build(), _sql(), test_mariadb_two_way_sync() (+26 more)

### Community 158 - "backup_engine.py"
Cohesion: 0.15
Nodes (29): check_db_name(), _managed_user_for(), _mariadb_clear(), _mariadb_create_db(), mariadb_current_point(), _mariadb_drop_db(), _mariadb_exec(), _mariadb_log_bin_enabled() (+21 more)

### Community 159 - "readOnly.ts"
Cohesion: 0.35
Nodes (9): checkMongoReadOnly(), checkReadOnly(), checkSqlReadOnly(), firstKeyword(), MONGO_WRITE_NAMES, MONGO_WRITE_RE, ReadOnlyCheck, splitSqlStatements() (+1 more)

### Community 160 - "Data API with API keys"
Cohesion: 0.20
Nodes (10): order(), rows(), Calling from a browser, Config file, Data API with API keys, Queries, Rotating a key, Rows (SQL sources) (+2 more)

### Community 161 - "cancel_job"
Cohesion: 0.23
Nodes (4): cancel_job(), get_job(), _get_job(), list_jobs()

### Community 162 - "LocalExecutor"
Cohesion: 0.13
Nodes (3): node_for(), backup_root(), LocalExecutor

### Community 163 - "services"
Cohesion: 0.18
Nodes (10): command, volumes, volumes, volumes, services, api, migrate, query-shell (+2 more)

### Community 164 - "test_container_config.py"
Cohesion: 0.24
Nodes (7): read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through(), test_migrations_run_to_completion_before_the_api_starts(), test_query_shell_sidecar_holds_no_secrets(), test_security_headers_are_set_by_caddy_not_nginx(), test_untrusted_containers_share_no_network_with_the_api()

### Community 165 - "query/diff.ts"
Cohesion: 0.43
Nodes (6): DIFF_MAX_LINES, DiffLine, diffStats(), lineDiff(), lines(), render()

### Community 166 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.06
Nodes (30): AppSecrets, API, API, dashboard, MCP, AWS policy split as built: purpose-sized managed policies, C2-5 as built: MCP, transfer, project delete, C2 - cloud databases (what is left), Cloud hosting and databases (AWS, Firebase), Code, API, dashboard (+22 more)

### Community 167 - "wslplatform.tests.ps1"
Cohesion: 0.15
Nodes (3): Initialize-WslPlatform(), Get-WindowsOptionalFeature(), Test-Reboot()

### Community 168 - "volumes"
Cohesion: 0.18
Nodes (11): volumes, backups, caddy_apps, caddy_config, caddy_data, mariadb_conf, mariadb_data, mongodb_config (+3 more)

### Community 169 - "steps"
Cohesion: 0.36
Nodes (11): steps, steps, steps, steps, steps, steps, if, name (+3 more)

### Community 170 - "bundle"
Cohesion: 0.20
Nodes (11): name, needs, permissions, runs-on, jobs, bundle, tests, contents (+3 more)

### Community 171 - "C2-3 as built: Cloud Firestore"
Cohesion: 0.11
Nodes (21): chunks(), bad(), key(), cursor(), device_apply(), Add database -> In your Firebase project, API, Apps on Cloud Run (+13 more)

### Community 172 - "Deploy a website with Deployer"
Cohesion: 0.17
Nodes (12): Cloud targets (AWS / Firebase through Deployer), Co-host PCs (the same app on other PCs, with failover), Connecting an AI agent (MCP), Deploy a website with Deployer, Do / don't, Feature status (check before promising anything), Hard rule: always ask which platform, People, sign-in and co-hosting (+4 more)

### Community 173 - "images"
Cohesion: 0.18
Nodes (11): name, needs, permissions, runs-on, strategy, component, context, images (+3 more)

### Community 174 - "SetupOptions"
Cohesion: 0.18
Nodes (8): SetupOptions, Autostart, DesktopShortcut, EnableLan, InstallDir, KeepAwake, Port, Runtime

### Community 175 - "test_managed_db_connection_cap.py"
Cohesion: 0.29
Nodes (4): FakeConn, _patch_engine(), test_existing_managed_users_are_capped_and_others_left_alone(), test_new_managed_user_is_created_with_the_cap()

### Community 176 - "api"
Cohesion: 0.20
Nodes (10): defaults, name, runs-on, defaults, name, runs-on, run, api (+2 more)

### Community 177 - "lan.tests.ps1"
Cohesion: 0.18
Nodes (5): Add-DeployerFirewallRule(), Enable-DeployerLanAccess(), Get-DeployerNonPrivateNetworks(), Write-DeployerNetworkProfileWarning(), Get-NetConnectionProfile()

### Community 178 - "jobs"
Cohesion: 0.20
Nodes (10): name, runs-on, name, runs-on, name, runs-on, jobs, compose (+2 more)

### Community 179 - "SyncConflict"
Cohesion: 0.08
Nodes (22): SyncConflict, _check_value(), diff(), _drain(), _eq(), _field(), resolve(), _undo_primary() (+14 more)

### Community 180 - "healthcheck"
Cohesion: 0.53
Nodes (9): healthcheck, interval, retries, start_period, test, timeout, healthcheck, healthcheck (+1 more)

### Community 181 - "redis"
Cohesion: 0.22
Nodes (9): REDISCLI_AUTH, command, environment, image, mem_limit, networks, restart, volumes (+1 more)

### Community 182 - "steps"
Cohesion: 0.33
Nodes (9): steps, steps, steps, id, if, name, run, shell (+1 more)

### Community 183 - "WizardPage"
Cohesion: 0.22
Nodes (9): WizardPage, Checks, Docker, Error, Finish, Install, Options, Reboot (+1 more)

### Community 184 - "apply_changes"
Cohesion: 0.11
Nodes (16): apply_changes(), _project(), same(), Store, 10. Dashboard data features: databases, data browser, schema, query notebook/terminal, backups, devices, co-hosting, jobs, deploys, 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough (+8 more)

### Community 185 - "test_cohost_apps.py"
Cohesion: 0.11
Nodes (22): AppReplica, push_tunnel(), replicate(), sweep(), sweep_device(), new_token(), deploy(), handler_for() (+14 more)

### Community 186 - "test_api_docs_routes.py"
Cohesion: 0.43
Nodes (5): _documented(), _norm(), _paths(), _routes(), test_documented_endpoints_exist()

### Community 187 - "DeviceSide"
Cohesion: 0.32
Nodes (3): DeviceSide, full(), test_device_side_speaks_rpc_and_drops_unexpected_fields()

### Community 189 - "Monitoring and alerts"
Cohesion: 0.29
Nodes (7): text(), Alerts, API, API key rate limit, Monitoring and alerts, Not covered (yet), Webhook

### Community 190 - "mariadb"
Cohesion: 0.29
Nodes (7): command, image, mem_limit, networks, restart, volumes, mariadb

### Community 191 - "mongodb-upgrade-6"
Cohesion: 0.29
Nodes (7): entrypoint, image, mem_limit, network_mode, profiles, volumes, mongodb-upgrade-6

### Community 192 - "SqlStore"
Cohesion: 0.18
Nodes (7): dec(), enc(), enc_row(), _q(), SchemaMismatch, SqlStore, test_value_encoding_round_trips_and_hashes_stably()

### Community 193 - "mongodb-upgrade-8"
Cohesion: 0.29
Nodes (7): entrypoint, image, mem_limit, network_mode, profiles, volumes, mongodb-upgrade-8

### Community 194 - "test_dead_code.py"
Cohesion: 0.29
Nodes (5): test_a_name_used_only_by_tests_is_dead(), test_no_unreferenced_top_level_names(), _top_level_names(), _is_fixture(), test_no_fixture_is_imported_from_a_test_module()

### Community 195 - "C2-2 as built: DynamoDB"
Cohesion: 0.17
Nodes (10): engine(), Add database -> In your AWS account -> NoSQL, API, Apps on App Runner, Backups (Backups tab), C2-2 as built: DynamoDB, Data model, Not verified against real clouds (+2 more)

### Community 196 - "Invoke-Preflight"
Cohesion: 0.57
Nodes (5): Invoke-Preflight(), Get-DeployerAppPortUsers(), Test-DeployerAppPort(), Get-NetTCPConnection(), Get-Process()

### Community 198 - "x-mongodb-upgrade"
Cohesion: 0.33
Nodes (6): x-mongodb-upgrade, entrypoint, mem_limit, network_mode, profiles, volumes

### Community 200 - "test_skill_doc.py"
Cohesion: 0.60
Nodes (3): _section(), test_co_host_apps_are_not_listed_as_not_built(), test_external_platform_table_lists_only_external_platforms()

### Community 202 - "linux-installer"
Cohesion: 0.33
Nodes (6): NO_COLOR, linux-installer, env, name, runs-on, timeout-minutes

### Community 203 - "setup-exe"
Cohesion: 0.40
Nodes (5): HAS_SIGNING_CERT, setup-exe, env, name, runs-on

### Community 204 - "setup-engine.sh"
Cohesion: 0.47
Nodes (4): DEBIAN_FRONTEND, enable_unit(), log(), setup-engine.sh script

### Community 205 - "test_argon2_runs_at_most_two_at_once"
Cohesion: 0.83
Nodes (4): test_argon2_runs_at_most_two_at_once(), hash(), _track(), verify()

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 218 - "services/cli_tokens.py"
Cohesion: 0.05
Nodes (56): random_token(), sha256_hex(), CliLogin, CliToken, approve_login(), create_login(), deny_login(), list_tokens() (+48 more)

### Community 224 - "Invoke-DeployerNative"
Cohesion: 0.16
Nodes (15): Disable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes(), Get-DeployerLanAddresses(), Get-DeployerLanPorts(), Get-DeployerLanUrls(), Get-DeployerWslIp(), Invoke-DeployerNative() (+7 more)

### Community 247 - "ci.yml"
Cohesion: 0.17
Nodes (11): concurrency, cancel-in-progress, group, name, permissions, contents, branches, True (+3 more)

### Community 248 - "release.yml"
Cohesion: 0.33
Nodes (5): name, permissions, tags, True, push

### Community 251 - "handle"
Cohesion: 0.24
Nodes (3): handle(), mcp_endpoint(), _rpc_error()

### Community 253 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.20
Nodes (10): _key(), Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP (+2 more)

### Community 255 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.17
Nodes (8): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, New databases, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

### Community 259 - "install_error_handlers"
Cohesion: 0.27
Nodes (6): _body(), install_error_handlers(), _api_error(), _http(), _unhandled(), _validation()

## Knowledge Gaps
- **145 isolated node(s):** `deployer-api`, `RFC-5987`, `RFC-4180`, `Checking`, `Running` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2501 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `integration/test_query_console.py`, `install_error_handlers`, `source_sync.py`, `auth.py`, `device_host.py`, `apps.py`, `decrypt_json`, `Device`, `CloudError`, `services/backups.py`, `get_connection`, `rtdb.py`, `read_mongo_changes`, `mcp.py`, `record`, `_call_tool`, `oauth.py`, `routers/cloud.py`, `cloud_deploy.py`, `get_settings`, `SourceReplica`, `backup_engine.py`, `firestore.py`, `Job`, `errors.py`, `services/__init__.py`, `json.ts`, `App`, `C2-3 as built: Cloud Firestore`, `utcnow`, `test_source_sync.py`, `re`, `routers/backups.py`, `test_backups_pitr.py`, `post`, `SyncConflict`, `models.py`, `executors.py`, `services/transfer.py`, `test_cohost_apps.py`, `DeviceSide`, `deployments.py`, `cloud_db.py`, `check_ref`, `SqlStore`, `data.py`, `DataSource`, `device_apps.py`, `test_devices_management.py`, `query_console.py`, `test_query_log.py`, `tests/test_query_console.py`, `AuditLog`, `services/cli_tokens.py`, `DeviceAgent`, `connections.py`, `schema.py`, `device_local.py`, `saved_queries.py`, `CallContext`, `FakeDevice`, `get_source`?**
  _High betweenness centrality (0.128) - this node is a cross-community bridge._
- **Are the 146 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 146 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.07814207650273224 - nodes in this community are weakly interconnected._
- **Why does `docs/ARCHITECTURE.md - Deployer Architecture` connect `docs/ARCHITECTURE.md - Deployer Architecture` to `docker-compose.yml`, `Remote Access & Custom Domains (Cloudflare)`, `README.md`, `docs/PLATFORMS.md - Platforms and accounts this project uses`, `Query Console`, `Deployer HTTP API v1`, `HANDOVER.md`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `client.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.07256894049346879 - nodes in this community are weakly interconnected._