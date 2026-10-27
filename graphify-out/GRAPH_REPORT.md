# Graph Report - deployer  (2026-10-27)

## Corpus Check
- 520 files · ~645,822 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9645 nodes · 34347 edges · 246 communities (221 shown, 25 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3337 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `3280f203`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- PageSpinner
- Button
- types.ts
- source_sync.py
- oauth.py
- Badge
- ApiError
- update_app
- FlatButton
- Device
- react
- services/backups.py
- App
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
- metrics.py
- ControlForm
- routers/cloud.py
- cloud_deploy.py
- provisioning.py
- test_transfer_devices.py
- firestore.py
- Job
- CloudflareClient
- shell_runner.py
- deployer.sh
- deployments.py
- WizardForm
- ThemedForm
- services/__init__.py
- dynamo.py
- _reconcile_app
- deployer_cli.py
- NotebookConsole.tsx
- react
- project-context.ts
- MCP.md
- README.md
- re
- routers/backups.py
- Backup
- post
- ddl_export.py
- forbidden
- Color
- BackupExecutor
- CONTRIBUTING.md
- models.py
- test_data_browser.py
- Deployer HTTP API v1
- IShellLinkW
- test_github_actions.py
- services/cli_inputs.py
- deployments.py
- cloud_db.py
- test_cli_inputs.py
- common.ps1
- connection
- toast-context.ts
- docker-compose.yml
- environment
- data.py
- InputRequestPage.tsx
- DockerCli
- sqlalchemy
- terminal.ts
- test_firestore_admin.py
- useTerminalConsole.ts
- services
- get_redis
- QueryEditor.tsx
- Deployments (push-to-deploy) — phase 4
- tests/test_query_console.py
- QueryRequest
- test_remote_access.py
- ApiError
- test_oauth.py
- deployer.ps1
- UninstallForm
- caddy
- options
- install.ps1
- DeviceAgent
- export_firestore
- Usability for non-experts
- DumpScanner
- connections.py
- migrate
- BaseModel
- .TestMarkers
- with
- health.py
- EncryptingWriter
- device_local.py
- conventions.py
- DeviceExecutor
- saved_queries.py
- NotebookSidebar.tsx
- docs/ARCHITECTURE.md - Deployer Architecture
- query-shell
- .Ask
- ScriptRunner
- test_repo_detect.py
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- _wrap
- mongo_snapshot
- AwsClient
- query_console.py
- approve_login
- with
- compilerOptions
- test_data_sources.py
- test_rtdb.py
- record
- AppFields
- routers/remote_access.py
- test_backups_engine.py
- test_cli_client.py
- FakeDockerCli
- enqueue
- package.json
- Get-DeployerSource
- mongodb
- compilerOptions
- tunnel
- AuditLog
- worker
- integration/test_query_console.py
- CloudError
- schema_diff.py
- Remote Access & Custom Domains (Cloudflare)
- MarkerKind
- test_transfer_stream.py
- Core.cs
- supervisor.sh
- test_big_mongo_document_is_sent_in_a_batch_of_its_own
- tempfile
- images
- FakeCloudflare
- test_document_tools
- results.ts
- _call_tool
- test_query_log.py
- CliError
- apiSnippets.ts
- HANDOVER.md
- test_conventions.py
- backup_engine.py
- readOnly.ts
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
- cursor
- Deploy a website with Deployer
- images
- SetupOptions
- test_cli_tokens.py
- api
- lan.tests.ps1
- jobs
- How the main code paths work
- healthcheck
- redis
- steps
- WizardPage
- test_backups_pitr.py
- _JsonReader
- re
- .ensure_github_role
- rtdb_read
- utcnow
- mariadb
- mongodb-upgrade-6
- InputCreate
- mongodb-upgrade-8
- test_dead_code.py
- C2-2 as built: DynamoDB
- Invoke-Preflight
- test_sweep_leftovers_removes_stale_partials_and_temp_databases
- x-mongodb-upgrade
- test_query_docs.py
- test_skill_doc.py
- API runtime dependencies (requirements.txt)
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_nat_network_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- create_input
- ThemeProvider.tsx
- Schema endpoints, SchemaLink and ConventionIssue
- csv.ts
- cmd_login
- CheckRow
- test_mysql_canceller_kills_the_query_from_a_private_pool
- .delete_secret
- consoleMode.ts
- services/cli_tokens.py
- _clean_up_slot
- test_managed_db_connection_cap.py
- SqlStore
- tsconfig.json
- Invoke-DeployerNative
- list_subcollections
- runtime.tests.ps1
- _rtdb_source
- docker-entrypoint.sh
- list_jobs
- Data API with API keys
- _TempArtifact
- m_drop
- mongo_read_only_refusal
- signal
- _json_or_text
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

## Communities (246 total, 25 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.08
Nodes (15): SettingsDialog, Autostart, KeepAwake, Lan, Port, InputBox, Invalid, Rule (+7 more)

### Community 1 - "PageSpinner"
Cohesion: 0.07
Nodes (77): isApiError(), isApiStarting(), hasLiveReplica(), useCohostEligibility(), useDataSourcesWithReplicas(), useInstanceSettings(), useProviders(), useSetupStatus() (+69 more)

### Community 2 - "Button"
Cohesion: 0.06
Nodes (151): refresh(), errorMessage(), saveBlob(), isJobFinished(), useApps(), useJob(), usePlacementOptions(), useProjects() (+143 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (155): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+147 more)

### Community 4 - "source_sync.py"
Cohesion: 0.02
Nodes (106): SyncVersion, mark_online(), add_version(), apply_changes(), DeviceSide, _dt(), enc(), enc_row() (+98 more)

### Community 5 - "oauth.py"
Cohesion: 0.03
Nodes (87): random_token(), change_password(), LinkIn, login(), LoginIn, logout(), me(), MeUpdate (+79 more)

### Community 6 - "Badge"
Cohesion: 0.05
Nodes (118): isDeviceOffline(), useApp(), useDeployment(), useDeployments(), useSyncConflict(), useSyncConflicts(), useSyncHistory(), Deployment (+110 more)

### Community 7 - "ApiError"
Cohesion: 0.03
Nodes (95): _detach(), _find_user(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore() (+87 more)

### Community 8 - "update_app"
Cohesion: 0.06
Nodes (47): add_domain(), _audit_cohost(), _audit_database_access(), cancel_deployment(), _check_billing(), check_domain(), _check_internet(), _check_preset() (+39 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (27): CheckOption, CheckColor, Checked, Description, ChoiceCard, Badge, BadgeColor, Checked (+19 more)

### Community 10 - "Device"
Cohesion: 0.03
Nodes (114): AppReplica, Device, DeviceEnrollment, DeviceProjectGrant, SourceReplica, SyncConflict, enroll_cancel(), approve_enrollment() (+106 more)

### Community 11 - "react"
Cohesion: 0.07
Nodes (62): Backup, BackupCopy, BackupSchedule, BackupTrigger, KeptAs, RecoveryWindow, RestoreMode, COPY_ICONS (+54 more)

### Community 12 - "services/backups.py"
Cohesion: 0.05
Nodes (90): validation_error(), BackupCopy, BackupPolicy, new_id(), sha256_file(), any_copy(), archive_source_logs(), _artifact_host() (+82 more)

### Community 13 - "App"
Cohesion: 0.04
Nodes (67): App, Deployment, _switch_target(), cloud_url(), instance_role_name(), out(), set_enabled(), state_of() (+59 more)

### Community 14 - "rtdb.py"
Cohesion: 0.09
Nodes (29): analyze_documents(), _as_doc(), call(), check(), check_key(), check_path(), check_value(), _child() (+21 more)

### Community 15 - "DevicesPage.tsx"
Cohesion: 0.07
Nodes (50): useDevices(), DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability, ManagedEngine, useCurrentUser() (+42 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.20
Nodes (25): Project API keys (dpl_role_random), Platform data model (UUID-keyed MariaDB tables), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), docs/PLATFORMS.md - Platforms and accounts this project uses, AWS hosting and databases, deployer-boundary IAM permissions boundary, Three AWS IAM policies: DeployerHosting, DeployerDatabases, DeployerRoles, Cloudflare tunnel and DNS (+17 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.05
Nodes (84): @xyflow/react@^12.11.6, useSchema(), ConventionIssue, Entity, LinkCardinality, ProjectSchema, RelationshipCardinality, SourceSchema (+76 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.06
Nodes (74): CloudflareZone, CloudProvider, Domain, ProviderSettings, PublicUrlRequest, PublicUrlResponse, RemoteAccess, RemoteAccessMode (+66 more)

### Community 19 - "ApiError"
Cohesion: 0.13
Nodes (20): check_forbidden(), _collection(), decode_input(), delete_document(), encode_value(), find_forbidden_operator(), _find_id(), id_candidates() (+12 more)

### Community 20 - "deploys.ts"
Cohesion: 0.08
Nodes (55): useDataSources(), App, AppDetectDraft, AppPreset, AppTarget, CloudTarget, DeploymentStatus, DeploymentTrigger (+47 more)

### Community 21 - "GcpClient"
Cohesion: 0.04
Nodes (31): CloudError, _api_error(), client(), GcpClient, _name(), _secret_id(), set_transport(), teardown_steps() (+23 more)

### Community 22 - "mcp.py"
Cohesion: 0.10
Nodes (53): _confirmed(), Ctx, _limit(), _mongo(), _p(), _rpc_error(), _sql(), t_app_logs() (+45 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.08
Nodes (47): _add_cloud_domain(), get_value(), set_value(), _active_hostnames(), add_hostname(), apps_tunnel_name(), _cached_zones(), _client() (+39 more)

### Community 24 - "metrics.py"
Cohesion: 0.05
Nodes (55): get_metrics(), get_summary(), list_alerts(), active(), _api_rule(), _cloud_cleanup_rule(), Condition, conditions() (+47 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (19): ControlForm, IsBusy, State, RunState, Busy, Checking, NotResponding, Running (+11 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.10
Nodes (32): _audit(), _billing(), check_connection(), _confirm_delete(), connect_database(), connection_databases(), create_connection(), create_database() (+24 more)

### Community 27 - "cloud_deploy.py"
Cohesion: 0.04
Nodes (49): cache_control(), cloud_env(), _export(), Publish, poll(), poll(), poll(), cleanup() (+41 more)

### Community 28 - "provisioning.py"
Cohesion: 0.08
Nodes (38): ensure_database(), database_size(), m_provision(), provision_target(), cap_mariadb_users(), _check(), _check_db(), create_mariadb_database() (+30 more)

### Community 29 - "test_transfer_devices.py"
Cohesion: 0.22
Nodes (14): _export_handler(), handler(), fake_provision(), provision_managed_source(), _payload(), test_export_fails_when_device_offline(), test_instance_export_includes_device_tables_and_device_data(), test_instance_import_offline_device_restores_on_main() (+6 more)

### Community 30 - "firestore.py"
Cohesion: 0.08
Nodes (42): _and(), _bad(), call(), check(), check_path(), collection_entity(), collection_ids(), _count() (+34 more)

### Community 31 - "Job"
Cohesion: 0.05
Nodes (44): Job, cancel_job(), reconcile_interrupted(), cancel_deployment(), claim(), _clamp(), finish(), heartbeat() (+36 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.07
Nodes (17): CloudflareClient, CloudflareError, _cname_body(), to_api_error(), tunnel_cname_target(), test_bearer_header_and_verify(), test_check_permissions_all_ok(), test_check_permissions_missing() (+9 more)

### Community 33 - "shell_runner.py"
Cohesion: 0.09
Nodes (15): _as_uid(), _child_env(), _field(), _kill(), main(), make_server(), do_POST(), _reply() (+7 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "deployments.py"
Cohesion: 0.02
Nodes (97): get_settings(), seal_process(), Settings, _b64d(), _b64e(), decrypt_with_passphrase(), _derive(), encrypt_secret() (+89 more)

### Community 36 - "WizardForm"
Cohesion: 0.11
Nodes (12): Card, BorderColor, Fill, Radius, TextBlock, RightAlign, SingleLine, TextColor (+4 more)

### Community 37 - "ThemedForm"
Cohesion: 0.13
Nodes (4): AppIcon, ThemedForm, IsForcedScale, ResetPasswordDialog

### Community 38 - "services/__init__.py"
Cohesion: 0.02
Nodes (101): sha256_hex(), api_key_not_allowed(), bearer_token(), check_api_key_rate(), client_ip(), decode_access_token(), get_current_user(), load_api_key_access() (+93 more)

### Community 39 - "dynamo.py"
Cohesion: 0.10
Nodes (42): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), create_backups(), _cursor_in() (+34 more)

### Community 40 - "_reconcile_app"
Cohesion: 0.03
Nodes (51): github_disconnect(), github_repos(), github_status(), enqueue_teardown(), artifact_for(), cancel_setup(), check_can_build(), dispatch() (+43 more)

### Community 41 - "deployer_cli.py"
Cohesion: 0.14
Nodes (23): api_from_config(), app_path(), _app_status(), _apply_hint(), ask_secret(), cmd_app_show(), human(), cmd_apps() (+15 more)

### Community 42 - "NotebookConsole.tsx"
Cohesion: 0.12
Nodes (47): useSourceSchema(), SavedQuery, newId(), attachSaved(), CELL_PERSIST_MAX, closeTab(), detachSaved(), EMPTY_NOTEBOOK (+39 more)

### Community 43 - "react"
Cohesion: 0.07
Nodes (66): api, qk, invalidateProjectSources(), CloudDatabaseOptions, ColumnSpec, DataSource, DataSourceKind, ForeignKeyAction (+58 more)

### Community 44 - "project-context.ts"
Cohesion: 0.06
Nodes (43): useProject(), CloudRestoredFrom, Role, { api }, flush(), info, render(), source (+35 more)

### Community 45 - "MCP.md"
Cohesion: 0.10
Nodes (47): CI job: Linux installer (install, CLI, update, uninstall), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits, Per-project MCP server (POST /v1/projects/<id>/mcp), MCP server for AI agents (+39 more)

### Community 46 - "README.md"
Cohesion: 0.06
Nodes (58): Linux support work: install.sh, deployer.sh, linux-installer CI, Docker Engine inside the deployer WSL distro (default runtime), Linux server platform (alternative to Windows PC), Windows PC platform (required unless Linux), docs/SETUP.md - Setting up Deployer, Cloudflare API token permissions (Tunnel Edit, Account Settings Read, DNS Edit, Zone Read), Open from any device with your own domain (Cloudflare tunnel), Deploy an app and connect an AI agent (MCP) (+50 more)

### Community 47 - "re"
Cohesion: 0.05
Nodes (68): DataSource, backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids() (+60 more)

### Community 48 - "routers/backups.py"
Cohesion: 0.10
Nodes (33): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+25 more)

### Community 49 - "Backup"
Cohesion: 0.10
Nodes (30): Backup, BackupLogSegment, _bucket_keys(), contiguous(), _covers(), covers_anchor(), expire_project_backups(), _follows() (+22 more)

### Community 50 - "post"
Cohesion: 0.06
Nodes (35): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job(), _owned_projects() (+27 more)

### Community 51 - "ddl_export.py"
Cohesion: 0.08
Nodes (33): build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources(), export_sql_source() (+25 more)

### Community 52 - "forbidden"
Cohesion: 0.07
Nodes (23): role_rank(), keys_to_rotate(), accept_invite(), create_invite(), get_invite(), _get_member(), InviteCreate, list_invites() (+15 more)

### Community 53 - "Color"
Cohesion: 0.07
Nodes (25): Logo, Glyphs, IconBadge, Color, Kind, Soft, IconKind, Check (+17 more)

### Community 54 - "BackupExecutor"
Cohesion: 0.05
Nodes (10): register_copy_target(), unregister(), BackupExecutor, DeviceExecutorUnavailable, local_executor(), register_device_executor_factory(), run_local_call(), test_copy_hook() (+2 more)

### Community 55 - "CONTRIBUTING.md"
Cohesion: 0.15
Nodes (14): CI job: Windows installer checks and DeployerSetup.exe, Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Ground rules, Layout (+6 more)

### Community 56 - "models.py"
Cohesion: 0.03
Nodes (117): decrypt_json(), decrypt_secret(), Base, ApiKey, CloudConnection, InstanceSetting, Project, ProjectInvite (+109 more)

### Community 57 - "test_data_browser.py"
Cohesion: 0.17
Nodes (20): _coerce_for_column(), _db_error(), delete_row(), _fetch_by_pk(), insert_row(), list_rows(), _pk_clause(), _pk_columns() (+12 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.11
Nodes (36): Data sources endpoints and DataSourceInput, Error envelope and common error codes, Health and setup endpoints, Backups, Versions & Recovery, Backups API, Backup data model (jobs, backup_policies, backups, segments, copies), Backup storage and encryption (chunked AES-256-GCM, HKDF), Backups error codes (+28 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.09
Nodes (5): IShellLinkW, ShellLinkCoClass, MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "test_github_actions.py"
Cohesion: 0.13
Nodes (32): role_name(), role_name_for(), workflow_path(), aws(), by_run(), cloud_app(), committed(), connect_github() (+24 more)

### Community 61 - "services/cli_inputs.py"
Cohesion: 0.10
Nodes (24): CliInput, get_input(), submit_input(), apps_out(), cancel(), cancel_for_token(), check_pending(), clean_values() (+16 more)

### Community 62 - "deployments.py"
Cohesion: 0.04
Nodes (72): _kill(), _watch(), _job_archive(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify() (+64 more)

### Community 63 - "cloud_db.py"
Cohesion: 0.07
Nodes (30): encrypt_json(), app_databases(), _cloud_call(), cloud_out(), connect(), connect_firestore(), connect_rtdb(), connect_tables() (+22 more)

### Community 64 - "test_cli_inputs.py"
Cohesion: 0.15
Nodes (28): _check_env(), reserved_env(), bearer(), _create(), _issue(), _poll(), _submit(), test_app_ids_need_developer() (+20 more)

### Community 65 - "common.ps1"
Cohesion: 0.07
Nodes (45): Invoke-Update(), Get-SystemFacts(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerArgument(), ConvertTo-DeployerRuntimePath(), ConvertTo-DeployerStateTable() (+37 more)

### Community 66 - "connection"
Cohesion: 0.03
Nodes (104): set_factory(), aws_statements(), resource_name(), site_id(), set_factory(), aws(), aws_key_id(), aws_secret() (+96 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.03
Nodes (75): ApiClientOptions, ApiError, buildQuery(), client, codeForStatus(), createApiClient(), download(), emit() (+67 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.10
Nodes (38): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, Checks to run before opening a PR (CI runs the same) (+30 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.23
Nodes (14): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _mongo_source(), RowDelete (+6 more)

### Community 71 - "InputRequestPage.tsx"
Cohesion: 0.10
Nodes (37): CliInputField, JsonValue, Textarea, childPath(), cleanRtdbPath(), isBranch(), isRtdbKey(), parentPath() (+29 more)

### Community 72 - "DockerCli"
Cohesion: 0.04
Nodes (35): DockerCli, on(), DockerError, _git_env(), parse_size(), _percent(), build_image(), _docker_failure() (+27 more)

### Community 73 - "sqlalchemy"
Cohesion: 0.06
Nodes (28): run_migrations_offline(), run_migrations_online(), _url(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+20 more)

### Community 74 - "terminal.ts"
Cohesion: 0.15
Nodes (33): MongoQueryResponse, SqlStatementResult, QueryPrefs, docsToTable(), outputLines(), statementLabel(), asciiTable(), bracketsBalanced() (+25 more)

### Community 75 - "test_firestore_admin.py"
Cohesion: 0.06
Nodes (45): requirements(), _size(), test_every_policy_leaves_room_under_the_iam_limit(), test_split_kept_exactly_the_previous_permissions(), base(), connected(), FakeAdmin, gcp() (+37 more)

### Community 76 - "useTerminalConsole.ts"
Cohesion: 0.14
Nodes (29): QueryRequest, addHistoryEntry(), HISTORY_LIMIT, HistoryEntry, historyKey(), isEntry(), loadHistory(), DEFAULT_PREFS (+21 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "get_redis"
Cohesion: 0.03
Nodes (82): get_redis(), download_transfer(), iterate(), dismiss_alert(), alert_out(), mute(), read_status(), write_status() (+74 more)

### Community 79 - "QueryEditor.tsx"
Cohesion: 0.07
Nodes (37): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+29 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.12
Nodes (22): provider(), static(), target(), local(), API, API, C1 as built, Cloud connections (+14 more)

### Community 81 - "tests/test_query_console.py"
Cohesion: 0.09
Nodes (28): run_sql(), _timeout_statement(), mongo_config(), run_fake(), test_mongosh_cursor_batch_and_truncation(), test_mongosh_errors_are_in_band(), test_mongosh_missing_in_sidecar_or_sidecar_down(), test_mongosh_node_escapes_refused_for_developers() (+20 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.08
Nodes (39): Domain, fix_state_ownership(), test_apps_tunnel_created_once_cname_moves_and_ingress(), add_host(), assert_no_secrets(), desired(), link(), test_add_hostname_dns_failure_rolls_back_ingress() (+31 more)

### Community 84 - "ApiError"
Cohesion: 0.04
Nodes (67): ApiError, _actions_report(), _github_delivery(), github_webhook(), _lookup_rate_limit(), snooze_alert(), SnoozeBody, test_webhook() (+59 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.16
Nodes (21): auth_payload(), create_access_token(), factory(), _callback(), _error_of(), _link_state(), _start(), test_callback_invalid_or_reused_state() (+13 more)

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
Nodes (12): _connector(), _describe(), DeviceAgent, run_agent(), _send(), ws_url(), error_payload(), main() (+4 more)

### Community 92 - "export_firestore"
Cohesion: 0.22
Nodes (3): database_options(), export_firestore(), options()

### Community 93 - "Usability for non-experts"
Cohesion: 0.06
Nodes (33): _outcome(), 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 3. Query console, query log, saved queries, 4. Backups, PITR, jobs, worker, export/import (+25 more)

### Community 94 - "DumpScanner"
Cohesion: 0.19
Nodes (9): count_insert_rows(), _count_row_tuples(), DumpScanner, test_count_insert_rows_ignores_parens_inside_strings(), test_dump_scanner_collects_point_and_counts(), _scan(), test_count_insert_rows_first_line_only(), test_multi_line_extended_insert_as_written_by_mariadb_11() (+1 more)

### Community 95 - "connections.py"
Cohesion: 0.04
Nodes (61): build_mongo_client(), build_sql_engine(), check_status(), cloud_engine(), _connect_args(), connection_info(), display_for(), _fingerprint() (+53 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "BaseModel"
Cohesion: 0.14
Nodes (11): AwsCredentials, CloudDatabaseConnect, CloudDatabaseCreate, ConnectionCreate, FirebaseCredentials, FirestoreClone, FirestoreExport, FirestoreImport (+3 more)

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (7): CheckResult, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "health.py"
Cohesion: 0.08
Nodes (17): get_engine(), _body(), install_error_handlers(), _api_error(), _http(), _unhandled(), _validation(), create_app() (+9 more)

### Community 101 - "EncryptingWriter"
Cohesion: 0.05
Nodes (35): body(), backup_key(), BackupCryptoError, DecryptingReader, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf() (+27 more)

### Community 102 - "device_local.py"
Cohesion: 0.10
Nodes (20): device_status(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to(), _load_state() (+12 more)

### Community 103 - "conventions.py"
Cohesion: 0.11
Nodes (25): check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural(), _issue() (+17 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.11
Nodes (27): SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query() (+19 more)

### Community 106 - "NotebookSidebar.tsx"
Cohesion: 0.14
Nodes (27): useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), ModeSwitch(), PendingWriteAlert(), ReadOnlyBadge(), RowsSelect() (+19 more)

### Community 107 - "docs/ARCHITECTURE.md - Deployer Architecture"
Cohesion: 0.11
Nodes (21): Deployer HTTP API v1, Auth endpoints (signup, login, refresh, OAuth), Export and import endpoints, Members and invites endpoints, OAuth callback redirect flow, Projects endpoints, Role hierarchy viewer<developer<admin<owner, docs/ARCHITECTURE.md - Deployer Architecture (+13 more)

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
Cohesion: 0.07
Nodes (7): aws(), FakeDynamo, _missing(), aws(), PitrFake, test_retried_delete_skips_the_protection_switch(), viewer()

### Community 113 - "Query Console"
Cohesion: 0.13
Nodes (25): Data browser (SQL rows, MongoDB documents), Query Console, Query API endpoint, query.run audit event, Concurrency, timeout and output limits, Dashboard Query tab, CodeMirror editor and toolbar, In-band query errors vs HTTP errors (+17 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (3): Register-DeployerTask(), ConvertTo-DeployerWslPath(), Register-ScheduledTask()

### Community 115 - "_wrap"
Cohesion: 0.08
Nodes (3): _code(), _wrap(), inner()

### Community 116 - "mongo_snapshot"
Cohesion: 0.14
Nodes (12): ArtifactWriter, _latest_oplog_ts(), mariadb_snapshot(), mongo_archive_logs(), mongo_snapshot(), _oldest_oplog_ts(), _oplog_available(), ts_from() (+4 more)

### Community 118 - "query_console.py"
Cohesion: 0.13
Nodes (15): _enter_read_only(), _error_text(), _first_keyword(), _is_blank(), _is_timeout(), _leading_keyword(), _ms(), _names_re() (+7 more)

### Community 119 - "approve_login"
Cohesion: 0.19
Nodes (13): approve_login(), create_login(), deny_login(), list_tokens(), login_by_code(), LoginAction, LoginCreate, LoginPoll (+5 more)

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "test_data_sources.py"
Cohesion: 0.08
Nodes (11): fake_connect(), project_setup(), sqlite_engine(), test_check_connection_and_delete(), test_create_external_sql_source(), test_deleting_source_removes_links(), test_internal_network_is_refused_for_non_owners(), test_managed_create_drops_database_when_commit_fails() (+3 more)

### Community 123 - "test_rtdb.py"
Cohesion: 0.11
Nodes (19): base(), connect(), _fail(), FakeRtdb, by(), gcp(), test_browse_lazily_query_and_write_by_path(), test_cloud_run_app_gets_its_realtime_database() (+11 more)

### Community 124 - "record"
Cohesion: 0.05
Nodes (48): cohosting_eligibility(), create_replica(), delete_replica(), get_conflict(), _key_param(), list_conflicts(), list_replicas(), _replica() (+40 more)

### Community 125 - "AppFields"
Cohesion: 0.12
Nodes (10): AppCreate, AppFields, AppUpdate, BuildBody, DeployBody, DetectBody, HostnameBody, _one_line() (+2 more)

### Community 126 - "routers/remote_access.py"
Cohesion: 0.20
Nodes (15): add_hostname(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, quick(), QuickBody (+7 more)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.10
Nodes (15): binlog_name_with_seq(), binlog_seq(), feed(), _mongo_build_oplog(), parse_binlog(), parse_mongodump_counts(), rename_oplog_entry(), rewrite_dump_line() (+7 more)

### Community 128 - "test_cli_client.py"
Cohesion: 0.07
Nodes (39): _merge_env(), env_of(), make_app(), env(), cli(), urlopen(), _fail_on(), _fill() (+31 more)

### Community 130 - "enqueue"
Cohesion: 0.10
Nodes (13): detached_source_params(), enqueue_detached_finalize(), _redis_due(), scheduler_tick(), soft_delete_source(), start_platform_snapshot(), device_removed(), active_job() (+5 more)

### Community 131 - "package.json"
Cohesion: 0.06
Nodes (43): devDependencies, eslint@^10.10.0, @eslint/js@^10.0.1, eslint-plugin-react-hooks@^7.1.1, eslint-plugin-react-refresh@^0.5.7, globals@^17.12.0, jsdom@^30.0.1, tailwindcss@^4.3.3 (+35 more)

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

### Community 136 - "AuditLog"
Cohesion: 0.03
Nodes (57): CaddyProxyHeaders, AuditLog, create_invite(), reset_logins(), create(), env(), sign(), test_app_hostnames() (+49 more)

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "integration/test_query_console.py"
Cohesion: 0.15
Nodes (19): mariadb(), mongo(), run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results(), test_mariadb_multi_statement_script(), test_mariadb_read_only_session(), test_mariadb_session_state_does_not_leak() (+11 more)

### Community 139 - "CloudError"
Cohesion: 0.17
Nodes (6): free_blocks(), _nat_alive(), _ours(), _public_subnet(), test_nat_helpers(), What the deploy makes (`cloud_deploy.Publish.nat_connector`, `cloud_aws.ensure_nat_network`)

### Community 140 - "schema_diff.py"
Cohesion: 0.22
Nodes (13): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), entity(), field() (+5 more)

### Community 141 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.23
Nodes (18): Instance settings and users endpoints, Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes (+10 more)

### Community 142 - "MarkerKind"
Cohesion: 0.17
Nodes (11): Marker, MarkerKind, Check, Done, Error, None, Other, RebootRequired (+3 more)

### Community 143 - "test_transfer_stream.py"
Cohesion: 0.13
Nodes (11): read_data_entry(), _stream_parts(), _dump(), fake_engine(), FakeConn, materialize(), test_bare_numbers_cut_by_the_buffer(), test_lazy_entry_matches_json_load() (+3 more)

### Community 144 - "Core.cs"
Cohesion: 0.15
Nodes (4): DeployerSetup, DeployerCli, Internet, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 146 - "test_big_mongo_document_is_sent_in_a_batch_of_its_own"
Cohesion: 0.22
Nodes (3): _dumps_token(), read_mongo_changes(), test_big_mongo_document_is_sent_in_a_batch_of_its_own()

### Community 147 - "tempfile"
Cohesion: 0.09
Nodes (26): BackupEngineError, _check_exit(), _fetch_binlog(), _index_path(), _load_index(), mariadb_archive_logs(), mariadb_defaults_file(), mongo_config_file() (+18 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "FakeCloudflare"
Cohesion: 0.14
Nodes (5): set_transport(), _err(), fake_cf(), FakeCloudflare, _ok()

### Community 150 - "test_document_tools"
Cohesion: 0.50
Nodes (4): run(), test_document_tools(), recorder(), fn()

### Community 151 - "results.ts"
Cohesion: 0.19
Nodes (18): QueryResponse, SqlQueryResponse, addPrimaryKeyQuery(), base64Size(), CellKind, describeQueryError(), ejsonLeaf(), expandedCellText() (+10 more)

### Community 152 - "_call_tool"
Cohesion: 0.14
Nodes (9): _call_tool(), _check_args(), _dispatch(), _error_result(), handle(), mcp_endpoint(), RpcError, _text_result() (+1 more)

### Community 153 - "test_query_log.py"
Cohesion: 0.05
Nodes (34): QueryRun, delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), delete_before(), get_run(), list_runs() (+26 more)

### Community 154 - "CliError"
Cohesion: 0.19
Nodes (11): all_apps(), Api, ask_web(), _cancel_input(), CliError, cmd_app_create(), cmd_ask(), find_app() (+3 more)

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.09
Nodes (30): Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Notes for AI agents (skill copy, MCP, graphify), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09), For AI agents (+22 more)

### Community 157 - "test_conventions.py"
Cohesion: 0.44
Nodes (17): check_conventions(), entity(), field(), _link(), mongo_source(), rules(), sql_source(), test_errored_sources_are_skipped() (+9 more)

### Community 158 - "backup_engine.py"
Cohesion: 0.13
Nodes (33): check_db_name(), compare_counts(), ensure_mongo_replica_set(), _load_dump(), _managed_user_for(), _mariadb_clear(), _mariadb_create_db(), mariadb_current_point() (+25 more)

### Community 159 - "readOnly.ts"
Cohesion: 0.35
Nodes (9): checkMongoReadOnly(), checkReadOnly(), checkSqlReadOnly(), firstKeyword(), MONGO_WRITE_NAMES, MONGO_WRITE_RE, ReadOnlyCheck, splitSqlStatements() (+1 more)

### Community 160 - "error"
Cohesion: 0.07
Nodes (24): error(), fake_primary(), FakePrimary, test_enrollment_poll_never_overwrites_a_cancel(), cancelled_meanwhile(), test_enrollment_poll_race_keeps_approved(), slow_primary(), primary() (+16 more)

### Community 161 - "restore_cloud_backup"
Cohesion: 0.17
Nodes (12): CloudBackupCreate, CloudRestore, create_cloud_backup(), _dynamo_source(), list_cloud_backups(), PitrUpdate, restore_cloud_backup(), set_point_in_time_recovery() (+4 more)

### Community 163 - "services"
Cohesion: 0.18
Nodes (10): command, volumes, volumes, volumes, services, api, migrate, query-shell (+2 more)

### Community 164 - "test_container_config.py"
Cohesion: 0.24
Nodes (7): read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through(), test_migrations_run_to_completion_before_the_api_starts(), test_query_shell_sidecar_holds_no_secrets(), test_security_headers_are_set_by_caddy_not_nginx(), test_untrusted_containers_share_no_network_with_the_api()

### Community 165 - "query/diff.ts"
Cohesion: 0.43
Nodes (6): DIFF_MAX_LINES, DiffLine, diffStats(), lineDiff(), lines(), render()

### Community 166 - "run_mongosh"
Cohesion: 0.15
Nodes (11): _call_shell(), _clamp(), _connect_uri(), _first_line(), parse_shell_output(), run_mongosh(), _shell_error_message(), test_connect_uri_adds_timeouts_once() (+3 more)

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

### Community 171 - "cursor"
Cohesion: 0.15
Nodes (14): cursor(), Browsing, editing, querying, Browsing, editing, querying, C2-5 as built: MCP, transfer, project delete, Data tools on cloud databases, Deleting a project, MCP: every tool needs at least its REST route's role, Not verified against real clouds (+6 more)

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

### Community 179 - "How the main code paths work"
Cohesion: 0.12
Nodes (11): _Watchdog, 1. Signing in, 3. Running a query in the console or notebook, 7. Deploying to the cloud, 8. Installing, updating and staying up, `deployer update`, How the main code paths work, Keeping the session alive (refresh rotation) (+3 more)

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
Cohesion: 0.36
Nodes (11): invalidate(), _iso(), _pause(), _restore(), _run_all(), _snapshot(), _source(), _t_between() (+3 more)

### Community 186 - "re"
Cohesion: 0.06
Nodes (18): _slug_filename(), _documented(), _norm(), _paths(), _routes(), test_documented_endpoints_exist(), _create(), test_api_key_lifecycle() (+10 more)

### Community 187 - ".ensure_github_role"
Cohesion: 0.20
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

### Community 188 - "rtdb_read"
Cohesion: 0.30
Nodes (3): list_documents(), list_rows(), rtdb_read()

### Community 189 - "utcnow"
Cohesion: 0.06
Nodes (46): utcnow(), _backup_rules(), prune_all(), run_queued(), test_deploy_cancel_rollback_and_delete(), _iso(), _snapshot(), test_archive_logs_creates_and_extends_segments() (+38 more)

### Community 190 - "mariadb"
Cohesion: 0.29
Nodes (7): command, image, mem_limit, networks, restart, volumes, mariadb

### Community 191 - "mongodb-upgrade-6"
Cohesion: 0.29
Nodes (7): entrypoint, image, mem_limit, network_mode, profiles, volumes, mongodb-upgrade-6

### Community 192 - "InputCreate"
Cohesion: 0.24
Nodes (3): InputCreate, InputField, InputSubmit

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

### Community 201 - "API runtime dependencies (requirements.txt)"
Cohesion: 0.20
Nodes (12): API runtime dependencies (requirements.txt), alembic, argon2-cffi (password hashing), cryptography, API dev and test dependencies (requirements-dev.txt), fakeredis, pytest, ruff (+4 more)

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
Nodes (10): nat_name(), _unless_gone(), test_ensure_vpc_connector_runs_against_the_real_botocore_models(), test_nat_network_runs_against_the_real_botocore_models(), subnet(), API, MCP, dashboard, C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway), Not verified against real clouds (+2 more)

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 209 - "create_input"
Cohesion: 0.46
Nodes (4): cancel_input(), _cli_row(), create_input(), poll_input()

### Community 210 - "ThemeProvider.tsx"
Cohesion: 0.26
Nodes (9): labels, next, initialMode(), subscribe(), ThemeProvider(), THEME_STORAGE_KEY, ThemeContext, ThemeContextValue (+1 more)

### Community 211 - "Schema endpoints, SchemaLink and ConventionIssue"
Cohesion: 0.44
Nodes (8): Schema endpoints, SchemaLink and ConventionIssue, Database Planning Conventions, Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle), ERD crow's-foot notation, Naming rules N1-N6, Structure rules S1-S8

### Community 212 - "csv.ts"
Cohesion: 0.30
Nodes (10): BOM, Cell, csvField(), exportCsv(), exportFilename(), exportJson(), ExportTable, rowsToObjects() (+2 more)

### Community 213 - "cmd_login"
Cohesion: 0.27
Nodes (8): cmd_login(), cmd_logout(), config_path(), _home(), load_config(), local_url(), _login_local(), save_config()

### Community 214 - "CheckRow"
Cohesion: 0.17
Nodes (12): CheckRow, Detail, SingleLine, State, TextLeft, Title, CheckStatus, Fail (+4 more)

### Community 217 - "consoleMode.ts"
Cohesion: 0.33
Nodes (9): DEFAULT_QUERY_CONSOLE_MODE, listeners, loadQueryConsoleMode(), QUERY_CONSOLE_MODE_KEY, QUERY_CONSOLE_MODES, QueryConsoleMode, saveQueryConsoleMode(), subscribe() (+1 more)

### Community 218 - "services/cli_tokens.py"
Cohesion: 0.12
Nodes (19): CliLogin, CliToken, approve(), authenticate(), _clean(), create_login(), expire_if_needed(), issue_token() (+11 more)

### Community 219 - "_clean_up_slot"
Cohesion: 0.22
Nodes (5): _clean_up_slot(), _slot_pids(), _fake_proc(), test_clean_up_slot_kills_a_real_process(), test_slot_pids_reads_proc_without_forking()

### Community 220 - "test_managed_db_connection_cap.py"
Cohesion: 0.29
Nodes (4): FakeConn, _patch_engine(), test_existing_managed_users_are_capped_and_others_left_alone(), test_new_managed_user_is_created_with_the_cap()

### Community 221 - "SqlStore"
Cohesion: 0.06
Nodes (19): m_sync_mongo_apply(), m_sync_mongo_changes(), m_sync_position(), m_sync_sql_apply(), m_sync_sql_changes(), _sync_database(), _sync_limit(), _sync_offset() (+11 more)

### Community 224 - "Invoke-DeployerNative"
Cohesion: 0.16
Nodes (15): Disable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes(), Get-DeployerLanAddresses(), Get-DeployerLanPorts(), Get-DeployerLanUrls(), Get-DeployerWslIp(), Invoke-DeployerNative() (+7 more)

### Community 225 - "list_subcollections"
Cohesion: 0.22
Nodes (8): list_subcollections(), Add database -> In your Firebase project, Apps on Cloud Run, C2-3 as built: Cloud Firestore, Data model, MCP, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide)

### Community 227 - "_rtdb_source"
Cohesion: 0.28
Nodes (5): rtdb_push(), rtdb_set(), _rtdb_source(), rtdb_update(), RtdbWrite

### Community 229 - "list_jobs"
Cohesion: 0.31
Nodes (3): get_job(), _get_job(), list_jobs()

### Community 230 - "Data API with API keys"
Cohesion: 0.22
Nodes (9): rows(), Calling from a browser, Config file, Data API with API keys, Queries, Rotating a key, Rows (SQL sources), Schema (+1 more)

### Community 232 - "m_drop"
Cohesion: 0.48
Nodes (6): hosted_summary(), load_credentials(), _load_json_setting(), m_drop(), save_credentials(), servers()

### Community 233 - "mongo_read_only_refusal"
Cohesion: 0.33
Nodes (5): mongo_read_only_refusal(), test_mongo_read_only_accepts(), test_mongo_read_only_refuses(), test_read_only_refusals_name_the_word(), test_sql_read_only_accepts()

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
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2551 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `test_cli_client.py`, `source_sync.py`, `oauth.py`, `ApiError`, `update_app`, `AuditLog`, `Device`, `integration/test_query_console.py`, `services/backups.py`, `App`, `rtdb.py`, `test_big_mongo_document_is_sent_in_a_batch_of_its_own`, `ApiError`, `GcpClient`, `mcp.py`, `services/remote_access.py`, `_call_tool`, `metrics.py`, `routers/cloud.py`, `test_query_log.py`, `provisioning.py`, `test_transfer_devices.py`, `backup_engine.py`, `firestore.py`, `CloudflareClient`, `restore_cloud_backup`, `deployments.py`, `services/__init__.py`, `dynamo.py`, `_reconcile_app`, `run_mongosh`, `re`, `routers/backups.py`, `post`, `forbidden`, `models.py`, `test_data_browser.py`, `services/cli_inputs.py`, `deployments.py`, `cloud_db.py`, `utcnow`, `test_cli_inputs.py`, `data.py`, `get_redis`, `create_input`, `tests/test_query_console.py`, `services/cli_tokens.py`, `DeviceAgent`, `export_firestore`, `SqlStore`, `Usability for non-experts`, `connections.py`, `list_subcollections`, `_rtdb_source`, `device_local.py`, `m_drop`, `saved_queries.py`, `query_console.py`, `approve_login`, `record`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Are the 149 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 149 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.07814207650273224 - nodes in this community are weakly interconnected._
- **Why does `WizardForm` connect `WizardForm` to `Ui`, `.TestMarkers`, `ThemedForm`, `services/__init__.py`, `FlatButton`, `.Ask`, `ScriptRunner`, `SetupOptions`, `Core.cs`, `Color`, `CheckRow`, `UninstallForm`, `ControlForm`, `IShellLinkW`, `WizardPage`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `PageSpinner` be split into smaller, more focused modules?**
  _Cohesion score 0.0660941000746826 - nodes in this community are weakly interconnected._