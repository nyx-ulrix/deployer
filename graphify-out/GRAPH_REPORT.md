# Graph Report - deployer  (2026-10-27)

## Corpus Check
- 520 files · ~645,937 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9647 nodes · 34353 edges · 245 communities (216 shown, 29 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3337 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c46bd368`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- AccountSettingsPage.tsx
- Button
- types.ts
- source_sync.py
- oauth.py
- Badge
- ApiError
- update_app
- FlatButton
- Device
- BackupsTab.tsx
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
- services/remote_access.py
- test_monitoring.py
- ControlForm
- routers/cloud.py
- cloud_secrets.py
- provisioning.py
- User
- firestore.py
- Job
- CloudflareClient
- shell_runner.py
- deployer.sh
- test_cohost_apps.py
- WizardForm
- ThemedForm
- utcnow
- dynamo.py
- App
- deployer_cli.py
- NotebookConsole.tsx
- json.ts
- repoLinks.ts
- MCP.md
- README.md
- re
- routers/backups.py
- Backup
- post
- ddl_export.py
- SourceReplica
- Color
- BackupExecutor
- connection
- models.py
- test_devices_management.py
- Deployer HTTP API v1
- IShellLinkW
- get_schema
- services/cli_inputs.py
- deployments.py
- DataSource
- test_cli_inputs.py
- common.ps1
- make_app
- toast-context.ts
- docker-compose.yml
- environment
- data.py
- worker.py
- DockerCli
- sqlalchemy
- BackupCopy
- FakeCloud
- metrics.py
- services
- call
- QueryEditor.tsx
- Deployments (push-to-deploy) — phase 4
- tests/test_query_console.py
- run_query
- test_remote_access.py
- _github_delivery
- test_oauth.py
- deployer.ps1
- UninstallForm
- caddy
- options
- install.ps1
- enroll_start
- JobProgress.tsx
- Usability for non-experts
- DumpScanner
- connections.py
- migrate
- DecryptingReader
- .TestMarkers
- with
- create_app
- EncryptingWriter
- dependencies
- conventions.py
- restore_deleted_project
- saved_queries.py
- cn
- docs/ARCHITECTURE.md - Deployer Architecture
- query-shell
- .Ask
- ScriptRunner
- test_repo_detect.py
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- AwsClient
- mariadb_snapshot
- .set_aliases
- sql_read_only_refusal
- base64
- with
- compilerOptions
- set_transport
- test_rtdb.py
- data_sources.py
- FakeDevice
- routers/remote_access.py
- test_backups_engine.py
- test_cli_client.py
- test_github_integration.py
- scheduler_tick
- package.json
- Get-DeployerSource
- mongodb
- compilerOptions
- tunnel
- get_sessionmaker
- worker
- integration/test_query_console.py
- test_cloud_boundary.py
- schema_diff.py
- Remote Access & Custom Domains (Cloudflare)
- MarkerKind
- read_data_entry
- Core.cs
- supervisor.sh
- test_source_sync.py
- tempfile
- images
- FakeCloudflare
- env
- _client_for
- sample
- test_query_log.py
- CliError
- apiSnippets.ts
- HANDOVER.md
- eslint.config.js
- backup_engine.py
- introspect_mongo_collection
- error
- restore_cloud_backup
- LocalExecutor
- services
- test_container_config.py
- query/diff.ts
- run_mongosh
- wslplatform.tests.ps1
- volumes
- steps
- bundle
- C2-3 as built: Cloud Firestore
- Deploy a website with Deployer
- images
- SetupOptions
- test_cli_tokens.py
- api
- lan.tests.ps1
- jobs
- _Writer
- healthcheck
- redis
- steps
- WizardPage
- test_backups_pitr.py
- _JsonReader
- deployments.py
- G3 as built: a permissions boundary for the roles Deployer creates
- conditions
- utcnow
- mariadb
- mongodb-upgrade-6
- test_api_docs_routes.py
- mongodb-upgrade-8
- test_dead_code.py
- C2-2 as built: DynamoDB
- Invoke-Preflight
- test_sweep_leftovers_removes_stale_partials_and_temp_databases
- FakeExecutor
- test_query_docs.py
- test_skill_doc.py
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_nat_network_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- CloudflareError
- test_agent_skips_calls_whose_deadline_passed_and_keeps_short_calls_free
- Schema endpoints, SchemaLink and ConventionIssue
- scripts
- get_summary
- CheckRow
- test_mysql_canceller_kills_the_query_from_a_private_pool
- _error_text
- FakeConn
- services/cli_tokens.py
- _clean_up_slot
- Firestore point-in-time recovery and deletes (as built)
- install_error_handlers
- tsconfig.json
- Invoke-DeployerNative
- Settings
- runtime.tests.ps1
- RequestMetricsMiddleware
- docker-entrypoint.sh
- list_jobs
- KeyRoutesCORS
- ask_secret
- connection_info
- signal
- entrypoint.sh
- upgrade.sh
- ci.yml
- release.yml
- deployer-api
- C2-4 as built: Firebase Realtime Database
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
- `Checked and found OK` --references--> `deploy()`  [INFERRED]
  docs/SECURITY_REVIEW.md → api/app/routers/apps.py
- `How it works` --references--> `logout()`  [INFERRED]
  docs/CLI.md → api/app/routers/auth.py

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

## Communities (245 total, 29 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.08
Nodes (15): SettingsDialog, Autostart, KeepAwake, Lan, Port, InputBox, Invalid, Rule (+7 more)

### Community 1 - "AccountSettingsPage.tsx"
Cohesion: 0.09
Nodes (49): isApiError(), useProviders(), CliInputField, Identity, ProviderName, useAuth(), AuthShell(), GitHubIcon() (+41 more)

### Community 2 - "Button"
Cohesion: 0.06
Nodes (116): refresh(), errorMessage(), useApps(), useDataSources(), useInstanceSettings(), useProjects(), EnrollState, FirestoreBackup (+108 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (163): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+155 more)

### Community 4 - "source_sync.py"
Cohesion: 0.03
Nodes (50): redact(), redact_error(), _enter_read_only(), apply_changes(), dec(), DeviceSide, _dt(), _dumps_token() (+42 more)

### Community 5 - "oauth.py"
Cohesion: 0.02
Nodes (105): change_password(), LinkIn, login(), LoginIn, logout(), me(), MeUpdate, oauth_callback() (+97 more)

### Community 6 - "Badge"
Cohesion: 0.06
Nodes (124): isApiStarting(), isDeviceOffline(), useDevices(), useProject(), useSetupStatus(), useSyncConflict(), useSyncConflicts(), useSyncHistory() (+116 more)

### Community 7 - "ApiError"
Cohesion: 0.03
Nodes (81): copy_artifact(), register(), run_device_job(), run_executor_call(), _sized(), _TempArtifact, _apps_method(), CallContext (+73 more)

### Community 8 - "update_app"
Cohesion: 0.04
Nodes (71): add_domain(), AppCreate, AppFields, AppUpdate, _audit_cohost(), _audit_database_access(), BuildBody, cancel_deployment() (+63 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (27): CheckOption, CheckColor, Checked, Description, ChoiceCard, Badge, BadgeColor, Checked (+19 more)

### Community 10 - "Device"
Cohesion: 0.03
Nodes (102): random_token(), AppReplica, Device, DeviceEnrollment, DeviceProjectGrant, create_replica(), ReplicaCreate, approve_enrollment() (+94 more)

### Community 11 - "BackupsTab.tsx"
Cohesion: 0.04
Nodes (110): hasLiveReplica(), useCohostEligibility(), useDataSourcesWithReplicas(), usePlacementOptions(), Backup, BackupCopy, BackupSchedule, BackupTrigger (+102 more)

### Community 12 - "services/backups.py"
Cohesion: 0.06
Nodes (68): BackupLogSegment, any_copy(), archive_source_logs(), backup_out(), backups_out(), _columns(), consistent_at(), contiguous() (+60 more)

### Community 13 - "get_connection"
Cohesion: 0.07
Nodes (24): GitHubConnection, github_connect(), github_disconnect(), github_repos(), github_status(), clone_token(), _api(), apps_using() (+16 more)

### Community 14 - "rtdb.py"
Cohesion: 0.09
Nodes (29): _firebase_listing(), analyze_documents(), _as_doc(), call(), check(), check_key(), check_path(), check_value() (+21 more)

### Community 15 - "DevicesPage.tsx"
Cohesion: 0.08
Nodes (47): Device, DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability, ManagedEngine, PlacementOption (+39 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.08
Nodes (45): CI job: Windows installer checks and DeployerSetup.exe, Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Layout, PowerShell conventions (+37 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.04
Nodes (90): useSchema(), ConventionIssue, LinkCardinality, ProjectSchema, RelationshipCardinality, SourceSchema, SchemaTab, labels (+82 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.06
Nodes (82): CloudflareZone, CloudProvider, Domain, ProviderSettings, PublicUrlRequest, PublicUrlResponse, RemoteAccess, RemoteAccessMode (+74 more)

### Community 19 - "ApiError"
Cohesion: 0.06
Nodes (65): ApiError, bad(), check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document() (+57 more)

### Community 20 - "deploys.ts"
Cohesion: 0.05
Nodes (97): api, qk, invalidateProjectSources(), useApp(), useDeployment(), useDeployments(), App, AppDetectDraft (+89 more)

### Community 21 - "GcpClient"
Cohesion: 0.05
Nodes (9): CloudError, _api_error(), GcpClient, _name(), _secret_id(), handle(), test_real_google_client_binding_and_provider_requests(), handle() (+1 more)

### Community 22 - "mcp.py"
Cohesion: 0.07
Nodes (61): CloudRestore, FirestoreImport, _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result() (+53 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.08
Nodes (50): _add_cloud_domain(), to_api_error(), tunnel_cname_target(), set_value(), _active_hostnames(), add_hostname(), apps_tunnel_name(), _cached_zones() (+42 more)

### Community 24 - "test_monitoring.py"
Cohesion: 0.17
Nodes (15): active(), evaluate(), _minute(), record_request(), factory(), host_point(), put_host(), test_alerts_open_hold_and_resolve() (+7 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (19): ControlForm, IsBusy, State, RunState, Busy, Checking, NotResponding, Running (+11 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.07
Nodes (47): _audit(), AwsCredentials, _billing(), check_connection(), CloudDatabaseConnect, CloudDatabaseCreate, _confirm_delete(), connect_database() (+39 more)

### Community 27 - "cloud_secrets.py"
Cohesion: 0.08
Nodes (23): _runtime_settings(), resources(), cleanup(), enabled(), out(), resources(), _save_stored(), secret_name() (+15 more)

### Community 28 - "provisioning.py"
Cohesion: 0.05
Nodes (57): get_settings(), ensure_database(), dispose_all(), invalidate(), database_size(), m_drop(), m_provision(), save_credentials() (+49 more)

### Community 29 - "User"
Cohesion: 0.06
Nodes (45): Base, get_engine(), User, set_redis(), auth_payload(), create_access_token(), auth_headers(), factory() (+37 more)

### Community 30 - "firestore.py"
Cohesion: 0.07
Nodes (46): _and(), _bad(), call(), check(), check_path(), collection_entity(), collection_ids(), composite_indexes() (+38 more)

### Community 31 - "Job"
Cohesion: 0.05
Nodes (41): Job, _backup_rules(), _fmt_age(), detached_source_params(), enqueue_detached_finalize(), soft_delete_source(), start_drop(), start_platform_snapshot() (+33 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.09
Nodes (14): _create_cf_records(), CloudflareClient, _cname_body(), test_bearer_header_and_verify(), test_check_permissions_all_ok(), test_check_permissions_missing(), test_check_permissions_no_zones_and_no_accounts(), test_error_mapping() (+6 more)

### Community 33 - "shell_runner.py"
Cohesion: 0.09
Nodes (15): _as_uid(), _child_env(), _field(), _kill(), main(), make_server(), do_POST(), _reply() (+7 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "test_cohost_apps.py"
Cohesion: 0.07
Nodes (34): new_token(), create(), env(), sign(), test_app_hostnames(), test_create_list_get_and_roles(), test_database_access_is_admin_only(), test_delete_app_when_cloudflare_fails() (+26 more)

### Community 36 - "WizardForm"
Cohesion: 0.11
Nodes (12): Card, BorderColor, Fill, Radius, TextBlock, RightAlign, SingleLine, TextColor (+4 more)

### Community 37 - "ThemedForm"
Cohesion: 0.13
Nodes (4): AppIcon, ThemedForm, IsForcedScale, ResetPasswordDialog

### Community 38 - "utcnow"
Cohesion: 0.02
Nodes (117): sha256_hex(), api_key_not_allowed(), bearer_token(), check_api_key_rate(), client_ip(), decode_access_token(), get_current_user(), load_api_key_access() (+109 more)

### Community 39 - "dynamo.py"
Cohesion: 0.14
Nodes (31): aws_for(), backup_name(), _backup_out(), call(), check(), create_backups(), delete_document(), describe() (+23 more)

### Community 40 - "App"
Cohesion: 0.04
Nodes (89): App, cloud_url(), enqueue_teardown(), generate_dockerfile(), local_url(), resync_webhooks(), _shell_quote(), webhook_secret() (+81 more)

### Community 41 - "deployer_cli.py"
Cohesion: 0.16
Nodes (26): api_from_config(), app_path(), _app_status(), _apply_hint(), cmd_app_create(), cmd_app_show(), human(), cmd_apps() (+18 more)

### Community 42 - "NotebookConsole.tsx"
Cohesion: 0.03
Nodes (190): useSourceSchema(), DataSourceKind, MongoQueryResponse, QueryRequest, QueryRun, SavedQuery, SqlQueryResponse, SqlStatementResult (+182 more)

### Community 43 - "json.ts"
Cohesion: 0.21
Nodes (7): _cursor_out(), _size(), test_every_policy_leaves_room_under_the_iam_limit(), test_split_kept_exactly_the_previous_permissions(), docIdString(), itemKeyId(), JsonParse

### Community 44 - "repoLinks.ts"
Cohesion: 0.50
Nodes (3): blob, raw, repoLinks()

### Community 45 - "MCP.md"
Cohesion: 0.09
Nodes (55): CI job: Linux installer (install, CLI, update, uninstall), Notes for AI agents (skill copy, MCP, graphify), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits (+47 more)

### Community 46 - "README.md"
Cohesion: 0.07
Nodes (40): Invite people and turn on Google/GitHub sign-in apps, deployer.service systemd autostart, Setup troubleshooting table, Autostart scheduled task and 5-minute watchdog, Container runtime choices, Deploy an app, Deployer, The deployer command (PowerShell CLI) (+32 more)

### Community 47 - "re"
Cohesion: 0.07
Nodes (34): backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids(), create_schedule() (+26 more)

### Community 48 - "routers/backups.py"
Cohesion: 0.09
Nodes (34): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+26 more)

### Community 49 - "Backup"
Cohesion: 0.13
Nodes (20): Backup, BackupPolicy, new_id(), _bucket_keys(), _default_policy(), gfs_keep(), _kept_as(), SegmentChains (+12 more)

### Community 50 - "post"
Cohesion: 0.08
Nodes (25): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job(), projects_export() (+17 more)

### Community 51 - "ddl_export.py"
Cohesion: 0.05
Nodes (48): build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources(), export_sql_source() (+40 more)

### Community 52 - "SourceReplica"
Cohesion: 0.04
Nodes (74): SourceReplica, SyncConflict, SyncVersion, cohosting_eligibility(), delete_replica(), get_conflict(), list_conflicts(), list_replicas() (+66 more)

### Community 53 - "Color"
Cohesion: 0.07
Nodes (25): Logo, Glyphs, IconBadge, Color, Kind, Soft, IconKind, Check (+17 more)

### Community 54 - "BackupExecutor"
Cohesion: 0.05
Nodes (10): register_copy_target(), unregister(), BackupExecutor, DeviceExecutorUnavailable, register_device_executor_factory(), RemoteArtifactError, run_local_call(), test_copy_hook() (+2 more)

### Community 55 - "connection"
Cohesion: 0.07
Nodes (52): aws_statements(), connection(), test_policy_covers_databases_and_scopes_the_firewall(), test_policy_and_roles_cover_the_secret_stores(), test_target_rules(), aws(), base(), connect() (+44 more)

### Community 56 - "models.py"
Cohesion: 0.03
Nodes (102): _b64d(), _b64e(), decrypt_json(), decrypt_secret(), decrypt_with_passphrase(), _derive(), encrypt_secret(), encrypt_stream_with_passphrase() (+94 more)

### Community 57 - "test_devices_management.py"
Cohesion: 0.06
Nodes (34): create_move_job(), run_move(), start_move(), device_source(), add_source(), docker(), fake_cf(), fake_mongosh() (+26 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.08
Nodes (48): Deployer HTTP API v1, Project API keys (dpl_role_random), Auth endpoints (signup, login, refresh, OAuth), Data sources endpoints and DataSourceInput, Error envelope and common error codes, Export and import endpoints, Health and setup endpoints, Instance settings and users endpoints (+40 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.09
Nodes (5): IShellLinkW, ShellLinkCoClass, MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "get_schema"
Cohesion: 0.12
Nodes (18): t_get_schema(), CollectionInput, ColumnReference, ColumnSpec, create_collection(), create_link(), create_table(), delete_link() (+10 more)

### Community 61 - "services/cli_inputs.py"
Cohesion: 0.09
Nodes (25): _apps_for(), cancel_input(), _cli_row(), create_input(), get_input(), poll_input(), submit_input(), apps_out() (+17 more)

### Community 62 - "deployments.py"
Cohesion: 0.04
Nodes (57): _job_archive(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify(), client(), _backup_status() (+49 more)

### Community 63 - "DataSource"
Cohesion: 0.03
Nodes (80): encrypt_json(), CloudConnection, DataSource, _cloud_cleanup(), _bad(), check_connection(), config_of(), connection_out() (+72 more)

### Community 64 - "test_cli_inputs.py"
Cohesion: 0.09
Nodes (35): CliInput, _check_env(), InputCreate, InputField, InputSubmit, reserved_env(), expire_due(), prune() (+27 more)

### Community 65 - "common.ps1"
Cohesion: 0.07
Nodes (45): Invoke-Update(), Get-SystemFacts(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerArgument(), ConvertTo-DeployerRuntimePath(), ConvertTo-DeployerStateTable() (+37 more)

### Community 66 - "make_app"
Cohesion: 0.05
Nodes (91): Deployment, site_id(), _enqueue_job(), handle_push(), logs_key(), republish(), rollback(), runtime_logs() (+83 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.03
Nodes (97): ApiClientOptions, ApiError, buildQuery(), client, codeForStatus(), createApiClient(), download(), emit() (+89 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.06
Nodes (57): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, API runtime dependencies (requirements.txt) (+49 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.10
Nodes (25): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _json_or_text(), list_documents() (+17 more)

### Community 71 - "worker.py"
Cohesion: 0.12
Nodes (16): ensure_mongo_replica_set(), acquire_leadership(), _guard(), _load_plugins(), main(), mongo_replset_loop(), register_background_task(), release_leadership() (+8 more)

### Community 72 - "DockerCli"
Cohesion: 0.04
Nodes (47): DockerCli, on(), _kill(), _watch(), DockerError, get_docker(), _git_env(), parse_size() (+39 more)

### Community 73 - "sqlalchemy"
Cohesion: 0.05
Nodes (28): run_migrations_offline(), run_migrations_online(), _url(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+20 more)

### Community 74 - "BackupCopy"
Cohesion: 0.11
Nodes (20): BackupCopy, _artifact_host(), _copy_destination(), _final_snapshot_detached(), _job_copy(), _job_platform_snapshot(), local_copy(), progress() (+12 more)

### Community 75 - "FakeCloud"
Cohesion: 0.06
Nodes (19): set_factory(), set_factory(), aws(), aws(), aws(), KwFake, with_kwargs(), FakeCloud (+11 more)

### Community 76 - "metrics.py"
Cohesion: 0.17
Nodes (16): _container_rules(), _avg(), container_problem(), containers(), current_host(), _hist(), host_points(), metrics() (+8 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "call"
Cohesion: 0.04
Nodes (43): allocate_offset(), _drop_device_copy(), run_copy(), DeviceExecutor, dump_source(), restore_into(), call(), claim_upload() (+35 more)

### Community 79 - "QueryEditor.tsx"
Cohesion: 0.13
Nodes (20): COLLECTION_METHODS, ConsoleAction, CURSOR_METHODS, cursorLine(), DB_METHODS, editorKeys, EditorMode, editorTheme() (+12 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.12
Nodes (23): provider(), static(), target(), local(), API, API, C1 as built, Cloud connections (+15 more)

### Community 81 - "tests/test_query_console.py"
Cohesion: 0.09
Nodes (28): run_sql(), _timeout_statement(), mongo_config(), run_fake(), test_mongosh_cursor_batch_and_truncation(), test_mongosh_errors_are_in_band(), test_mongosh_missing_in_sidecar_or_sidecar_down(), test_mongosh_node_escapes_refused_for_developers() (+20 more)

### Community 82 - "run_query"
Cohesion: 0.40
Nodes (3): t_run_query(), QueryRequest, run_query()

### Community 83 - "test_remote_access.py"
Cohesion: 0.09
Nodes (37): Domain, fix_state_ownership(), add_host(), assert_no_secrets(), desired(), link(), test_add_hostname_dns_failure_rolls_back_ingress(), test_add_hostname_existing_record() (+29 more)

### Community 84 - "_github_delivery"
Cohesion: 0.15
Nodes (12): _actions_report(), _github_delivery(), github_webhook(), read_body_capped(), verify_signature(), 4. Push-to-deploy, 7. Deploying to the cloud, 8. Installing, updating and staying up (+4 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.20
Nodes (18): _callback(), _error_of(), _link_state(), _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error(), test_callback_requires_same_browser(), test_github_requires_primary_verified_email() (+10 more)

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
Cohesion: 0.19
Nodes (19): logging, logging, logging, driver, options, logging, logging, logging (+11 more)

### Community 90 - "install.ps1"
Cohesion: 0.13
Nodes (33): Get-InstallerArgumentString(), Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Register-ResumeAfterReboot(), Request-Reboot() (+25 more)

### Community 91 - "enroll_start"
Cohesion: 0.05
Nodes (35): device_status(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to(), _load_state() (+27 more)

### Community 92 - "JobProgress.tsx"
Cohesion: 0.20
Nodes (16): saveBlob(), isJobFinished(), useJob(), ImportJobResult, ImportSummary, JobStatus, JobRow(), JobStatusBadge() (+8 more)

### Community 93 - "Usability for non-experts"
Cohesion: 0.09
Nodes (21): Checklist, Critical, Deployer audit - 2026-09-28, Executive summary, High, Journey 1: Install on an old PC, Journey 2: First run and owner account, Journey 3: Create a project, a table and some rows (+13 more)

### Community 94 - "DumpScanner"
Cohesion: 0.19
Nodes (9): count_insert_rows(), _count_row_tuples(), DumpScanner, test_count_insert_rows_ignores_parens_inside_strings(), test_dump_scanner_collects_point_and_counts(), _scan(), test_count_insert_rows_first_line_only(), test_multi_line_extended_insert_as_written_by_mariadb_11() (+1 more)

### Community 95 - "connections.py"
Cohesion: 0.04
Nodes (75): build_mongo_client(), build_sql_engine(), check_status(), cloud_engine(), _connect_args(), connection_info(), display_for(), _fingerprint() (+67 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "DecryptingReader"
Cohesion: 0.12
Nodes (7): DecryptingReader, feed(), name_rewriter(), rewrite_dump_line(), test_decrypting_reader_is_a_context_manager(), test_open_artifact_plain_uncompressed_closes_file_on_exit(), test_rewrite_dump_line()

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (7): CheckResult, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "create_app"
Cohesion: 0.14
Nodes (5): seal_process(), create_app(), lifespan(), setup(), test_unhandled_error_is_enveloped()

### Community 101 - "EncryptingWriter"
Cohesion: 0.07
Nodes (32): body(), backup_key(), BackupCryptoError, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material() (+24 more)

### Community 102 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+11 more)

### Community 103 - "conventions.py"
Cohesion: 0.11
Nodes (42): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+34 more)

### Community 104 - "restore_deleted_project"
Cohesion: 0.13
Nodes (9): _deleted_project(), deleted_project_backups(), _deleted_project_finals(), _deleted_source(), instance_health(), last_verification(), restore_deleted_project(), unfinished_detached_deletes() (+1 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.12
Nodes (27): SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query() (+19 more)

### Community 106 - "cn"
Cohesion: 0.09
Nodes (50): useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useCurrentUser(), AlertBadge(), AppLayout(), navClass() (+42 more)

### Community 107 - "docs/ARCHITECTURE.md - Deployer Architecture"
Cohesion: 0.05
Nodes (36): Ground rules, AppSecrets, docs/ARCHITECTURE.md - Deployer Architecture, API layering: routers, deps, services, drivers, Security model (argon2id, JWT, refresh rotation, AES-256-GCM, rate limits), Commands, Google sign-in for your apps, How it works (+28 more)

### Community 108 - "query-shell"
Cohesion: 0.11
Nodes (18): cap_add, cap_drop, command, cpus, entrypoint, extra_hosts, image, init (+10 more)

### Community 109 - ".Ask"
Cohesion: 0.07
Nodes (21): AppInfo, DefaultInstallDir, ExePath, PowerShellExe, Ref, Repo, RepoUrl, TroubleshootingUrl (+13 more)

### Community 110 - "ScriptRunner"
Cohesion: 0.09
Nodes (8): LogWindow, ToolbarHeight, OutputWindow, ToolbarHeight, Payload, ScriptRunner, Cancelled, IsRunning

### Community 111 - "test_repo_detect.py"
Cohesion: 0.12
Nodes (21): detect(), _detect_dir(), has(), src(), _dirs(), env_keys(), _find_module(), _join() (+13 more)

### Community 112 - "FakeDynamo"
Cohesion: 0.09
Nodes (4): FakeDynamo, _missing(), PitrFake, test_retried_restore_never_asks_twice()

### Community 113 - "Query Console"
Cohesion: 0.13
Nodes (25): Data browser (SQL rows, MongoDB documents), Query Console, Query API endpoint, query.run audit event, Concurrency, timeout and output limits, Dashboard Query tab, CodeMirror editor and toolbar, In-band query errors vs HTTP errors (+17 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (3): Register-DeployerTask(), ConvertTo-DeployerWslPath(), Register-ScheduledTask()

### Community 115 - "AwsClient"
Cohesion: 0.06
Nodes (6): AwsClient, _code(), _wrap(), test_secrets_manager_calls_match_botocore_models(), Not verified against real clouds, The fix: `deployer-boundary`

### Community 116 - "mariadb_snapshot"
Cohesion: 0.17
Nodes (15): ArtifactWriter, _fetch_binlog(), _index_path(), _load_index(), mariadb_archive_logs(), mariadb_defaults_file(), mariadb_snapshot(), mongo_config_file() (+7 more)

### Community 118 - "sql_read_only_refusal"
Cohesion: 0.14
Nodes (12): _first_keyword(), _is_blank(), _leading_keyword(), mongo_read_only_refusal(), split_sql(), sql_read_only_refusal(), test_mongo_read_only_accepts(), test_mongo_read_only_refuses() (+4 more)

### Community 119 - "base64"
Cohesion: 0.17
Nodes (11): _bad(), _cursor_in(), key_of(), equals(), plain(), run_console(), serialize(), serialize_item() (+3 more)

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "set_transport"
Cohesion: 0.14
Nodes (9): set_transport(), token(), test_secret_manager_rest_shapes(), test_real_client_admin_and_storage_urls(), handle(), test_real_client_storage_objects(), test_real_client_builds_firestore_urls_and_shares_tokens(), handle() (+1 more)

### Community 123 - "test_rtdb.py"
Cohesion: 0.11
Nodes (23): requirements(), test_google_requirements_include_firestore_backups(), test_google_requirements_include_firestore(), base(), connect(), _fail(), FakeRtdb, by() (+15 more)

### Community 124 - "data_sources.py"
Cohesion: 0.11
Nodes (20): validation_error(), _key_param(), check_data_source(), _config_hosts(), create_data_source(), DataSourceInput, DataSourceUpdate, delete_data_source() (+12 more)

### Community 125 - "FakeDevice"
Cohesion: 0.12
Nodes (6): CallListener, publish_reply(), reply_channel(), fake_device(), factory(), FakeDevice

### Community 126 - "routers/remote_access.py"
Cohesion: 0.20
Nodes (15): add_hostname(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, quick(), QuickBody (+7 more)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.16
Nodes (8): binlog_name_with_seq(), binlog_seq(), parse_binlog(), rename_oplog_entry(), _event(), test_binlog_names(), test_parse_binlog_extracts_databases_and_times(), test_rename_oplog_entry()

### Community 128 - "test_cli_client.py"
Cohesion: 0.08
Nodes (33): env_of(), cli(), urlopen(), _fail_on(), _fill(), _http_error(), _login(), call() (+25 more)

### Community 129 - "test_github_integration.py"
Cohesion: 0.06
Nodes (21): set_docker(), FakeDockerCli, b64(), connect(), docker(), env(), fake_token(), FakeGitHub (+13 more)

### Community 130 - "scheduler_tick"
Cohesion: 0.32
Nodes (4): _discard_new_source(), reconcile_interrupted(), _redis_due(), scheduler_tick()

### Community 131 - "package.json"
Cohesion: 0.10
Nodes (26): devDependencies, eslint@^10.10.0, jsdom@^30.0.1, tailwindcss@^4.3.3, @tailwindcss/vite@^4.3.3, @types/node@^22.20.3, @types/react@^19.3.0, @types/react-dom@^19.3.0 (+18 more)

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

### Community 136 - "get_sessionmaker"
Cohesion: 0.06
Nodes (39): _detach(), _find_user(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore() (+31 more)

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "integration/test_query_console.py"
Cohesion: 0.14
Nodes (20): mariadb(), mongo(), run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results(), test_mariadb_multi_statement_script(), test_mariadb_read_only_session(), test_mariadb_session_state_does_not_leak() (+12 more)

### Community 139 - "test_cloud_boundary.py"
Cohesion: 0.21
Nodes (12): aws_key_id(), aws_secret(), _actions(), real_client(), _resources(), role(), test_boundary_document_caps_roles_to_deployer_resources(), test_deployer_user_may_only_write_roles_that_carry_the_boundary() (+4 more)

### Community 140 - "schema_diff.py"
Cohesion: 0.22
Nodes (13): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), entity(), field() (+5 more)

### Community 141 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.26
Nodes (16): Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes, Link step (find or create tunnel, fetch connector token) (+8 more)

### Community 142 - "MarkerKind"
Cohesion: 0.17
Nodes (11): Marker, MarkerKind, Check, Done, Error, None, Other, RebootRequired (+3 more)

### Community 143 - "read_data_entry"
Cohesion: 0.18
Nodes (7): read_data_entry(), _stream_parts(), materialize(), test_bare_numbers_cut_by_the_buffer(), test_lazy_entry_matches_json_load(), test_unread_rows_are_skipped_in_order(), Trickle

### Community 144 - "Core.cs"
Cohesion: 0.15
Nodes (4): DeployerSetup, DeployerCli, Internet, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 146 - "test_source_sync.py"
Cohesion: 0.05
Nodes (31): sync_round(), _conflicts(), _fake_binlog(), gtid(), __init__(), FakeSide, FakeStore, _read_all() (+23 more)

### Community 147 - "tempfile"
Cohesion: 0.13
Nodes (12): BackupEngineError, _check_exit(), _mongorestore(), open_artifact_plain(), _replay_binlogs(), feed(), _run_mariadb_client(), _run_tool() (+4 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "FakeCloudflare"
Cohesion: 0.13
Nodes (5): set_transport(), _err(), fake_cf(), FakeCloudflare, _ok()

### Community 150 - "env"
Cohesion: 0.20
Nodes (9): inner(), run(), env(), call(), rpc(), test_data_tools(), test_document_tools(), recorder() (+1 more)

### Community 151 - "_client_for"
Cohesion: 0.23
Nodes (7): add_domain(), check_domain(), _client_for(), _delete_cf_records(), enqueue_domain_check(), _merge_records(), remove_domain()

### Community 152 - "sample"
Cohesion: 0.20
Nodes (6): _iso(), sample(), sample_loop(), FakeDocker, test_docker_stats_parses_ps_inspect_and_stats(), test_sample_writes_bounded_host_series_and_containers()

### Community 153 - "test_query_log.py"
Cohesion: 0.04
Nodes (37): QueryRun, delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), delete_before(), get_run(), list_runs() (+29 more)

### Community 154 - "CliError"
Cohesion: 0.14
Nodes (14): all_apps(), Api, ask_web(), _cancel_input(), CliError, cmd_login(), cmd_logout(), config_path() (+6 more)

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.09
Nodes (32): Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09), For AI agents, Full codebase audit (198 findings, all ticked) (+24 more)

### Community 157 - "eslint.config.js"
Cohesion: 0.18
Nodes (10): @eslint/js@^10.0.1, eslint-plugin-react-hooks@^7.1.1, eslint-plugin-react-refresh@^0.5.7, globals@^17.12.0, typescript-eslint@^8.70.0, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh (+2 more)

### Community 158 - "backup_engine.py"
Cohesion: 0.11
Nodes (43): check_db_name(), compare_counts(), _latest_oplog_ts(), _load_dump(), _managed_user_for(), _mariadb_clear(), _mariadb_create_db(), mariadb_current_point() (+35 more)

### Community 159 - "introspect_mongo_collection"
Cohesion: 0.24
Nodes (9): visit(), apply_mongo_indexes(), bson_type_name(), _compile_type(), introspect_mongo_collection(), mongo_indexes(), _sort_types(), _value_type() (+1 more)

### Community 160 - "error"
Cohesion: 0.06
Nodes (33): client(), rows(), error(), primary(), text(), 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough (+25 more)

### Community 161 - "restore_cloud_backup"
Cohesion: 0.13
Nodes (16): CloudBackupCreate, create_cloud_backup(), _dynamo_source(), list_cloud_backups(), PitrUpdate, set_point_in_time_recovery(), t_create_cloud_backup(), t_list_cloud_backups() (+8 more)

### Community 163 - "services"
Cohesion: 0.18
Nodes (10): command, volumes, volumes, volumes, services, api, migrate, query-shell (+2 more)

### Community 164 - "test_container_config.py"
Cohesion: 0.24
Nodes (7): read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through(), test_migrations_run_to_completion_before_the_api_starts(), test_query_shell_sidecar_holds_no_secrets(), test_security_headers_are_set_by_caddy_not_nginx(), test_untrusted_containers_share_no_network_with_the_api()

### Community 165 - "query/diff.ts"
Cohesion: 0.39
Nodes (7): DIFF_MAX_LINES, DiffLine, diffStats(), lineDiff(), lines(), render(), DiffView()

### Community 166 - "run_mongosh"
Cohesion: 0.10
Nodes (14): _call_shell(), _clamp(), _connect_uri(), _first_line(), parse_shell_output(), run_mongosh(), _shell_error_message(), _Watchdog (+6 more)

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
Cohesion: 0.13
Nodes (18): bad(), key(), cursor(), device_apply(), Add database -> In your Firebase project, Apps on Cloud Run, Browsing, editing, querying, Browsing, editing, querying (+10 more)

### Community 172 - "Deploy a website with Deployer"
Cohesion: 0.17
Nodes (12): Cloud targets (AWS / Firebase through Deployer), Co-host PCs (the same app on other PCs, with failover), Connecting an AI agent (MCP), Deploy a website with Deployer, Do / don't, Feature status (check before promising anything), Hard rule: always ask which platform, People, sign-in and co-hosting (+4 more)

### Community 173 - "images"
Cohesion: 0.18
Nodes (11): name, needs, permissions, runs-on, strategy, component, context, images (+3 more)

### Community 174 - "SetupOptions"
Cohesion: 0.18
Nodes (8): SetupOptions, Autostart, DesktopShortcut, EnableLan, InstallDir, KeepAwake, Port, Runtime

### Community 175 - "test_cli_tokens.py"
Cohesion: 0.33
Nodes (12): _approve(), bearer(), _login(), _poll(), test_deny_and_expiry(), test_disabled_user_and_unknown_tokens_are_refused(), test_full_login_flow(), test_list_and_revoke() (+4 more)

### Community 176 - "api"
Cohesion: 0.20
Nodes (10): defaults, name, runs-on, defaults, name, runs-on, run, api (+2 more)

### Community 177 - "lan.tests.ps1"
Cohesion: 0.18
Nodes (5): Add-DeployerFirewallRule(), Enable-DeployerLanAccess(), Get-DeployerNonPrivateNetworks(), Write-DeployerNetworkProfileWarning(), Get-NetConnectionProfile()

### Community 178 - "jobs"
Cohesion: 0.20
Nodes (10): name, runs-on, name, runs-on, name, runs-on, jobs, compose (+2 more)

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

### Community 184 - "test_backups_pitr.py"
Cohesion: 0.24
Nodes (13): sha256_file(), perform_verify(), _error_text(), _iso(), _pause(), _restore(), _run_all(), _snapshot() (+5 more)

### Community 185 - "_JsonReader"
Cohesion: 0.27
Nodes (4): _JsonReader, fill_once(), test_remove_or_demote_lists_keys_to_rotate(), make_key()

### Community 186 - "deployments.py"
Cohesion: 0.02
Nodes (64): conflict(), get_redis(), dispatch_env_deployment(), enroll_cancel(), _save_if_current(), _save_state(), _check_mariadb(), _check_mongodb() (+56 more)

### Community 187 - "G3 as built: a permissions boundary for the roles Deployer creates"
Cohesion: 0.67
Nodes (3): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, The threat

### Community 188 - "conditions"
Cohesion: 0.44
Nodes (8): _api_rule(), _cloud_cleanup_rule(), Condition, conditions(), _fmt_gb(), _host_rules(), _replica_rules(), _tunnel_rule()

### Community 189 - "utcnow"
Cohesion: 0.06
Nodes (36): prune_all(), _hourly_with_pitr(), _iso(), _segment(), _snapshot(), test_archive_logs_creates_and_extends_segments(), test_copy_target_and_restore_device_follow_sharing_rules(), test_deleted_project_final_snapshot_is_listed_and_downloadable() (+28 more)

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

### Community 200 - "test_skill_doc.py"
Cohesion: 0.60
Nodes (3): _section(), test_co_host_apps_are_not_listed_as_not_built(), test_external_platform_table_lists_only_external_platforms()

### Community 201 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.25
Nodes (8): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, New databases, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

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
Cohesion: 0.07
Nodes (17): free_blocks(), _nat_alive(), nat_name(), _ours(), _public_subnet(), _unless_gone(), nat_teardown_steps(), test_ensure_vpc_connector_runs_against_the_real_botocore_models() (+9 more)

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 211 - "Schema endpoints, SchemaLink and ConventionIssue"
Cohesion: 0.44
Nodes (8): Schema endpoints, SchemaLink and ConventionIssue, Database Planning Conventions, Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle), ERD crow's-foot notation, Naming rules N1-N6, Structure rules S1-S8

### Community 212 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 213 - "get_summary"
Cohesion: 0.47
Nodes (4): get_metrics(), get_summary(), list_alerts(), visible()

### Community 214 - "CheckRow"
Cohesion: 0.17
Nodes (12): CheckRow, Detail, SingleLine, State, TextLeft, Title, CheckStatus, Fail (+4 more)

### Community 216 - "_error_text"
Cohesion: 0.47
Nodes (4): _error_text(), _is_timeout(), _statement_error(), test_statement_error_classification()

### Community 218 - "services/cli_tokens.py"
Cohesion: 0.08
Nodes (30): CliLogin, CliToken, approve_login(), create_login(), deny_login(), list_tokens(), login_by_code(), LoginAction (+22 more)

### Community 219 - "_clean_up_slot"
Cohesion: 0.22
Nodes (5): _clean_up_slot(), _slot_pids(), _fake_proc(), test_clean_up_slot_kills_a_real_process(), test_slot_pids_reads_proc_without_forking()

### Community 220 - "Firestore point-in-time recovery and deletes (as built)"
Cohesion: 0.33
Nodes (6): API, Deletes (Backups tab; typed name), Firestore point-in-time recovery and deletes (as built), MCP, Not verified against real clouds, Point-in-time recovery (Backups tab -> Point-in-time recovery)

### Community 221 - "install_error_handlers"
Cohesion: 0.27
Nodes (6): _body(), install_error_handlers(), _api_error(), _http(), _unhandled(), _validation()

### Community 224 - "Invoke-DeployerNative"
Cohesion: 0.16
Nodes (15): Disable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes(), Get-DeployerLanAddresses(), Get-DeployerLanPorts(), Get-DeployerLanUrls(), Get-DeployerWslIp(), Invoke-DeployerNative() (+7 more)

### Community 229 - "list_jobs"
Cohesion: 0.23
Nodes (4): cancel_job(), get_job(), _get_job(), list_jobs()

### Community 247 - "ci.yml"
Cohesion: 0.17
Nodes (11): concurrency, cancel-in-progress, group, name, permissions, contents, branches, True (+3 more)

### Community 248 - "release.yml"
Cohesion: 0.33
Nodes (5): name, permissions, tags, True, push

### Community 253 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

## Knowledge Gaps
- **145 isolated node(s):** `deployer-api`, `RFC-5987`, `RFC-4180`, `Checking`, `Running` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2552 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `test_github_integration.py`, `source_sync.py`, `oauth.py`, `ApiError`, `get_sessionmaker`, `update_app`, `Device`, `integration/test_query_console.py`, `services/backups.py`, `get_connection`, `rtdb.py`, `test_source_sync.py`, `GcpClient`, `mcp.py`, `services/remote_access.py`, `_client_for`, `test_query_log.py`, `routers/cloud.py`, `provisioning.py`, `User`, `backup_engine.py`, `firestore.py`, `restore_cloud_backup`, `test_cohost_apps.py`, `utcnow`, `dynamo.py`, `App`, `run_mongosh`, `C2-3 as built: Cloud Firestore`, `re`, `routers/backups.py`, `post`, `_Writer`, `SourceReplica`, `ddl_export.py`, `test_backups_pitr.py`, `models.py`, `deployments.py`, `test_devices_management.py`, `get_schema`, `services/cli_inputs.py`, `deployments.py`, `DataSource`, `utcnow`, `test_cli_inputs.py`, `data.py`, `BackupCopy`, `call`, `tests/test_query_console.py`, `run_query`, `_github_delivery`, `services/cli_tokens.py`, `enroll_start`, `install_error_handlers`, `connections.py`, `restore_deleted_project`, `saved_queries.py`, `base64`, `data_sources.py`, `FakeDevice`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Are the 149 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 149 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.07814207650273224 - nodes in this community are weakly interconnected._
- **Why does `WizardForm` connect `WizardForm` to `Ui`, `.TestMarkers`, `ThemedForm`, `utcnow`, `FlatButton`, `.Ask`, `ScriptRunner`, `SetupOptions`, `Core.cs`, `Color`, `CheckRow`, `UninstallForm`, `ControlForm`, `IShellLinkW`, `WizardPage`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `AccountSettingsPage.tsx` be split into smaller, more focused modules?**
  _Cohesion score 0.08725542041248018 - nodes in this community are weakly interconnected._