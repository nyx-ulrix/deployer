# Graph Report - deployer  (2026-10-29)

## Corpus Check
- 521 files · ~646,376 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9671 nodes · 34499 edges · 253 communities (228 shown, 25 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3373 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4172ca7f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- react
- Button
- types.ts
- App
- oauth.py
- Badge
- device_host.py
- test_source_sync.py
- FlatButton
- Device
- routers/transfer.py
- ProjectMember
- services/cli_tokens.py
- rtdb.py
- BackupsTab.tsx
- docs/PLATFORMS.md - Platforms and accounts this project uses
- SchemaTab.tsx
- CloudflareSetup.tsx
- SourceReplica
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
- client.ts
- executors.py
- dynamo.py
- github_actions.py
- deployer_cli.py
- NotebookConsole.tsx
- firestore_admin.py
- source_ops.py
- MCP.md
- README.md
- connections.py
- record
- services/backups.py
- json.ts
- ddl_export.py
- source_sync.py
- .RenderChildren
- BackupExecutor
- refresh_pc_ips
- services/transfer.py
- get_redis
- Deployer HTTP API v1
- IShellLinkW
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
- json.ts
- test_cohosting_api.py
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
- device_local.py
- get_schema
- get_source
- DumpScanner
- dependencies
- migrate
- DecryptingReader
- .TestMarkers
- with
- test_data_sources.py
- test_backup_crypto.py
- delete
- conventions.py
- ApiError
- saved_queries.py
- threading
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
- test_device_rpc.py
- _json_or_text
- with
- compilerOptions
- DataSource
- FakeRtdb
- data_sources.py
- test_jobs.py
- write
- test_backups_engine.py
- test_cli_client.py
- test_github_integration.py
- test_backups_pitr.py
- devDependencies
- Get-DeployerSource
- mongodb
- compilerOptions
- tunnel
- device_executor.py
- worker
- integration/test_query_console.py
- connection
- schema_diff.py
- test_cli_tokens.py
- MarkerKind
- docs/ARCHITECTURE.md - Deployer Architecture
- Core.cs
- supervisor.sh
- BackupPolicy
- mongo_snapshot
- images
- FakeCloudflare
- test_mcp.py
- cli
- sample
- Remote Access & Custom Domains (Cloudflare)
- test_transfer_devices.py
- apiSnippets.ts
- HANDOVER.md
- active
- backup_engine.py
- introspection.py
- services/devices.py
- CheckRow
- LocalExecutor
- services
- test_container_config.py
- request_cancel
- list_query_log
- wslplatform.tests.ps1
- .stats
- steps
- bundle
- _JsonReader
- validate
- images
- SetupOptions
- By section
- api
- lan.tests.ps1
- jobs
- Schema endpoints, SchemaLink and ConventionIssue
- healthcheck
- redis
- steps
- WizardPage
- test_projects.py
- test_transfer_stream.py
- models.py
- ScriptRunner
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
- eslint.config.js
- pathlib
- Deployer audit - 2026-09-28
- test_webhook
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_nat_network_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- CloudflareError
- Usability for non-experts
- test_devices_enrollment.py
- scripts
- package.json
- .__getattr__
- create_input
- DeviceSide
- error
- User
- shared_fixtures.py
- test_data_api_keys.py
- install_error_handlers
- tsconfig.json
- test_release_workflow.py
- Invoke-DeployerNative
- query/diff.ts
- install.ps1
- RequestMetricsMiddleware
- docker-entrypoint.sh
- test_big_mongo_document_is_sent_in_a_batch_of_its_own
- vite.config.ts
- run_query
- .set_aliases
- API runtime dependencies (requirements.txt)
- test_auto_increment_is_persisted_for_restarts_and_repaired_with_a_log
- test_devices_local.py
- repoLinks.ts
- entrypoint.sh
- upgrade.sh
- ensure_mongo_replica_set
- test_export_temp_file_deleted_when_client_is_gone
- fix_state_ownership
- Data API with API keys
- test_cli_provider_tools.py
- ci.yml
- release.yml
- deployer-api
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

## Communities (253 total, 25 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.08
Nodes (15): SettingsDialog, Autostart, KeepAwake, Lan, Port, InputBox, Invalid, Rule (+7 more)

### Community 1 - "react"
Cohesion: 0.06
Nodes (78): api, qk, invalidateProjectSources(), isJobFinished(), useJob(), CloudDatabaseOptions, DataSource, Entity (+70 more)

### Community 2 - "Button"
Cohesion: 0.06
Nodes (156): refresh(), errorMessage(), isApiError(), useProjects(), FirestoreBackup, useCurrentUser(), Avatar(), GitHubIcon() (+148 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (133): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+125 more)

### Community 4 - "App"
Cohesion: 0.03
Nodes (99): ProjectAccess, forbidden(), App, Domain, _actions_report(), _add_cloud_domain(), add_domain(), AppCreate (+91 more)

### Community 5 - "oauth.py"
Cohesion: 0.03
Nodes (90): _find_user(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore(), _read_json_stdin() (+82 more)

### Community 6 - "Badge"
Cohesion: 0.06
Nodes (106): useDevices(), useSyncConflict(), useSyncConflicts(), useSyncHistory(), CohostEligibility, Replica, SyncConflict, SyncSide (+98 more)

### Community 7 - "device_host.py"
Cohesion: 0.05
Nodes (73): _detach(), remove_all(), _apps_method(), CallContext, capabilities(), clear_link(), collect_metrics(), _cpu_percent() (+65 more)

### Community 8 - "test_source_sync.py"
Cohesion: 0.05
Nodes (35): prune_versions(), run_due(), _run_one(), sync_loop(), sync_round(), _conflicts(), _fake_binlog(), gtid() (+27 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (27): CheckOption, CheckColor, Checked, Description, ChoiceCard, Badge, BadgeColor, Checked (+19 more)

### Community 10 - "Device"
Cohesion: 0.06
Nodes (51): Device, role_rank(), approve_enrollment(), _authenticate(), _can_remove_copy(), _deny(), deny_enrollment(), device_connect() (+43 more)

### Community 11 - "routers/transfer.py"
Cohesion: 0.07
Nodes (37): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job(), _owned_projects() (+29 more)

### Community 12 - "ProjectMember"
Cohesion: 0.07
Nodes (40): decrypt_with_passphrase(), encrypt_stream_with_passphrase(), encrypt_with_passphrase(), Base, ApiKey, InstanceSetting, Project, ProjectInvite (+32 more)

### Community 13 - "services/cli_tokens.py"
Cohesion: 0.08
Nodes (32): CliLogin, CliToken, approve_login(), create_login(), deny_login(), list_tokens(), login_by_code(), LoginAction (+24 more)

### Community 14 - "rtdb.py"
Cohesion: 0.14
Nodes (17): call(), check(), _child(), connection_info(), display(), entity(), _entity(), _error() (+9 more)

### Community 15 - "BackupsTab.tsx"
Cohesion: 0.04
Nodes (131): saveBlob(), hasLiveReplica(), useCohostEligibility(), useDataSourcesWithReplicas(), usePlacementOptions(), Backup, BackupCopy, BackupPolicy (+123 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.22
Nodes (24): Platform data model (UUID-keyed MariaDB tables), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), docs/PLATFORMS.md - Platforms and accounts this project uses, AWS hosting and databases, deployer-boundary IAM permissions boundary, Three AWS IAM policies: DeployerHosting, DeployerDatabases, DeployerRoles, Cloudflare tunnel and DNS, Cloudflare API token (four permissions) (+16 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.04
Nodes (90): useSchema(), ConventionIssue, LinkCardinality, RelationshipCardinality, SourceSchema, SchemaTab, labels, next (+82 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.06
Nodes (61): CloudflareZone, CloudProvider, ProviderName, ProviderSettings, GoogleIcon(), ProviderIcon(), ExtLink(), StepCard() (+53 more)

### Community 19 - "SourceReplica"
Cohesion: 0.09
Nodes (31): SourceReplica, SyncConflict, create_replica(), allocate_offset(), _check_value(), cohost_problem(), diff(), _drain() (+23 more)

### Community 20 - "deploys.ts"
Cohesion: 0.07
Nodes (68): useApp(), useApps(), useDataSources(), useDeployment(), useDeployments(), App, AppDetectDraft, AppPreset (+60 more)

### Community 21 - "GcpClient"
Cohesion: 0.04
Nodes (23): CloudError, _api_error(), GcpClient, _name(), _secret_id(), release(), handle(), test_real_google_client_binding_and_provider_requests() (+15 more)

### Community 22 - "mcp.py"
Cohesion: 0.07
Nodes (65): _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result(), handle(), _limit() (+57 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.07
Nodes (55): to_api_error(), m_tunnel(), get_value(), set_value(), _active_hostnames(), add_hostname(), apps_tunnel_name(), _cached_zones() (+47 more)

### Community 24 - "test_monitoring.py"
Cohesion: 0.21
Nodes (13): evaluate(), _minute(), record_request(), factory(), host_point(), put_host(), test_alerts_open_hold_and_resolve(), test_backup_failure_and_api_error_rules() (+5 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (19): ControlForm, IsBusy, State, RunState, Busy, Checking, NotResponding, Running (+11 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.06
Nodes (60): _audit(), AwsCredentials, _billing(), check_connection(), CloudBackupCreate, CloudDatabaseConnect, CloudDatabaseCreate, CloudRestore (+52 more)

### Community 27 - "Publish"
Cohesion: 0.09
Nodes (10): cache_control(), Publish, poll(), poll(), poll(), cleanup(), _save_stored(), _stored() (+2 more)

### Community 28 - "provisioning.py"
Cohesion: 0.05
Nodes (49): get_settings(), Settings, _check_mongodb(), _mongo_client(), ensure_database(), drop_copy(), provision_target(), cap_mariadb_users() (+41 more)

### Community 29 - "conftest.py"
Cohesion: 0.06
Nodes (28): get_engine(), set_redis(), auth_headers(), factory(), _clean_state(), client(), db(), fake_provisioning() (+20 more)

### Community 30 - "firestore.py"
Cohesion: 0.07
Nodes (48): _and(), _bad(), call(), check(), check_path(), collection_entity(), collection_ids(), composite_indexes() (+40 more)

### Community 31 - "Color"
Cohesion: 0.07
Nodes (25): Logo, Glyphs, IconBadge, Color, Kind, Soft, IconKind, Check (+17 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.08
Nodes (15): _delete_cf_records(), CloudflareClient, _cname_body(), _err(), test_bearer_header_and_verify(), test_check_permissions_all_ok(), test_check_permissions_missing(), test_check_permissions_no_zones_and_no_accounts() (+7 more)

### Community 33 - "shell_runner.py"
Cohesion: 0.07
Nodes (20): _as_uid(), _child_env(), _clean_up_slot(), _field(), _kill(), main(), make_server(), do_POST() (+12 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "test_cohost_apps.py"
Cohesion: 0.07
Nodes (33): AppReplica, apps_tunnel_token(), cohost_devices(), copy_problem(), deploy_params(), device_env(), device_problem(), eligible_devices() (+25 more)

### Community 36 - "WizardForm"
Cohesion: 0.11
Nodes (12): Card, BorderColor, Fill, Radius, TextBlock, RightAlign, SingleLine, TextColor (+4 more)

### Community 37 - "client.ts"
Cohesion: 0.11
Nodes (22): ApiClientOptions, buildQuery(), client, codeForStatus(), createApiClient(), download(), emit(), request() (+14 more)

### Community 38 - "executors.py"
Cohesion: 0.06
Nodes (32): BackupCopy, sha256_file(), any_copy(), _artifact_host(), _copy_destination(), _discard_new_source(), _final_snapshot_detached(), _job_copy() (+24 more)

### Community 39 - "dynamo.py"
Cohesion: 0.10
Nodes (42): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), create_backups(), _cursor_in() (+34 more)

### Community 40 - "github_actions.py"
Cohesion: 0.03
Nodes (85): conflict(), GitHubConnection, github_connect(), github_disconnect(), github_repos(), github_status(), delete_connection(), enqueue_teardown() (+77 more)

### Community 41 - "deployer_cli.py"
Cohesion: 0.12
Nodes (13): cmd_login(), cmd_logout(), config_path(), _home(), _interrupt_on_signals(), _is_root(), load_config(), local_url() (+5 more)

### Community 42 - "NotebookConsole.tsx"
Cohesion: 0.02
Nodes (225): ApiError, isDeviceOffline(), useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSourceSchema(), DataSourceKind (+217 more)

### Community 43 - "firestore_admin.py"
Cohesion: 0.07
Nodes (35): backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids(), create_schedule() (+27 more)

### Community 44 - "source_ops.py"
Cohesion: 0.11
Nodes (31): get_mongo_db(), check_status(), connection_info(), create_collection(), create_table(), delete_document(), delete_row(), drop_collection() (+23 more)

### Community 45 - "MCP.md"
Cohesion: 0.14
Nodes (31): CI job: Linux installer (install, CLI, update, uninstall), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits, Per-project MCP server (POST /v1/projects/<id>/mcp), MCP server for AI agents (+23 more)

### Community 46 - "README.md"
Cohesion: 0.06
Nodes (56): Linux support work: install.sh, deployer.sh, linux-installer CI, Docker Engine inside the deployer WSL distro (default runtime), Linux server platform (alternative to Windows PC), Windows PC platform (required unless Linux), docs/SETUP.md - Setting up Deployer, Cloudflare API token permissions (Tunnel Edit, Account Settings Read, DNS Edit, Zone Read), Open from any device with your own domain (Cloudflare tunnel), Deploy an app and connect an AI agent (MCP) (+48 more)

### Community 47 - "connections.py"
Cohesion: 0.06
Nodes (34): _require_tls(), build_mongo_client(), build_sql_engine(), _connect_args(), connection_info(), display_for(), _fingerprint(), friendly_error() (+26 more)

### Community 48 - "record"
Cohesion: 0.10
Nodes (32): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+24 more)

### Community 49 - "services/backups.py"
Cohesion: 0.05
Nodes (80): validation_error(), Backup, BackupLogSegment, archive_source_logs(), backup_out(), backups_out(), _bucket_keys(), _columns() (+72 more)

### Community 50 - "json.ts"
Cohesion: 0.07
Nodes (15): _connector(), process_redirect(), _describe(), DeviceAgent, _load_link(), run_agent(), _send(), write_status() (+7 more)

### Community 51 - "ddl_export.py"
Cohesion: 0.08
Nodes (31): cloud_engine(), build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources() (+23 more)

### Community 52 - "source_sync.py"
Cohesion: 0.04
Nodes (43): apply_changes(), dec(), _dt(), _dumps_token(), enc(), enc_row(), ext(), _failed() (+35 more)

### Community 53 - ".RenderChildren"
Cohesion: 0.13
Nodes (4): AppIcon, ThemedForm, IsForcedScale, ResetPasswordDialog

### Community 55 - "refresh_pc_ips"
Cohesion: 0.16
Nodes (19): refresh_pc_ips(), base(), create(), test_app_runner_app_gets_the_cloud_database(), test_connect_existing_instance(), test_create_needs_admin_and_billing_confirmation_then_builds_the_instance(), test_create_without_default_vpc_fails_plainly(), test_created_database_ip_for_admins_and_fixed_host() (+11 more)

### Community 56 - "services/transfer.py"
Cohesion: 0.06
Nodes (48): decrypt_json(), CloudConnection, invalid(), _api_key_out(), _api_key_secret(), _app_model(), _app_out(), _batches() (+40 more)

### Community 57 - "get_redis"
Cohesion: 0.05
Nodes (40): get_db(), get_sessionmaker(), DeviceProjectGrant, get_redis(), create_move_job(), _device_removed(), drop_copies_on_device(), _forget_lock() (+32 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.10
Nodes (38): Data sources endpoints and DataSourceInput, Error envelope and common error codes, Health and setup endpoints, Projects endpoints, Role hierarchy viewer<developer<admin<owner, Backups, Versions & Recovery, Backups API, Backup data model (jobs, backup_policies, backups, segments, copies) (+30 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.09
Nodes (5): IShellLinkW, ShellLinkCoClass, MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "test_github_actions.py"
Cohesion: 0.08
Nodes (41): workflow_path(), aws(), by_run(), cloud_app(), committed(), contents_path(), gh(), oidc() (+33 more)

### Community 61 - "services/cli_inputs.py"
Cohesion: 0.10
Nodes (24): CliInput, get_input(), submit_input(), apps_out(), cancel(), cancel_for_token(), check_pending(), clean_values() (+16 more)

### Community 62 - "deployments.py"
Cohesion: 0.07
Nodes (47): _drop_unless_gone(), _job_archive(), _job_drop(), _job_finalize_delete(), _job_platform_snapshot(), _job_prune(), _job_restore(), _job_snapshot() (+39 more)

### Community 63 - "AuditLog"
Cohesion: 0.04
Nodes (46): CaddyProxyHeaders, AuditLog, RefreshToken, prune(), test_prune(), _refresh(), test_change_password(), test_forwarded_headers_count_only_from_caddy() (+38 more)

### Community 64 - "test_cli_inputs.py"
Cohesion: 0.15
Nodes (27): bearer(), _create(), _issue(), _poll(), _submit(), test_app_ids_need_developer(), test_app_ids_submit_with_nothing_typed_changes_nothing(), test_app_ids_write_the_environment() (+19 more)

### Community 65 - "common.ps1"
Cohesion: 0.08
Nodes (38): Invoke-StatusJson(), Invoke-Update(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerStateTable(), Get-DeployerComposeServices(), Get-DeployerHealth() (+30 more)

### Community 66 - "make_app"
Cohesion: 0.03
Nodes (118): Deployment, DockerError, get_docker(), create_table(), enqueue_delete(), go_live(), prune(), secrets_of() (+110 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.03
Nodes (125): isApiStarting(), useInstanceSettings(), useProject(), useProviders(), useSetupStatus(), ImportSummary, Role, User (+117 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.07
Nodes (51): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, Checks to run before opening a PR (CI runs the same) (+43 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.12
Nodes (23): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), list_documents(), list_rows() (+15 more)

### Community 71 - "projects.py"
Cohesion: 0.09
Nodes (15): _cloud_cleanup(), create_project(), delete_project(), get_project(), list_projects(), ProjectCreate, ProjectUpdate, Provision (+7 more)

### Community 72 - "DockerCli"
Cohesion: 0.10
Nodes (9): DockerCli, on(), _kill(), _watch(), _git_env(), test_registry_password_goes_through_stdin_not_argv(), test_real_docker_cli_argv_hardening_and_secrets_stay_out_of_argv(), test_run_stops_a_silent_process_when_the_job_is_cancelled() (+1 more)

### Community 73 - "InputRequestPage.tsx"
Cohesion: 0.11
Nodes (34): CliInputField, JsonValue, Textarea, childPath(), cleanRtdbPath(), isBranch(), isRtdbKey(), parentPath() (+26 more)

### Community 74 - "api_from_config"
Cohesion: 0.10
Nodes (31): api_from_config(), app_path(), _app_status(), ask_secret(), _ask_values(), CliError, _cloudflare_stale(), cmd_alerts() (+23 more)

### Community 75 - "test_firestore.py"
Cohesion: 0.15
Nodes (5): FakeAdmin, _fail(), FakeFirestore, gcp(), viewer()

### Community 76 - "metrics.py"
Cohesion: 0.18
Nodes (15): _avg(), container_problem(), containers(), current_host(), _hist(), host_points(), metrics(), p95() (+7 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "json.ts"
Cohesion: 0.06
Nodes (37): _status(), read_status(), on_progress(), dump_source(), restore_into(), call(), calls_channel(), claim_upload() (+29 more)

### Community 79 - "test_cohosting_api.py"
Cohesion: 0.09
Nodes (28): SyncVersion, mark_online(), add_version(), _merge_warnings(), conflicted(), _replica(), team(), test_conflict_list_diff_and_suggestion() (+20 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.12
Nodes (23): static(), target(), local(), API, C1 as built, Cloud connections, Custom domains, Dashboard (+15 more)

### Community 81 - "tests/test_query_console.py"
Cohesion: 0.03
Nodes (66): _call_shell(), _canceller(), _clamp(), _connect_uri(), _enter_read_only(), _error_text(), _first_keyword(), _first_line() (+58 more)

### Community 82 - "CliError"
Cohesion: 0.15
Nodes (12): all_apps(), Api, _apply_hint(), ask_web(), _cancel_input(), cmd_ask(), cmd_google_oauth(), find_app() (+4 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.09
Nodes (36): add_host(), assert_no_secrets(), desired(), link(), test_add_hostname_dns_failure_rolls_back_ingress(), test_add_hostname_existing_record(), test_add_hostname_new(), test_add_hostname_overwrite_cname_updates_in_place() (+28 more)

### Community 84 - "routers/remote_access.py"
Cohesion: 0.22
Nodes (17): add_hostname(), delete_stale_records(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, quick() (+9 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.20
Nodes (18): _callback(), _error_of(), _link_state(), _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error(), test_callback_requires_same_browser(), test_github_requires_primary_verified_email() (+10 more)

### Community 86 - "deployer.ps1"
Cohesion: 0.17
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

### Community 90 - "Install-WslEngine"
Cohesion: 0.12
Nodes (27): Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Test-ExistingRuntime(), Write-DryRunAction(), ConvertTo-DeployerRuntimePath() (+19 more)

### Community 91 - "device_local.py"
Cohesion: 0.13
Nodes (19): device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to() (+11 more)

### Community 92 - "get_schema"
Cohesion: 0.13
Nodes (17): CollectionInput, ColumnReference, ColumnSpec, create_collection(), create_link(), create_table(), delete_link(), _drop() (+9 more)

### Community 93 - "get_source"
Cohesion: 0.19
Nodes (18): cohosting_eligibility(), delete_replica(), get_conflict(), _key_param(), list_conflicts(), list_replicas(), _replica(), replica_action() (+10 more)

### Community 94 - "DumpScanner"
Cohesion: 0.19
Nodes (9): count_insert_rows(), _count_row_tuples(), DumpScanner, test_count_insert_rows_ignores_parens_inside_strings(), test_dump_scanner_collects_point_and_counts(), _scan(), test_count_insert_rows_first_line_only(), test_multi_line_extended_insert_as_written_by_mariadb_11() (+1 more)

### Community 95 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+11 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "DecryptingReader"
Cohesion: 0.10
Nodes (7): DecryptingReader, EncryptingWriter, open_artifact_plain(), test_small_writes_and_reader_with_gzip(), _encrypted(), test_decrypting_reader_is_a_context_manager(), test_open_artifact_plain_uncompressed_closes_file_on_exit()

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (7): CheckResult, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "test_data_sources.py"
Cohesion: 0.09
Nodes (9): fake_connect(), project_setup(), sqlite_engine(), test_check_connection_and_delete(), test_deleting_source_removes_links(), test_internal_network_is_refused_for_non_owners(), test_managed_connection_hint_says_database_access_is_needed(), test_managed_create_drops_database_when_commit_fails() (+1 more)

### Community 101 - "test_backup_crypto.py"
Cohesion: 0.09
Nodes (29): body(), backup_key(), BackupCryptoError, derive_backup_key(), export_key_material(), _hkdf(), import_key_material(), iter_decrypt() (+21 more)

### Community 102 - "delete"
Cohesion: 0.10
Nodes (22): tunnel_cname_target(), cursor(), delete(), stale(), test_delete_rechecks_and_skips_records_that_are_no_longer_stale(), test_delete_reports_a_record_that_vanished(), test_delete_validates_record_ids(), test_lists_only_unknown_tunnel_cnames() (+14 more)

### Community 103 - "conventions.py"
Cohesion: 0.13
Nodes (38): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+30 more)

### Community 104 - "ApiError"
Cohesion: 0.05
Nodes (76): ApiError, check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document(), delete_row() (+68 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.12
Nodes (27): SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query() (+19 more)

### Community 106 - "threading"
Cohesion: 0.10
Nodes (9): CallListener, fake_device(), factory(), FakeDevice, make_device(), factory(), add_source(), sql_config() (+1 more)

### Community 107 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.06
Nodes (34): cloud_env(), AppSecrets, Add database -> In your Firebase project, API, API, API, dashboard, MCP, Apps, Apps on Cloud Run (+26 more)

### Community 108 - "query-shell"
Cohesion: 0.11
Nodes (18): cap_add, cap_drop, command, cpus, entrypoint, extra_hosts, image, init (+10 more)

### Community 109 - ".Ask"
Cohesion: 0.07
Nodes (21): AppInfo, DefaultInstallDir, ExePath, PowerShellExe, Ref, Repo, RepoUrl, TroubleshootingUrl (+13 more)

### Community 110 - "SchemaDiffView.tsx"
Cohesion: 0.15
Nodes (23): DiffChange, FieldDiff, SchemaDiff, SchemaDiffEntity, AttributeChange, CHANGE_LABELS, CHANGE_ORDER, DiffSummary (+15 more)

### Community 111 - "test_repo_detect.py"
Cohesion: 0.12
Nodes (21): detect(), _detect_dir(), has(), src(), _dirs(), env_keys(), _find_module(), _join() (+13 more)

### Community 112 - "FakeDynamo"
Cohesion: 0.08
Nodes (4): FakeDynamo, _missing(), PitrFake, test_retried_delete_skips_the_protection_switch()

### Community 113 - "Query Console"
Cohesion: 0.13
Nodes (25): Data browser (SQL rows, MongoDB documents), Query Console, Query API endpoint, query.run audit event, Concurrency, timeout and output limits, Dashboard Query tab, CodeMirror editor and toolbar, In-band query errors vs HTTP errors (+17 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (3): Register-DeployerTask(), ConvertTo-DeployerWslPath(), Register-ScheduledTask()

### Community 115 - "AwsClient"
Cohesion: 0.06
Nodes (5): AwsClient, _code(), _wrap(), test_secrets_manager_calls_match_botocore_models(), Not verified against real clouds

### Community 116 - "CONTRIBUTING.md"
Cohesion: 0.19
Nodes (12): CI job: Windows installer checks and DeployerSetup.exe, Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Layout, PowerShell conventions (+4 more)

### Community 118 - "test_device_rpc.py"
Cohesion: 0.16
Nodes (14): _fresh(), _hello(), test_call_fails_when_connection_replaced(), handler(), test_call_offline_device(), test_call_timeout(), test_disabling_device_closes_socket(), test_error_status_is_clamped() (+6 more)

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "DataSource"
Cohesion: 0.06
Nodes (33): DataSource, _cloud_call(), cloud_out(), connect(), connect_firestore(), connect_rtdb(), connect_tables(), _connection() (+25 more)

### Community 123 - "FakeRtdb"
Cohesion: 0.31
Nodes (3): _fail(), FakeRtdb, by()

### Community 124 - "data_sources.py"
Cohesion: 0.13
Nodes (12): check_data_source(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate, _ensure_name_free(), external_config(), list_data_sources() (+4 more)

### Community 125 - "test_jobs.py"
Cohesion: 0.07
Nodes (33): claim(), _clamp(), finish(), handler_for(), HandlerSpec, heartbeat(), Heartbeat, decorator() (+25 more)

### Community 126 - "write"
Cohesion: 0.16
Nodes (10): _as_doc(), check_key(), check_path(), check_value(), query_params(), read(), run_console(), run_op() (+2 more)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.16
Nodes (8): binlog_name_with_seq(), binlog_seq(), parse_binlog(), rename_oplog_entry(), _event(), test_binlog_names(), test_parse_binlog_extracts_databases_and_times(), test_rename_oplog_entry()

### Community 128 - "test_cli_client.py"
Cohesion: 0.10
Nodes (34): env_of(), _fill(), _http_error(), _login(), call(), _no_input_request(), _pipe(), test_a_deleted_app_stops_the_wait_and_cancels() (+26 more)

### Community 130 - "test_backups_pitr.py"
Cohesion: 0.21
Nodes (13): dispose_all(), _iso(), _pause(), _restore(), _run_all(), servers(), _snapshot(), _source() (+5 more)

### Community 131 - "devDependencies"
Cohesion: 0.14
Nodes (14): devDependencies, eslint@^10.10.0, jsdom@^30.0.1, tailwindcss@^4.3.3, @types/react@^19.3.0, @types/react-dom@^19.3.0, vite@^8.3.0, vitest@^5.0.1 (+6 more)

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

### Community 136 - "device_executor.py"
Cohesion: 0.05
Nodes (18): register_copy_target(), copy_artifact(), DeviceExecutor, register(), run_device_job(), run_executor_call(), _sized(), _TempArtifact (+10 more)

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "integration/test_query_console.py"
Cohesion: 0.17
Nodes (18): mariadb(), mongo(), run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results(), test_mariadb_multi_statement_script(), test_mariadb_read_only_session(), test_mariadb_session_state_does_not_leak() (+10 more)

### Community 139 - "connection"
Cohesion: 0.03
Nodes (134): encrypt_json(), set_factory(), aws_statements(), app_databases(), instance_role_name(), resource_name(), resources(), site_id() (+126 more)

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
Cohesion: 0.10
Nodes (24): Ground rules, Deployer HTTP API v1, Project API keys (dpl_role_random), Auth endpoints (signup, login, refresh, OAuth), Export and import endpoints, Instance settings and users endpoints, Members and invites endpoints, OAuth callback redirect flow (+16 more)

### Community 144 - "Core.cs"
Cohesion: 0.15
Nodes (4): DeployerSetup, DeployerCli, Internet, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 146 - "BackupPolicy"
Cohesion: 0.27
Nodes (12): BackupPolicy, new_id(), gfs_keep(), policy(), seg(), snap(), test_chain_stops_at_the_restore_gap_marker(), test_chains_over_a_week_of_segments_key_each_segment_once() (+4 more)

### Community 147 - "mongo_snapshot"
Cohesion: 0.11
Nodes (19): BackupEngineError, _check_exit(), _fetch_binlog(), mariadb_defaults_file(), mongo_config_file(), mongo_root_uri(), _mongorestore(), _option_value() (+11 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "FakeCloudflare"
Cohesion: 0.15
Nodes (5): set_transport(), fake_cf(), fake_cf(), FakeCloudflare, _ok()

### Community 150 - "test_mcp.py"
Cohesion: 0.09
Nodes (13): inner(), run(), env(), call(), rpc(), _route_role(), test_data_tools(), test_document_tools() (+5 more)

### Community 151 - "cli"
Cohesion: 0.14
Nodes (5): cli(), urlopen(), _fail_on(), interrupt(), test_ctrl_c_exits_130_even_when_the_cancel_fails()

### Community 152 - "sample"
Cohesion: 0.18
Nodes (7): _iso(), sample(), sample_loop(), FakeDocker, test_docker_stats_parses_ps_inspect_and_stats(), test_sample_writes_bounded_host_series_and_containers(), Browsing, editing, querying

### Community 153 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.26
Nodes (16): Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes, Link step (find or create tunnel, fetch connector token) (+8 more)

### Community 154 - "test_transfer_devices.py"
Cohesion: 0.23
Nodes (13): _export_handler(), fake_provision(), provision_managed_source(), _payload(), test_export_fails_when_device_offline(), test_instance_export_includes_device_tables_and_device_data(), test_instance_import_offline_device_restores_on_main(), test_instance_import_onto_connected_device() (+5 more)

### Community 155 - "apiSnippets.ts"
Cohesion: 0.21
Nodes (15): UsageDialog(), buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req (+7 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.09
Nodes (32): Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Notes for AI agents (skill copy, MCP, graphify), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09), For AI agents (+24 more)

### Community 157 - "active"
Cohesion: 0.18
Nodes (11): dismiss_alert(), get_metrics(), get_summary(), list_alerts(), snooze_alert(), SnoozeBody, WebhookTestBody, active() (+3 more)

### Community 158 - "backup_engine.py"
Cohesion: 0.09
Nodes (53): ArtifactWriter, check_db_name(), compare_counts(), _index_path(), _latest_oplog_ts(), _load_dump(), feed(), _load_index() (+45 more)

### Community 159 - "introspection.py"
Cohesion: 0.07
Nodes (39): chunks(), match_entity(), reference_base(), bad(), analyze_documents(), visit(), apply_mongo_indexes(), approximate_row_counts() (+31 more)

### Community 160 - "services/devices.py"
Cohesion: 0.04
Nodes (70): _b64d(), _b64e(), decrypt_secret(), _derive(), encrypt_secret(), _master_key(), _passphrase_key(), random_token() (+62 more)

### Community 161 - "CheckRow"
Cohesion: 0.17
Nodes (12): CheckRow, Detail, SingleLine, State, TextLeft, Title, CheckStatus, Fail (+4 more)

### Community 162 - "LocalExecutor"
Cohesion: 0.18
Nodes (3): node_for(), backup_root(), LocalExecutor

### Community 163 - "services"
Cohesion: 0.18
Nodes (10): command, volumes, volumes, volumes, services, api, migrate, query-shell (+2 more)

### Community 164 - "test_container_config.py"
Cohesion: 0.24
Nodes (7): read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through(), test_migrations_run_to_completion_before_the_api_starts(), test_query_shell_sidecar_holds_no_secrets(), test_security_headers_are_set_by_caddy_not_nginx(), test_untrusted_containers_share_no_network_with_the_api()

### Community 165 - "request_cancel"
Cohesion: 0.19
Nodes (5): cancel_job(), get_job(), _get_job(), list_jobs(), request_cancel()

### Community 166 - "list_query_log"
Cohesion: 0.21
Nodes (5): delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), serialize()

### Community 168 - ".stats"
Cohesion: 0.15
Nodes (10): parse_size(), _percent(), text(), Alerts, API, API key rate limit, Monitoring and alerts, Not covered (yet) (+2 more)

### Community 169 - "steps"
Cohesion: 0.36
Nodes (11): steps, steps, steps, steps, steps, steps, if, name (+3 more)

### Community 170 - "bundle"
Cohesion: 0.20
Nodes (11): name, needs, permissions, runs-on, jobs, bundle, tests, contents (+3 more)

### Community 171 - "_JsonReader"
Cohesion: 0.31
Nodes (3): _JsonReader, test_remove_or_demote_lists_keys_to_rotate(), make_key()

### Community 172 - "validate"
Cohesion: 0.21
Nodes (8): _bad(), check_connection(), create_connection(), list_connections(), normalize_aws(), normalize_firebase(), targets_out(), validate()

### Community 173 - "images"
Cohesion: 0.18
Nodes (11): name, needs, permissions, runs-on, strategy, component, context, images (+3 more)

### Community 174 - "SetupOptions"
Cohesion: 0.18
Nodes (8): SetupOptions, Autostart, DesktopShortcut, EnableLan, InstallDir, KeepAwake, Port, Runtime

### Community 175 - "By section"
Cohesion: 0.17
Nodes (11): _outcome(), 11. Docs and the deploy-website skill vs the code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 3. Query console, query log, saved queries, 4. Backups, PITR, jobs, worker, export/import, 5. Host devices, device RPC/agent, co-hosting sync and co-host apps (+3 more)

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

### Community 184 - "test_projects.py"
Cohesion: 0.21
Nodes (7): slugify(), unique_slug(), test_create_and_list(), test_create_provisioning_failure_rolls_back(), test_create_with_provisioning(), test_slugify(), test_unique_slug_suffix()

### Community 185 - "test_transfer_stream.py"
Cohesion: 0.11
Nodes (12): read_data_entry(), restore_file(), _stream_parts(), _dump(), fake_engine(), FakeConn, materialize(), test_bare_numbers_cut_by_the_buffer() (+4 more)

### Community 186 - "models.py"
Cohesion: 0.02
Nodes (68): seal_process(), require_role(), create_app(), _is_ip(), lifespan(), _config_hosts(), _is_internal(), normalize_input() (+60 more)

### Community 187 - "ScriptRunner"
Cohesion: 0.09
Nodes (8): LogWindow, ToolbarHeight, OutputWindow, ToolbarHeight, Payload, ScriptRunner, Cancelled, IsRunning

### Community 188 - "alerts.py"
Cohesion: 0.28
Nodes (12): _api_rule(), _cloud_cleanup_rule(), Condition, conditions(), _container_rules(), _fmt_age(), _fmt_gb(), _host_rules() (+4 more)

### Community 189 - "utcnow"
Cohesion: 0.04
Nodes (68): Job, utcnow(), _backup_rules(), prune_all(), reconcile_interrupted(), heartbeat_key(), recover_stale(), run_queued() (+60 more)

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

### Community 198 - "eslint.config.js"
Cohesion: 0.18
Nodes (10): @eslint/js@^10.0.1, eslint-plugin-react-hooks@^7.1.1, eslint-plugin-react-refresh@^0.5.7, globals@^17.12.0, typescript-eslint@^8.70.0, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh (+2 more)

### Community 200 - "Deployer audit - 2026-09-28"
Cohesion: 0.18
Nodes (11): Checklist, Critical, Deployer audit - 2026-09-28, Executive summary, High, Low, Medium, Not reviewed (+3 more)

### Community 201 - "test_webhook"
Cohesion: 0.20
Nodes (7): test_webhook(), deliver(), deliver_async(), post_webhook(), validate_webhook_url(), bad(), test_deliver_retries_with_backoff()

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
Cohesion: 0.06
Nodes (17): free_blocks(), _nat_alive(), nat_name(), _ours(), _public_subnet(), _unless_gone(), save_state(), test_ensure_vpc_connector_runs_against_the_real_botocore_models() (+9 more)

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 210 - "Usability for non-experts"
Cohesion: 0.20
Nodes (10): Journey 1: Install on an old PC, Journey 2: First run and owner account, Journey 3: Create a project, a table and some rows, Journey 4: Invite a friend, Journey 5: Deploy a website, Journey 6: Put it on the internet or the LAN, Journey 7: Backups and recovery, Journey 8: Day-to-day running (+2 more)

### Community 211 - "test_devices_enrollment.py"
Cohesion: 0.39
Nodes (6): _allow_poll(), _enroll(), test_approve_selected_projects(), test_deny_and_expiry(), test_device_token_does_not_work_on_user_endpoints(), test_full_enrollment_flow()

### Community 212 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 213 - "package.json"
Cohesion: 0.22
Nodes (8): @types/node@^22.20.3, typescript@~6.0.3, name, private, type, version, @types/node, typescript

### Community 215 - "create_input"
Cohesion: 0.46
Nodes (4): cancel_input(), _cli_row(), create_input(), poll_input()

### Community 216 - "DeviceSide"
Cohesion: 0.32
Nodes (3): DeviceSide, full(), test_device_side_speaks_rpc_and_drops_unexpected_fields()

### Community 217 - "error"
Cohesion: 0.22
Nodes (10): error(), primary(), 8. Windows setup wizard and Deployer Control (C# WinForms), New databases, API (`/v1/projects/{pid}`), Co-hosting: live two-way database copies and failover websites, Dashboard (for whoever builds it), Honest limits (shown in the dashboard where they matter) (+2 more)

### Community 218 - "User"
Cohesion: 0.04
Nodes (61): api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), load_project_access(), require_instance_owner() (+53 more)

### Community 219 - "shared_fixtures.py"
Cohesion: 0.16
Nodes (10): set_docker(), docker(), FakeProviders, make_source(), project_setup(), providers(), sqlite_engine(), state_dir() (+2 more)

### Community 220 - "test_data_api_keys.py"
Cohesion: 0.08
Nodes (17): QueryRun, delete_before(), get_run(), list_runs(), record_run(), _trim_project(), setup(), test_acting_user_falls_back_to_owner() (+9 more)

### Community 221 - "install_error_handlers"
Cohesion: 0.27
Nodes (6): _body(), install_error_handlers(), _api_error(), _http(), _unhandled(), _validation()

### Community 223 - "test_release_workflow.py"
Cohesion: 0.33
Nodes (3): _permissions(), test_images_wait_for_ci_and_prereleases_skip_latest(), test_release_workflow_permissions_are_per_job()

### Community 224 - "Invoke-DeployerNative"
Cohesion: 0.11
Nodes (19): Find-Python(), Invoke-PythonCli(), Test-CliCommand(), Test-CliSignedIn(), ConvertTo-DeployerArgument(), Disable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes() (+11 more)

### Community 225 - "query/diff.ts"
Cohesion: 0.48
Nodes (5): DIFF_MAX_LINES, DiffLine, lineDiff(), lines(), render()

### Community 226 - "install.ps1"
Cohesion: 0.09
Nodes (17): Get-InstallerArgumentString(), Get-InstallerCliHint(), Get-SystemFacts(), Register-ResumeAfterReboot(), Request-Reboot(), Show-DockerDesktopNotice(), Write-CheckResult(), Write-InstallStep() (+9 more)

### Community 230 - "vite.config.ts"
Cohesion: 0.40
Nodes (4): @tailwindcss/vite@^4.3.3, @vitejs/plugin-react@^6.1.1, @tailwindcss/vite, @vitejs/plugin-react

### Community 233 - "API runtime dependencies (requirements.txt)"
Cohesion: 0.20
Nodes (12): API runtime dependencies (requirements.txt), alembic, argon2-cffi (password hashing), cryptography, API dev and test dependencies (requirements-dev.txt), fakeredis, pytest, ruff (+4 more)

### Community 235 - "test_devices_local.py"
Cohesion: 0.09
Nodes (15): validate_primary_url(), bad(), fake_primary(), FakePrimary, test_enrollment_on_uninitialized_device(), test_enrollment_poll_never_overwrites_a_cancel(), cancelled_meanwhile(), test_enrollment_poll_race_keeps_approved() (+7 more)

### Community 236 - "repoLinks.ts"
Cohesion: 0.50
Nodes (3): blob, raw, repoLinks()

### Community 239 - "ensure_mongo_replica_set"
Cohesion: 0.50
Nodes (3): ensure_mongo_replica_set(), _redact(), _secrets()

### Community 242 - "Data API with API keys"
Cohesion: 0.22
Nodes (9): rows(), Calling from a browser, Config file, Data API with API keys, Queries, Rotating a key, Rows (SQL sources), Schema (+1 more)

### Community 243 - "test_cli_provider_tools.py"
Cohesion: 0.20
Nodes (8): _fake_run(), run(), test_google_apis_needs_gcloud_signed_in(), test_google_apis_takes_the_project_from_the_apps_client_id(), answers(), test_webhook_through_gh_sends_the_secret_on_stdin_only(), test_webhook_without_a_connection_or_gh_says_what_to_do(), test_conftest_removes_its_temp_dir_at_exit()

### Community 247 - "ci.yml"
Cohesion: 0.17
Nodes (11): concurrency, cancel-in-progress, group, name, permissions, contents, branches, True (+3 more)

### Community 248 - "release.yml"
Cohesion: 0.33
Nodes (5): name, permissions, tags, True, push

### Community 252 - "InputField"
Cohesion: 0.24
Nodes (3): InputCreate, InputField, InputSubmit

### Community 253 - "C2-4 as built: Firebase Realtime Database"
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

### Community 255 - "x-mongodb-upgrade"
Cohesion: 0.33
Nodes (6): x-mongodb-upgrade, entrypoint, mem_limit, network_mode, profiles, volumes

## Knowledge Gaps
- **145 isolated node(s):** `deployer-api`, `RFC-5987`, `RFC-4180`, `Checking`, `Running` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2554 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **25 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `App`, `oauth.py`, `device_host.py`, `device_executor.py`, `test_source_sync.py`, `Device`, `routers/transfer.py`, `ProjectMember`, `services/cli_tokens.py`, `rtdb.py`, `integration/test_query_console.py`, `SourceReplica`, `GcpClient`, `mcp.py`, `services/remote_access.py`, `routers/cloud.py`, `test_transfer_devices.py`, `provisioning.py`, `active`, `backup_engine.py`, `firestore.py`, `services/devices.py`, `introspection.py`, `conftest.py`, `test_cohost_apps.py`, `executors.py`, `dynamo.py`, `github_actions.py`, `firestore_admin.py`, `validate`, `source_ops.py`, `connections.py`, `record`, `services/backups.py`, `json.ts`, `By section`, `source_sync.py`, `services/transfer.py`, `get_redis`, `models.py`, `alerts.py`, `services/cli_inputs.py`, `deployments.py`, `AuditLog`, `utcnow`, `test_cli_inputs.py`, `make_app`, `test_github_actions.py`, `data.py`, `projects.py`, `test_webhook`, `json.ts`, `test_cohosting_api.py`, `tests/test_query_console.py`, `create_input`, `DeviceSide`, `User`, `device_local.py`, `get_schema`, `get_source`, `install_error_handlers`, `test_data_api_keys.py`, `run_query`, `saved_queries.py`, `threading`, `test_devices_local.py`, `test_auto_increment_is_persisted_for_restarts_and_repaired_with_a_log`, `test_device_rpc.py`, `DataSource`, `data_sources.py`, `write`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Are the 149 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 149 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.07814207650273224 - nodes in this community are weakly interconnected._
- **Why does `WizardForm` connect `WizardForm` to `Ui`, `CheckRow`, `.TestMarkers`, `FlatButton`, `IShellLinkW`, `.Ask`, `SetupOptions`, `Core.cs`, `.RenderChildren`, `UninstallForm`, `ControlForm`, `models.py`, `ScriptRunner`, `WizardPage`, `Color`?**
  _High betweenness centrality (0.062) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `react` be split into smaller, more focused modules?**
  _Cohesion score 0.06077755905511811 - nodes in this community are weakly interconnected._