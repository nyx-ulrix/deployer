# Graph Report - deployer  (2026-10-27)

## Corpus Check
- 523 files · ~652,578 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9709 nodes · 34598 edges · 248 communities (224 shown, 24 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3383 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `203f1ebe`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- react
- Button
- types.ts
- apps.py
- oauth.py
- Badge
- ApiError
- App
- FlatButton
- Device
- RestoreDialog.tsx
- sqlalchemy
- github.py
- rtdb.py
- DevicesPage.tsx
- docs/PLATFORMS.md - Platforms and accounts this project uses
- SchemaTab.tsx
- CloudflareSetup.tsx
- data_browser.py
- deploys.ts
- GcpClient
- mcp.py
- services/remote_access.py
- test_monitoring.py
- ControlForm
- routers/cloud.py
- Publish
- provisioning.py
- conftest.py
- firestore.py
- Color
- CloudflareClient
- shell_runner.py
- deployer.sh
- test_cohost_apps.py
- WizardForm
- ThemedForm
- api_key_config
- dynamo.py
- _reconcile_app
- deployer_cli.py
- NotebookConsole.tsx
- firestore_admin.py
- test_dynamo.py
- MCP.md
- README.md
- test_rds_tls.py
- record
- services/backups.py
- json.ts
- introspection.py
- source_sync.py
- .RenderChildren
- BackupExecutor
- connection
- services/transfer.py
- get_redis
- Deployer HTTP API v1
- NativeMethods
- test_github_actions.py
- services/cli_inputs.py
- deployments.py
- AuditLog
- test_cli_inputs.py
- common.ps1
- make_app
- toast-context.ts
- docker-compose.yml
- environment
- data.py
- projects.py
- DockerCli
- InputRequestPage.tsx
- api_from_config
- test_firestore.py
- metrics.py
- services
- call
- AuditLog
- Deployments (push-to-deploy) — phase 4
- tests/test_query_console.py
- CliError
- test_remote_access.py
- routers/remote_access.py
- test_oauth.py
- deployer.ps1
- UninstallForm
- caddy
- options
- Install-WslEngine
- get_sessionmaker
- QueryEditor.tsx
- crowsfoot.ts
- DumpScanner
- dependencies
- migrate
- DecryptingReader
- .TestMarkers
- with
- create_app
- test_backup_crypto.py
- test_stale_dns.py
- conventions.py
- pytest
- saved_queries.py
- test_data_browser.py
- Cloud hosting and databases (AWS, Firebase)
- query-shell
- .Ask
- SchemaDiffView.tsx
- test_repo_detect.py
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- AwsClient
- CONTRIBUTING.md
- AwsClient
- sql_read_only_refusal
- rtdb_read
- with
- compilerOptions
- set_transport
- test_rtdb.py
- data_sources.py
- runner_loop
- cloud_aws.py
- test_backups_engine.py
- test_cli_client.py
- test_github_integration.py
- aws_statements
- package.json
- Get-DeployerSource
- mongodb
- compilerOptions
- tunnel
- DeviceExecutor
- worker
- integration/test_query_console.py
- test_cloud_boundary.py
- schema_diff.py
- test_cli_tokens.py
- MarkerKind
- docs/ARCHITECTURE.md - Deployer Architecture
- Core.cs
- supervisor.sh
- .ensure_github_role
- mongo_snapshot
- images
- FakeCloudflare
- test_mcp.py
- cli
- sample
- query_log.py
- AppFields
- apiSnippets.ts
- HANDOVER.md
- test_data_browser.py
- backup_engine.py
- analyze_documents
- crypto.py
- CheckRow
- LocalExecutor
- services
- test_container_config.py
- PassphraseFields.tsx
- run_mongosh
- wslplatform.tests.ps1
- volumes
- steps
- bundle
- C2-3 as built: Cloud Firestore
- Deploy a website with Deployer
- images
- SetupOptions
- _clean_up_slot
- api
- lan.tests.ps1
- jobs
- Schema endpoints, SchemaLink and ConventionIssue
- healthcheck
- redis
- steps
- WizardPage
- _load_dump
- test_transfer_stream.py
- models.py
- .Cleanup
- alerts.py
- utcnow
- mariadb
- mongodb-upgrade-6
- test_api_docs_routes.py
- mongodb-upgrade-8
- test_dead_code.py
- C2-2 as built: DynamoDB
- Invoke-Preflight
- test_sweep_leftovers_removes_stale_partials_and_temp_databases
- id_candidates
- test_query_docs.py
- test_skill_doc.py
- RtdbView.tsx
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_nat_network_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- to_api_error
- test_agent_skips_calls_whose_deadline_passed_and_keeps_short_calls_free
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
- scripts
- .delete_secret
- FakeCloud
- test_mysql_canceller_kills_the_query_from_a_private_pool
- _error_text
- error
- User
- subprocess
- test_data_api_keys.py
- install_error_handlers
- tsconfig.json
- FakeExecutor
- Invoke-DeployerNative
- Firestore point-in-time recovery and deletes (as built)
- install.ps1
- RequestMetricsMiddleware
- docker-entrypoint.sh
- _describe
- vite.config.ts
- signal
- API runtime dependencies (requirements.txt)
- fake_primary
- entrypoint.sh
- upgrade.sh
- Data API with API keys
- test_cli_provider_tools.py
- ci.yml
- release.yml
- deployer-api
- Commands
- InputField
- C2-4 as built: Firebase Realtime Database
- x-mongodb-upgrade
- main

## God Nodes (most connected - your core abstractions)
1. `ApiError` - 533 edges
2. `DataSource` - 378 edges
3. `App` - 227 edges
4. `Button` - 223 edges
5. `utcnow()` - 203 edges
6. `cn()` - 158 edges
7. `Alert()` - 155 edges
8. `useToast()` - 154 edges
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
- **Backup protection layers for a managed database** — docs_backups_snapshots, docs_backups_pitr, docs_backups_safety_snapshots, docs_backups_recently_deleted, docs_backups_platform_backup, docs_backups_verification [EXTRACTED 1.00]
- **Device runtime protocol (control channel, RPC routing, methods, transfers)** — docs_devices_control_channel, docs_devices_rpc_routing, docs_devices_rpc_methods, docs_devices_bulk_transfers [EXTRACTED 1.00]
- **Secrets encrypted at rest with MASTER_KEY** — docs_platforms_master_key, docs_platforms_table_instance_settings, docs_platforms_table_github_connections, docs_platforms_table_apps, docs_platforms_table_cloud_connections, docs_platforms_table_data_sources [EXTRACTED 1.00]
- **MCP billable tools gated by confirm_billing** — docs_mcp_confirm_billing_pattern, docs_mcp_tool_set_app_target, docs_mcp_tool_create_cloud_database, docs_mcp_tool_set_build_location, docs_mcp_tool_set_app_secrets_store, docs_mcp_tool_set_app_internet_access [EXTRACTED 1.00]
- **Cloudflare tunnel stack (link, sidecar, supervisor, handshake files, Caddy 8081)** — docs_remote_access_link_step, docs_remote_access_tunnel_sidecar, docs_remote_access_supervisor, docs_remote_access_desired_status_files, docs_remote_access_caddy_8081 [INFERRED 0.85]

## Communities (248 total, 24 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.09
Nodes (12): SettingsDialog, Autostart, KeepAwake, Lan, Port, ResetPasswordDialog, InputBox, Invalid (+4 more)

### Community 1 - "react"
Cohesion: 0.06
Nodes (84): api, qk, isJobFinished(), useApps(), useCohostEligibility(), useJob(), useProject(), ColumnSpec (+76 more)

### Community 2 - "Button"
Cohesion: 0.06
Nodes (157): refresh(), errorMessage(), invalidateProjectSources(), useProjects(), CloudDatabaseOptions, FirestoreBackup, SqlExternalEngine, GitHubIcon() (+149 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (153): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+145 more)

### Community 4 - "apps.py"
Cohesion: 0.07
Nodes (46): _actions_report(), add_domain(), BuildBody, cancel_deployment(), check_domain(), delete_app(), deploy(), DeployBody (+38 more)

### Community 5 - "oauth.py"
Cohesion: 0.03
Nodes (109): sha256_hex(), client_ip(), RefreshToken, change_password(), LinkIn, login(), LoginIn, logout() (+101 more)

### Community 6 - "Badge"
Cohesion: 0.06
Nodes (96): useSyncConflict(), useSyncConflicts(), useSyncHistory(), SyncConflict, SyncSide, Badge(), Menu(), MenuItem() (+88 more)

### Community 7 - "ApiError"
Cohesion: 0.03
Nodes (130): ApiError, DataSource, diff(), schema_at(), _schema_snapshot(), build_mongo_client(), check_status(), cloud_engine() (+122 more)

### Community 8 - "App"
Cohesion: 0.06
Nodes (47): App, AppUpdate, _audit_cohost(), _audit_database_access(), _check_api_key_access(), _check_billing(), _check_cohost(), _check_database_access() (+39 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (25): CheckOption, CheckColor, Checked, Description, ChoiceCard, Badge, BadgeColor, Checked (+17 more)

### Community 10 - "Device"
Cohesion: 0.05
Nodes (59): random_token(), Device, DeviceEnrollment, approve_enrollment(), create_enrollment(), deny_enrollment(), DeviceUpdate, download_transfer() (+51 more)

### Community 11 - "RestoreDialog.tsx"
Cohesion: 0.10
Nodes (39): hasLiveReplica(), useDataSourcesWithReplicas(), usePlacementOptions(), BackupCopy, BackupTrigger, RestoreMode, COPY_ICONS, COPY_LABELS (+31 more)

### Community 12 - "sqlalchemy"
Cohesion: 0.05
Nodes (28): run_migrations_offline(), run_migrations_online(), _url(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+20 more)

### Community 13 - "github.py"
Cohesion: 0.06
Nodes (35): GitHubConnection, github_connect(), github_disconnect(), github_repos(), github_status(), clone_token(), repo_token(), check_can_build() (+27 more)

### Community 14 - "rtdb.py"
Cohesion: 0.11
Nodes (25): _as_doc(), call(), check_key(), check_path(), check_value(), _child(), connection_info(), display() (+17 more)

### Community 15 - "DevicesPage.tsx"
Cohesion: 0.05
Nodes (69): useDevices(), Device, DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability, EnrollState (+61 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.20
Nodes (25): Project API keys (dpl_role_random), Platform data model (UUID-keyed MariaDB tables), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), docs/PLATFORMS.md - Platforms and accounts this project uses, AWS hosting and databases, deployer-boundary IAM permissions boundary, Three AWS IAM policies: DeployerHosting, DeployerDatabases, DeployerRoles, Cloudflare tunnel and DNS (+17 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.06
Nodes (69): ConventionIssue, ProjectSchema, SourceSchema, SchemaTab, labels, next, initialMode(), subscribe() (+61 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.08
Nodes (59): CloudflareZone, ProviderSettings, PublicUrlResponse, RemoteAccess, RemoteAccessMode, CopyField(), StepCard(), StepStatus (+51 more)

### Community 19 - "data_browser.py"
Cohesion: 0.22
Nodes (14): check_forbidden(), _collection(), decode_input(), delete_document(), encode_value(), _find_id(), insert_document(), _is_bool_column() (+6 more)

### Community 20 - "deploys.ts"
Cohesion: 0.07
Nodes (68): useApp(), useDeployment(), useDeployments(), App, AppDetectDraft, AppPreset, AppTarget, CloudTarget (+60 more)

### Community 21 - "GcpClient"
Cohesion: 0.05
Nodes (8): CloudError, _api_error(), GcpClient, _name(), _secret_id(), test_real_google_client_binding_and_provider_requests(), handle(), test_real_google_client_lists_providers_members_and_the_live_version()

### Community 22 - "mcp.py"
Cohesion: 0.06
Nodes (67): _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result(), handle(), _limit() (+59 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.08
Nodes (51): conflict(), _add_cloud_domain(), enqueue_domain_check(), m_tunnel(), get_value(), set_value(), _active_hostnames(), add_hostname() (+43 more)

### Community 24 - "test_monitoring.py"
Cohesion: 0.20
Nodes (12): _minute(), record_request(), factory(), host_point(), put_host(), test_alerts_open_hold_and_resolve(), test_container_rule_waits_two_minutes(), test_deliver_retries_with_backoff() (+4 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (20): ControlForm, IsBusy, State, LogWindow, ToolbarHeight, OutputWindow, ToolbarHeight, RunState (+12 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.06
Nodes (58): _audit(), AwsCredentials, _billing(), check_connection(), CloudBackupCreate, CloudDatabaseConnect, CloudDatabaseCreate, CloudRestore (+50 more)

### Community 27 - "Publish"
Cohesion: 0.05
Nodes (26): cache_control(), cloud_env(), _connection(), _job_prune(), prune(), Publish, poll(), poll() (+18 more)

### Community 28 - "provisioning.py"
Cohesion: 0.05
Nodes (58): get_settings(), Settings, ensure_database(), ensure_mongo_replica_set(), _redact(), _secrets(), dispose_all(), _database_env() (+50 more)

### Community 29 - "conftest.py"
Cohesion: 0.08
Nodes (28): get_engine(), set_redis(), _check_mariadb(), _check_mongodb(), _check_redis(), health(), _mongo_client(), auth_headers() (+20 more)

### Community 30 - "firestore.py"
Cohesion: 0.08
Nodes (45): _and(), _bad(), call(), check(), check_path(), collection_entity(), collection_ids(), composite_indexes() (+37 more)

### Community 31 - "Color"
Cohesion: 0.06
Nodes (32): ServiceTile, StatusPill, Glyphs, IconBadge, Color, Kind, Soft, IconKind (+24 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.08
Nodes (16): _create_cf_records(), CloudflareClient, _cname_body(), _err(), test_bearer_header_and_verify(), test_check_permissions_all_ok(), test_check_permissions_missing(), test_check_permissions_no_zones_and_no_accounts() (+8 more)

### Community 33 - "shell_runner.py"
Cohesion: 0.09
Nodes (15): _as_uid(), _child_env(), _field(), _kill(), main(), make_server(), do_POST(), _reply() (+7 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "test_cohost_apps.py"
Cohesion: 0.07
Nodes (35): AppReplica, apps_tunnel_token(), cohost_devices(), copy_problem(), deploy_params(), device_env(), device_problem(), eligible_devices() (+27 more)

### Community 36 - "WizardForm"
Cohesion: 0.11
Nodes (12): Card, BorderColor, Fill, Radius, TextBlock, RightAlign, SingleLine, TextColor (+4 more)

### Community 37 - "ThemedForm"
Cohesion: 0.14
Nodes (8): codeForStatus(), request(), isErrorBody(), parseError(), Json, SignInAppsDialog, Current, ProviderName

### Community 38 - "api_key_config"
Cohesion: 0.22
Nodes (10): api_key_config(), api_key_out(), ApiKeyCreate, create_api_key(), generate_secret(), list_api_keys(), _project_key(), reveal_api_key() (+2 more)

### Community 39 - "dynamo.py"
Cohesion: 0.10
Nodes (42): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), create_backups(), _cursor_in() (+34 more)

### Community 40 - "_reconcile_app"
Cohesion: 0.05
Nodes (46): enqueue_teardown(), artifact_for(), audience(), _aws_identity(), aws_policy(), builds_on_github(), cancel_setup(), _cel() (+38 more)

### Community 41 - "deployer_cli.py"
Cohesion: 0.14
Nodes (19): app_path(), _apply_hint(), ask_secret(), cmd_app_create(), cmd_deploy(), cmd_domain(), cmd_env(), cmd_google_apis() (+11 more)

### Community 42 - "NotebookConsole.tsx"
Cohesion: 0.03
Nodes (212): isDeviceOffline(), saveBlob(), useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSourceSchema(), DataSourceKind (+204 more)

### Community 43 - "firestore_admin.py"
Cohesion: 0.07
Nodes (34): backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids(), create_schedule() (+26 more)

### Community 44 - "test_dynamo.py"
Cohesion: 0.13
Nodes (26): aws(), base(), connect(), docs_url(), test_mcp_restore_tools(), call(), test_point_in_time_recovery_on_and_off(), test_restore_a_backup_into_a_new_database() (+18 more)

### Community 45 - "MCP.md"
Cohesion: 0.10
Nodes (47): CI job: Linux installer (install, CLI, update, uninstall), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits, Per-project MCP server (POST /v1/projects/<id>/mcp), MCP server for AI agents (+39 more)

### Community 46 - "README.md"
Cohesion: 0.06
Nodes (57): Docker Engine inside the deployer WSL distro (default runtime), Linux server platform (alternative to Windows PC), Windows PC platform (required unless Linux), docs/SETUP.md - Setting up Deployer, Cloudflare API token permissions (Tunnel Edit, Account Settings Read, DNS Edit, Zone Read), Open from any device with your own domain (Cloudflare tunnel), Deploy an app and connect an AI agent (MCP), The deployer command (CLI reference) (+49 more)

### Community 47 - "test_rds_tls.py"
Cohesion: 0.10
Nodes (15): _connect_args(), friendly_error(), _hint(), rds_ca(), try_sql(), test_connection_errors_get_a_plain_hint_and_keep_the_driver_text(), test_try_sql_gives_up_quickly_on_a_silent_server(), _bundle_certs() (+7 more)

### Community 48 - "record"
Cohesion: 0.04
Nodes (80): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+72 more)

### Community 49 - "services/backups.py"
Cohesion: 0.03
Nodes (128): encrypt_json(), validation_error(), BackupLogSegment, Job, new_id(), _cloud_cleanup(), any_copy(), archive_source_logs() (+120 more)

### Community 50 - "json.ts"
Cohesion: 0.10
Nodes (11): _connector(), DeviceAgent, run_agent(), _send(), write_status(), ws_url(), main(), _size() (+3 more)

### Community 51 - "introspection.py"
Cohesion: 0.04
Nodes (51): build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources(), export_sql_source() (+43 more)

### Community 52 - "source_sync.py"
Cohesion: 0.02
Nodes (135): SourceReplica, SyncConflict, SyncVersion, allocate_offset(), _check_value(), cohost_problem(), diff(), _drain() (+127 more)

### Community 53 - ".RenderChildren"
Cohesion: 0.14
Nodes (4): AppIcon, ThemedForm, IsForcedScale, Logo

### Community 55 - "connection"
Cohesion: 0.13
Nodes (30): connection(), base(), create(), _project_with_cloud_things(), test_app_runner_app_gets_the_cloud_database(), test_connect_existing_instance(), test_create_needs_admin_and_billing_confirmation_then_builds_the_instance(), test_create_without_default_vpc_fails_plainly() (+22 more)

### Community 56 - "services/transfer.py"
Cohesion: 0.03
Nodes (97): decrypt_json(), decrypt_with_passphrase(), encrypt_stream_with_passphrase(), Base, ApiKey, InstanceSetting, Project, ProjectInvite (+89 more)

### Community 57 - "get_redis"
Cohesion: 0.03
Nodes (64): DeviceProjectGrant, get_redis(), enroll_cancel(), create_move_job(), drop_copies_on_device(), _forget_lock(), run_move(), _run_move() (+56 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.10
Nodes (39): Data sources endpoints and DataSourceInput, Error envelope and common error codes, Health and setup endpoints, Members and invites endpoints, Projects endpoints, Role hierarchy viewer<developer<admin<owner, Backups, Versions & Recovery, Backups API (+31 more)

### Community 59 - "NativeMethods"
Cohesion: 0.17
Nodes (3): MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "test_github_actions.py"
Cohesion: 0.13
Nodes (32): app_out(), local_url(), role_name(), workflow_path(), aws(), by_run(), cloud_app(), committed() (+24 more)

### Community 61 - "services/cli_inputs.py"
Cohesion: 0.08
Nodes (20): cancel_input(), _cli_row(), get_input(), poll_input(), submit_input(), cancel(), cancel_for_token(), check_pending() (+12 more)

### Community 62 - "deployments.py"
Cohesion: 0.05
Nodes (62): CloudConnection, _job_archive(), _job_copy(), _job_drop(), _job_finalize_delete(), _job_prune(), _job_restore(), _job_snapshot() (+54 more)

### Community 63 - "AuditLog"
Cohesion: 0.03
Nodes (39): CaddyProxyHeaders, _is_ip(), AuditLog, create_invite(), test_prune(), _refresh(), test_change_password(), test_forwarded_headers_count_only_from_caddy() (+31 more)

### Community 64 - "test_cli_inputs.py"
Cohesion: 0.15
Nodes (29): CliInput, bearer(), _create(), _issue(), _poll(), _submit(), test_app_ids_need_developer(), test_app_ids_submit_with_nothing_typed_changes_nothing() (+21 more)

### Community 65 - "common.ps1"
Cohesion: 0.08
Nodes (38): Invoke-StatusJson(), Invoke-Update(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerStateTable(), Get-DeployerComposeServices(), Get-DeployerHealth() (+30 more)

### Community 66 - "make_app"
Cohesion: 0.04
Nodes (74): Deployment, DockerError, get_docker(), apps_dir(), _build(), container_name(), _DeployLog, _docker_failure() (+66 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.03
Nodes (142): ApiClientOptions, ApiError, client, DownloadResult, FetchFn, isApiError(), isApiStarting(), QueryValue (+134 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.10
Nodes (38): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, Checks to run before opening a PR (CI runs the same) (+30 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.17
Nodes (19): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _mongo_source(), RowDelete (+11 more)

### Community 71 - "projects.py"
Cohesion: 0.07
Nodes (21): create_project(), delete_project(), get_project(), list_projects(), ProjectCreate, ProjectUpdate, Provision, _provisioning() (+13 more)

### Community 72 - "DockerCli"
Cohesion: 0.06
Nodes (24): DockerCli, on(), _kill(), _watch(), _git_env(), parse_size(), _percent(), build_image() (+16 more)

### Community 73 - "InputRequestPage.tsx"
Cohesion: 0.12
Nodes (25): CliInputField, AppsUnavailable(), ClosedNotice(), destination(), Errors, FieldInput(), Header(), InputForm() (+17 more)

### Community 74 - "api_from_config"
Cohesion: 0.15
Nodes (18): api_from_config(), _app_status(), _ask_values(), cmd_alerts(), cmd_app_show(), human(), cmd_apps(), cmd_cloud() (+10 more)

### Community 75 - "test_firestore.py"
Cohesion: 0.10
Nodes (20): FakeAdmin, base(), connect(), docs_url(), _fail(), FakeFirestore, gcp(), test_app_runner_app_does_not_get_firestore() (+12 more)

### Community 76 - "metrics.py"
Cohesion: 0.18
Nodes (15): _avg(), container_problem(), containers(), current_host(), _hist(), host_points(), metrics(), p95() (+7 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "call"
Cohesion: 0.04
Nodes (45): _TempArtifact, dump_source(), restore_into(), call(), claim_upload(), create_transfer(), _error_from(), finish_transfer() (+37 more)

### Community 79 - "AuditLog"
Cohesion: 0.23
Nodes (18): base(), connected(), gcp(), run_job(), test_backup_schedules_backups_and_restore(), test_create_a_named_firestore_database(), test_delete_a_backup_and_an_export(), test_delete_a_firestore_database_needs_its_name_and_no_protection() (+10 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.11
Nodes (23): provider(), cloud_url(), go_live(), static(), target(), local(), API, C1 as built (+15 more)

### Community 81 - "tests/test_query_console.py"
Cohesion: 0.09
Nodes (28): run_sql(), _timeout_statement(), mongo_config(), run_fake(), test_mongosh_cursor_batch_and_truncation(), test_mongosh_errors_are_in_band(), test_mongosh_missing_in_sidecar_or_sidecar_down(), test_mongosh_node_escapes_refused_for_developers() (+20 more)

### Community 82 - "CliError"
Cohesion: 0.13
Nodes (12): all_apps(), Api, ask_web(), _cancel_input(), CliError, _cloudflare_stale(), cmd_ask(), cmd_login() (+4 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.07
Nodes (41): Domain, check_domain(), _merge_records(), fix_state_ownership(), test_apps_tunnel_created_once_cname_moves_and_ingress(), add_host(), assert_no_secrets(), desired() (+33 more)

### Community 84 - "routers/remote_access.py"
Cohesion: 0.22
Nodes (17): add_hostname(), delete_stale_records(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, quick() (+9 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.17
Nodes (21): create_access_token(), factory(), _callback(), _error_of(), _link_state(), _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error() (+13 more)

### Community 86 - "deployer.ps1"
Cohesion: 0.17
Nodes (44): Assert-Admin(), Get-Context(), Get-OnOffArgument(), Initialize-Engine(), Invoke-Autostart(), Invoke-Backup(), Invoke-Compose(), Invoke-Config() (+36 more)

### Community 87 - "UninstallForm"
Cohesion: 0.06
Nodes (12): ProcessResult, ScriptOutput, Integration, StartMenuDir, IShellLinkW, ShellLinkCoClass, Phase, Confirm (+4 more)

### Community 88 - "caddy"
Cohesion: 0.10
Nodes (22): internal, internal, command, depends_on, entrypoint, image, mem_limit, networks (+14 more)

### Community 89 - "options"
Cohesion: 0.16
Nodes (21): logging, logging, logging, driver, options, logging, logging, logging (+13 more)

### Community 90 - "Install-WslEngine"
Cohesion: 0.12
Nodes (27): Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Test-ExistingRuntime(), Write-DryRunAction(), ConvertTo-DeployerRuntimePath() (+19 more)

### Community 91 - "get_sessionmaker"
Cohesion: 0.05
Nodes (53): _detach(), _find_user(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore() (+45 more)

### Community 92 - "QueryEditor.tsx"
Cohesion: 0.13
Nodes (21): COLLECTION_METHODS, ConsoleAction, CURSOR_METHODS, cursorLine(), DB_METHODS, editorKeys, EditorMode, editorTheme() (+13 more)

### Community 93 - "crowsfoot.ts"
Cohesion: 0.18
Nodes (17): LinkCardinality, RelationshipCardinality, Cardinality, describeEnds(), EndMarker, MARKER_LABEL, MARKER_NOTATION, markerPath() (+9 more)

### Community 94 - "DumpScanner"
Cohesion: 0.16
Nodes (12): count_insert_rows(), _count_row_tuples(), DumpScanner, _mariadb_log_bin_enabled(), _mariadb_size_estimate(), mariadb_snapshot(), test_count_insert_rows_ignores_parens_inside_strings(), test_dump_scanner_collects_point_and_counts() (+4 more)

### Community 95 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+11 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "DecryptingReader"
Cohesion: 0.15
Nodes (5): DecryptingReader, open_artifact_plain(), _encrypted(), test_decrypting_reader_is_a_context_manager(), test_open_artifact_plain_uncompressed_closes_file_on_exit()

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (8): CheckResult, Internet, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "create_app"
Cohesion: 0.18
Nodes (4): create_app(), lifespan(), setup(), test_unhandled_error_is_enveloped()

### Community 101 - "test_backup_crypto.py"
Cohesion: 0.07
Nodes (31): body(), backup_key(), BackupCryptoError, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material() (+23 more)

### Community 102 - "test_stale_dns.py"
Cohesion: 0.14
Nodes (9): tunnel_cname_target(), linked(), stale(), test_delete_rechecks_and_skips_records_that_are_no_longer_stale(), test_delete_reports_a_record_that_vanished(), test_delete_validates_record_ids(), test_lists_only_unknown_tunnel_cnames(), test_non_owner_forbidden() (+1 more)

### Community 103 - "conventions.py"
Cohesion: 0.10
Nodes (45): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+37 more)

### Community 104 - "pytest"
Cohesion: 0.14
Nodes (19): build_create_table(), check_collection_name(), check_identifier(), check_type(), _constraint_name(), create_collection(), normalize_validator(), render_default() (+11 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.06
Nodes (52): SavedQuery, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query(), get_version() (+44 more)

### Community 106 - "test_data_browser.py"
Cohesion: 0.28
Nodes (15): _coerce_for_column(), _db_error(), delete_row(), _fetch_by_pk(), insert_row(), list_rows(), _pk_clause(), _pk_columns() (+7 more)

### Community 107 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.12
Nodes (18): AppSecrets, API, dashboard, MCP, AWS policy split as built: purpose-sized managed policies, C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway), C2 - cloud databases (what is left), Cloud hosting and databases (AWS, Firebase), Code, API, dashboard, Environment changes reach App Runner / Cloud Run apps at once (+10 more)

### Community 108 - "query-shell"
Cohesion: 0.11
Nodes (18): cap_add, cap_drop, command, cpus, entrypoint, extra_hosts, image, init (+10 more)

### Community 109 - ".Ask"
Cohesion: 0.06
Nodes (21): AppInfo, DefaultInstallDir, ExePath, PowerShellExe, Ref, Repo, RepoUrl, TroubleshootingUrl (+13 more)

### Community 110 - "SchemaDiffView.tsx"
Cohesion: 0.16
Nodes (22): DiffChange, FieldDiff, SchemaDiffEntity, AttributeChange, CHANGE_LABELS, CHANGE_ORDER, DiffSummary, fieldAttributeChanges() (+14 more)

### Community 111 - "test_repo_detect.py"
Cohesion: 0.12
Nodes (21): detect(), _detect_dir(), has(), src(), _dirs(), env_keys(), _find_module(), _join() (+13 more)

### Community 112 - "FakeDynamo"
Cohesion: 0.09
Nodes (3): FakeDynamo, _missing(), PitrFake

### Community 113 - "Query Console"
Cohesion: 0.13
Nodes (25): Data browser (SQL rows, MongoDB documents), Query Console, Query API endpoint, query.run audit event, Concurrency, timeout and output limits, Dashboard Query tab, CodeMirror editor and toolbar, In-band query errors vs HTTP errors (+17 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (3): Register-DeployerTask(), ConvertTo-DeployerWslPath(), Register-ScheduledTask()

### Community 115 - "AwsClient"
Cohesion: 0.08
Nodes (3): _code(), _wrap(), inner()

### Community 116 - "CONTRIBUTING.md"
Cohesion: 0.15
Nodes (14): CI job: Windows installer checks and DeployerSetup.exe, Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Ground rules, Layout (+6 more)

### Community 118 - "sql_read_only_refusal"
Cohesion: 0.19
Nodes (9): mongo_read_only_refusal(), split_sql(), sql_read_only_refusal(), test_mongo_read_only_accepts(), test_mongo_read_only_refuses(), test_read_only_refusals_name_the_word(), test_split_sql_respects_strings_and_comments(), test_sql_read_only_accepts() (+1 more)

### Community 119 - "rtdb_read"
Cohesion: 0.19
Nodes (5): _json_or_text(), list_documents(), list_rows(), list_subcollections(), rtdb_read()

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "set_transport"
Cohesion: 0.17
Nodes (8): set_transport(), test_secret_manager_rest_shapes(), test_firebase_connection_token_exchange_ignores_key_token_uri(), handle(), test_real_client_admin_and_storage_urls(), handle(), test_real_client_storage_objects(), test_real_client_builds_firestore_urls_and_shares_tokens()

### Community 123 - "test_rtdb.py"
Cohesion: 0.13
Nodes (19): base(), connect(), _fail(), FakeRtdb, by(), gcp(), test_browse_lazily_query_and_write_by_path(), test_cloud_run_app_gets_its_realtime_database() (+11 more)

### Community 124 - "data_sources.py"
Cohesion: 0.10
Nodes (17): _config_hosts(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate, _ensure_name_free(), external_config(), _is_internal() (+9 more)

### Community 125 - "runner_loop"
Cohesion: 0.18
Nodes (11): acquire_leadership(), _guard(), run(), mongo_replset_loop(), register_background_task(), release_leadership(), runner_loop(), scheduler_loop() (+3 more)

### Community 126 - "cloud_aws.py"
Cohesion: 0.17
Nodes (6): free_blocks(), _nat_alive(), _ours(), _public_subnet(), test_nat_helpers(), What the deploy makes (`cloud_deploy.Publish.nat_connector`, `cloud_aws.ensure_nat_network`)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.15
Nodes (9): binlog_name_with_seq(), binlog_seq(), parse_binlog(), rename_oplog_entry(), _event(), test_binlog_names(), test_parse_binlog_extracts_databases_and_times(), test_parse_mongodump_counts_and_compare() (+1 more)

### Community 128 - "test_cli_client.py"
Cohesion: 0.11
Nodes (35): env_of(), make_app(), _fill(), _http_error(), _login(), call(), _no_input_request(), _pipe() (+27 more)

### Community 130 - "aws_statements"
Cohesion: 0.14
Nodes (14): aws_statements(), requirements(), _actions(), _resources(), test_boundary_document_caps_roles_to_deployer_resources(), test_deployer_user_may_only_write_roles_that_carry_the_boundary(), test_policy_covers_databases_and_scopes_the_firewall(), test_policy_and_roles_cover_the_secret_stores() (+6 more)

### Community 131 - "package.json"
Cohesion: 0.09
Nodes (32): devDependencies, eslint@^10.10.0, @eslint/js@^10.0.1, eslint-plugin-react-hooks@^7.1.1, eslint-plugin-react-refresh@^0.5.7, globals@^17.12.0, jsdom@^30.0.1, tailwindcss@^4.3.3 (+24 more)

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

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "integration/test_query_console.py"
Cohesion: 0.14
Nodes (20): mariadb(), mongo(), run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results(), test_mariadb_multi_statement_script(), test_mariadb_read_only_session(), test_mariadb_session_state_does_not_leak() (+12 more)

### Community 139 - "test_cloud_boundary.py"
Cohesion: 0.08
Nodes (36): instance_role_name(), resource_name(), site_id(), set_enabled(), state_of(), aws_key_id(), aws_secret(), real_client() (+28 more)

### Community 140 - "schema_diff.py"
Cohesion: 0.22
Nodes (13): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), entity(), field() (+5 more)

### Community 141 - "test_cli_tokens.py"
Cohesion: 0.33
Nodes (12): _approve(), bearer(), _login(), _poll(), test_deny_and_expiry(), test_disabled_user_and_unknown_tokens_are_refused(), test_full_login_flow(), test_list_and_revoke() (+4 more)

### Community 142 - "MarkerKind"
Cohesion: 0.17
Nodes (11): Marker, MarkerKind, Check, Done, Error, None, Other, RebootRequired (+3 more)

### Community 143 - "docs/ARCHITECTURE.md - Deployer Architecture"
Cohesion: 0.11
Nodes (30): Deployer HTTP API v1, Auth endpoints (signup, login, refresh, OAuth), Export and import endpoints, Instance settings and users endpoints, OAuth callback redirect flow, docs/ARCHITECTURE.md - Deployer Architecture, Export / import format (deployer-export JSON, AES-GCM, scrypt), Export and import as background jobs in the API process (+22 more)

### Community 144 - "Core.cs"
Cohesion: 0.17
Nodes (3): DeployerSetup, DeployerCli, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 146 - ".ensure_github_role"
Cohesion: 0.20
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

### Community 147 - "mongo_snapshot"
Cohesion: 0.10
Nodes (19): BackupEngineError, _check_exit(), mariadb_defaults_file(), mongo_config_file(), mongo_root_uri(), _mongorestore(), _option_value(), private_tmpdir() (+11 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "FakeCloudflare"
Cohesion: 0.17
Nodes (5): set_transport(), fake_cf(), fake_cf(), FakeCloudflare, _ok()

### Community 150 - "test_mcp.py"
Cohesion: 0.08
Nodes (16): handle_push(), test_webhook_body_is_capped(), test_commit_sha_never_reaches_git_as_an_option(), test_parse_repo_refuses_dot_segments(), env(), call(), rpc(), _route_role() (+8 more)

### Community 151 - "cli"
Cohesion: 0.14
Nodes (5): cli(), urlopen(), _fail_on(), interrupt(), test_ctrl_c_exits_130_even_when_the_cancel_fails()

### Community 152 - "sample"
Cohesion: 0.20
Nodes (6): _iso(), sample(), sample_loop(), FakeDocker, test_docker_stats_parses_ps_inspect_and_stats(), test_sample_writes_bounded_host_series_and_containers()

### Community 153 - "query_log.py"
Cohesion: 0.14
Nodes (11): delete_before(), get_run(), list_runs(), prune(), record_run(), _trim_project(), env(), test_nat_gateway_users_are_counted_when_the_teardown_runs() (+3 more)

### Community 154 - "AppFields"
Cohesion: 0.15
Nodes (7): AppCreate, AppFields, _check_env(), _one_line(), _valid_branch(), reserved_env(), 6. Push-to-deploy apps, GitHub integration, MCP, monitoring/alerts, remote access

### Community 155 - "apiSnippets.ts"
Cohesion: 0.11
Nodes (23): buildQuery(), createApiClient(), download(), emit(), send(), setSession(), upload(), filenameFromDisposition() (+15 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.09
Nodes (31): Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Notes for AI agents (skill copy, MCP, graphify), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09), For AI agents (+23 more)

### Community 157 - "test_data_browser.py"
Cohesion: 0.21
Nodes (7): find_forbidden_operator(), test_driver_errors_become_plain_messages(), test_encode_value(), test_forbidden_operators(), test_list_rows_limit_is_capped(), test_parse_ejson_relaxed_and_ids(), test_shared_helpers_live_in_one_module()

### Community 158 - "backup_engine.py"
Cohesion: 0.12
Nodes (43): ArtifactWriter, check_db_name(), compare_counts(), _fetch_binlog(), _index_path(), _latest_oplog_ts(), _load_index(), _managed_user_for() (+35 more)

### Community 159 - "analyze_documents"
Cohesion: 0.15
Nodes (15): bad(), analyze_documents(), visit(), apply_mongo_indexes(), bson_type_name(), _compile_type(), introspect_mongo_collection(), mongo_indexes() (+7 more)

### Community 160 - "crypto.py"
Cohesion: 0.04
Nodes (59): _b64d(), _b64e(), decrypt_secret(), _derive(), encrypt_secret(), chunks(), encrypt_with_passphrase(), _master_key() (+51 more)

### Community 161 - "CheckRow"
Cohesion: 0.17
Nodes (12): CheckRow, Detail, SingleLine, State, TextLeft, Title, CheckStatus, Fail (+4 more)

### Community 162 - "LocalExecutor"
Cohesion: 0.15
Nodes (5): node_for(), backup_root(), LocalExecutor, _load_plugins(), main()

### Community 163 - "services"
Cohesion: 0.18
Nodes (10): command, volumes, volumes, volumes, services, api, migrate, query-shell (+2 more)

### Community 164 - "test_container_config.py"
Cohesion: 0.24
Nodes (7): read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through(), test_migrations_run_to_completion_before_the_api_starts(), test_query_shell_sidecar_holds_no_secrets(), test_security_headers_are_set_by_caddy_not_nginx(), test_untrusted_containers_share_no_network_with_the_api()

### Community 165 - "PassphraseFields.tsx"
Cohesion: 0.29
Nodes (3): PassphraseState, MIN_PASSPHRASE, MIN_PASSWORD

### Community 166 - "run_mongosh"
Cohesion: 0.10
Nodes (14): _call_shell(), _clamp(), _connect_uri(), _first_line(), parse_shell_output(), run_mongosh(), _shell_error_message(), _Watchdog (+6 more)

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
Cohesion: 0.10
Nodes (21): cursor(), Add database -> In your Firebase project, API, Apps on Cloud Run, Browsing, editing, querying, C2-3 as built: Cloud Firestore, C2-5 as built: MCP, transfer, project delete, Data model (+13 more)

### Community 172 - "Deploy a website with Deployer"
Cohesion: 0.17
Nodes (12): Cloud targets (AWS / Firebase through Deployer), Co-host PCs (the same app on other PCs, with failover), Connecting an AI agent (MCP), Deploy a website with Deployer, Do / don't, Feature status (check before promising anything), Hard rule: always ask which platform, People, sign-in and co-hosting (+4 more)

### Community 173 - "images"
Cohesion: 0.18
Nodes (11): name, needs, permissions, runs-on, strategy, component, context, images (+3 more)

### Community 174 - "SetupOptions"
Cohesion: 0.18
Nodes (8): SetupOptions, Autostart, DesktopShortcut, EnableLan, InstallDir, KeepAwake, Port, Runtime

### Community 175 - "_clean_up_slot"
Cohesion: 0.22
Nodes (5): _clean_up_slot(), _slot_pids(), _fake_proc(), test_clean_up_slot_kills_a_real_process(), test_slot_pids_reads_proc_without_forking()

### Community 176 - "api"
Cohesion: 0.20
Nodes (10): defaults, name, runs-on, defaults, name, runs-on, run, api (+2 more)

### Community 177 - "lan.tests.ps1"
Cohesion: 0.18
Nodes (5): Add-DeployerFirewallRule(), Enable-DeployerLanAccess(), Get-DeployerNonPrivateNetworks(), Write-DeployerNetworkProfileWarning(), Get-NetConnectionProfile()

### Community 178 - "jobs"
Cohesion: 0.20
Nodes (10): name, runs-on, name, runs-on, name, runs-on, jobs, compose (+2 more)

### Community 179 - "Schema endpoints, SchemaLink and ConventionIssue"
Cohesion: 0.44
Nodes (8): Schema endpoints, SchemaLink and ConventionIssue, Database Planning Conventions, Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle), ERD crow's-foot notation, Naming rules N1-N6, Structure rules S1-S8

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

### Community 184 - "_load_dump"
Cohesion: 0.29
Nodes (6): _load_dump(), feed(), name_rewriter(), rewrite_dump_line(), on_progress(), test_rewrite_dump_line()

### Community 185 - "test_transfer_stream.py"
Cohesion: 0.09
Nodes (13): _JsonReader, read_data_entry(), _stream_parts(), fill_once(), _dump(), fake_engine(), FakeConn, materialize() (+5 more)

### Community 186 - "models.py"
Cohesion: 0.02
Nodes (84): seal_process(), _resolve(), _authenticate(), _deny(), device_connect(), receive_messages(), _record_disconnect(), _record_heartbeat() (+76 more)

### Community 188 - "alerts.py"
Cohesion: 0.08
Nodes (34): dismiss_alert(), get_metrics(), get_summary(), list_alerts(), snooze_alert(), SnoozeBody, test_webhook(), WebhookTestBody (+26 more)

### Community 189 - "utcnow"
Cohesion: 0.03
Nodes (109): Backup, BackupCopy, BackupPolicy, utcnow(), sha256_file(), backup_out(), backups_out(), copies_by_artifact() (+101 more)

### Community 190 - "mariadb"
Cohesion: 0.29
Nodes (7): command, image, mem_limit, networks, restart, volumes, mariadb

### Community 191 - "mongodb-upgrade-6"
Cohesion: 0.29
Nodes (7): entrypoint, image, mem_limit, network_mode, profiles, volumes, mongodb-upgrade-6

### Community 192 - "test_api_docs_routes.py"
Cohesion: 0.43
Nodes (5): _documented(), _norm(), _paths(), _routes(), test_documented_endpoints_exist()

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

### Community 198 - "id_candidates"
Cohesion: 0.43
Nodes (4): id_candidates(), test_integer_ids_are_tried_before_the_string_form(), test_object_id_then_string(), test_out_of_range_or_non_numeric_stay_strings()

### Community 200 - "test_skill_doc.py"
Cohesion: 0.60
Nodes (3): _section(), test_co_host_apps_are_not_listed_as_not_built(), test_external_platform_table_lists_only_external_platforms()

### Community 201 - "RtdbView.tsx"
Cohesion: 0.29
Nodes (13): childPath(), cleanRtdbPath(), isBranch(), isRtdbKey(), parentPath(), preview(), Actions, Branch() (+5 more)

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

### Community 206 - "test_nat_network_runs_against_the_real_botocore_models"
Cohesion: 0.10
Nodes (8): nat_name(), _unless_gone(), nat_teardown_steps(), test_ensure_vpc_connector_runs_against_the_real_botocore_models(), test_nat_network_runs_against_the_real_botocore_models(), subnet(), Permissions added (`DeployerDatabases` and `DeployerHosting`, shown in Settings -> Cloud accounts), Shared, reference-counted, removed with the last user

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 209 - "to_api_error"
Cohesion: 0.17
Nodes (7): CloudflareError, to_api_error(), delete_stale_records(), finish(), _find_stale(), _record_host(), verify()

### Community 211 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.29
Nodes (7): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

### Community 212 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 214 - "FakeCloud"
Cohesion: 0.10
Nodes (14): set_factory(), set_factory(), aws(), aws(), aws(), KwFake, with_kwargs(), FakeCloud (+6 more)

### Community 216 - "_error_text"
Cohesion: 0.47
Nodes (4): _error_text(), _is_timeout(), _statement_error(), test_statement_error_classification()

### Community 217 - "error"
Cohesion: 0.09
Nodes (23): error(), primary(), text(), 8. Windows setup wizard and Deployer Control (C# WinForms), API, C2-1 as built: cloud databases in AWS (RDS / Aurora), Data model, New databases (+15 more)

### Community 218 - "User"
Cohesion: 0.02
Nodes (106): api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), load_project_access(), ProjectAccess (+98 more)

### Community 219 - "subprocess"
Cohesion: 0.24
Nodes (7): test_config_download(), test_conftest_removes_its_temp_dir_at_exit(), config_path(), _home(), _is_root(), _login_local(), save_config()

### Community 220 - "test_data_api_keys.py"
Cohesion: 0.07
Nodes (16): QueryRun, delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), serialize(), test_acting_user_falls_back_to_owner(), test_anon_key_is_not_advertised_as_public() (+8 more)

### Community 221 - "install_error_handlers"
Cohesion: 0.27
Nodes (6): _body(), install_error_handlers(), _api_error(), _http(), _unhandled(), _validation()

### Community 224 - "Invoke-DeployerNative"
Cohesion: 0.11
Nodes (19): Find-Python(), Invoke-PythonCli(), Test-CliCommand(), Test-CliSignedIn(), ConvertTo-DeployerArgument(), Disable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes() (+11 more)

### Community 225 - "Firestore point-in-time recovery and deletes (as built)"
Cohesion: 0.33
Nodes (6): API, Deletes (Backups tab; typed name), Firestore point-in-time recovery and deletes (as built), MCP, Not verified against real clouds, Point-in-time recovery (Backups tab -> Point-in-time recovery)

### Community 226 - "install.ps1"
Cohesion: 0.09
Nodes (17): Get-InstallerArgumentString(), Get-InstallerCliHint(), Get-SystemFacts(), Register-ResumeAfterReboot(), Request-Reboot(), Show-DockerDesktopNotice(), Write-CheckResult(), Write-InstallStep() (+9 more)

### Community 229 - "_describe"
Cohesion: 0.40
Nodes (3): _describe(), test_connection_errors_read_as_plain_words(), describe()

### Community 230 - "vite.config.ts"
Cohesion: 0.40
Nodes (4): @tailwindcss/vite@^4.3.3, @vitejs/plugin-react@^6.1.1, @tailwindcss/vite, @vitejs/plugin-react

### Community 233 - "API runtime dependencies (requirements.txt)"
Cohesion: 0.20
Nodes (12): API runtime dependencies (requirements.txt), alembic, argon2-cffi (password hashing), cryptography, API dev and test dependencies (requirements-dev.txt), fakeredis, pytest, ruff (+4 more)

### Community 235 - "fake_primary"
Cohesion: 0.18
Nodes (6): fake_primary(), FakePrimary, test_enrollment_poll_never_overwrites_a_cancel(), cancelled_meanwhile(), test_enrollment_poll_race_keeps_approved(), slow_primary()

### Community 242 - "Data API with API keys"
Cohesion: 0.29
Nodes (7): Calling from a browser, Config file, Data API with API keys, Rotating a key, Rows (SQL sources), Schema, Sending the key

### Community 243 - "test_cli_provider_tools.py"
Cohesion: 0.26
Nodes (7): _fake_run(), run(), test_google_apis_needs_gcloud_signed_in(), test_google_apis_takes_the_project_from_the_apps_client_id(), answers(), test_webhook_through_gh_sends_the_secret_on_stdin_only(), test_webhook_without_a_connection_or_gh_says_what_to_do()

### Community 247 - "ci.yml"
Cohesion: 0.17
Nodes (11): concurrency, cancel-in-progress, group, name, permissions, contents, branches, True (+3 more)

### Community 248 - "release.yml"
Cohesion: 0.33
Nodes (5): name, permissions, tags, True, push

### Community 251 - "Commands"
Cohesion: 0.29
Nodes (7): Commands, Google sign-in for your apps, How it works, Input requests, Instance settings without sudo, Sign in, The `deployer` command line (no browser, no sudo)

### Community 253 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

### Community 255 - "x-mongodb-upgrade"
Cohesion: 0.33
Nodes (6): x-mongodb-upgrade, entrypoint, mem_limit, network_mode, profiles, volumes

## Knowledge Gaps
- **145 isolated node(s):** `deployer-api`, `RFC-5987`, `RFC-4180`, `Checking`, `Running` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2566 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `apps.py`, `oauth.py`, `App`, `Device`, `integration/test_query_console.py`, `github.py`, `rtdb.py`, `data_browser.py`, `GcpClient`, `mcp.py`, `services/remote_access.py`, `query_log.py`, `routers/cloud.py`, `provisioning.py`, `conftest.py`, `backup_engine.py`, `firestore.py`, `analyze_documents`, `crypto.py`, `test_data_browser.py`, `test_cohost_apps.py`, `run_mongosh`, `dynamo.py`, `_reconcile_app`, `firestore_admin.py`, `record`, `services/backups.py`, `json.ts`, `introspection.py`, `source_sync.py`, `services/transfer.py`, `get_redis`, `models.py`, `alerts.py`, `services/cli_inputs.py`, `deployments.py`, `utcnow`, `AuditLog`, `test_cli_inputs.py`, `make_app`, `data.py`, `projects.py`, `call`, `to_api_error`, `tests/test_query_console.py`, `User`, `get_sessionmaker`, `install_error_handlers`, `test_stale_dns.py`, `pytest`, `saved_queries.py`, `test_data_browser.py`, `rtdb_read`, `data_sources.py`?**
  _High betweenness centrality (0.121) - this node is a cross-community bridge._
- **Are the 149 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 149 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.09019607843137255 - nodes in this community are weakly interconnected._
- **Why does `WizardForm` connect `WizardForm` to `Ui`, `CheckRow`, `.TestMarkers`, `ThemedForm`, `FlatButton`, `sqlalchemy`, `.Ask`, `SetupOptions`, `Core.cs`, `.RenderChildren`, `UninstallForm`, `ControlForm`, `.Cleanup`, `WizardPage`, `Color`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `react` be split into smaller, more focused modules?**
  _Cohesion score 0.0629757063914086 - nodes in this community are weakly interconnected._