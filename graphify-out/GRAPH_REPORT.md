# Graph Report - deployer  (2026-10-29)

## Corpus Check
- 521 files · ~646,662 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9674 nodes · 34507 edges · 254 communities (226 shown, 28 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3373 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `053a7be9`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- react
- tests/test_query_console.py
- types.ts
- App
- test_auth.py
- Button
- device_host.py
- test_source_sync.py
- FlatButton
- models.py
- routers/transfer.py
- ProjectMember
- services/cli_tokens.py
- rtdb.py
- DevicesPage.tsx
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
- crypto.py
- WizardForm
- CloudError
- BackupPolicy
- dynamo.py
- github_actions.py
- FakeSide
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
- test_dynamo.py
- services/transfer.py
- test_setup.py
- Deployer HTTP API v1
- IShellLinkW
- github.py
- User
- cloud_db.py
- AuditLog
- test_cli_inputs.py
- common.ps1
- make_app
- toast-context.ts
- docker-compose.yml
- environment
- data.py
- deps.py
- crowsfoot.ts
- rtdb.ts
- deployer_cli.py
- test_firestore.py
- metrics.py
- services
- json.ts
- test_cohosting_api.py
- Cloud hosting and databases (AWS, Firebase)
- query_console.py
- test_firestore.py
- test_remote_access.py
- routers/remote_access.py
- test_oauth.py
- deployer.ps1
- UninstallForm
- caddy
- options
- Install-WslEngine
- get_redis
- record
- .transfer
- test_backups_engine.py
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
- create_app
- C2-3 as built: Cloud Firestore
- query-shell
- .Ask
- SchemaDiffView.tsx
- test_repo_detect.py
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- AwsClient
- test_query_log.py
- decrypt_with_passphrase
- .ensure_github_role
- with
- compilerOptions
- set_transport
- test_rtdb.py
- data_sources.py
- worker.py
- sql_read_only_refusal
- Any
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
- make_app
- schema_diff.py
- _fake_binlog
- MarkerKind
- docs/ARCHITECTURE.md - Deployer Architecture
- Core.cs
- supervisor.sh
- Backup
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
- get_summary
- backup_engine.py
- AppFields
- test_apps_api.py
- CheckRow
- LocalExecutor
- services
- test_source_sync_live.py
- audit.py
- test_mysql_canceller_kills_the_query_from_a_private_pool
- wslplatform.tests.ps1
- volumes
- steps
- bundle
- _clean_up_slot
- connection_out
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
- sqlalchemy
- ScriptRunner
- alerts.py
- utcnow
- mariadb
- mongodb-upgrade-6
- env
- mongodb-upgrade-8
- _TempArtifact
- C2-2 as built: DynamoDB
- Invoke-Preflight
- test_sweep_leftovers_removes_stale_partials_and_temp_databases
- eslint.config.js
- re
- Deployer audit - 2026-09-28
- oauth.py
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_nat_network_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- CloudflareError
- Usability for non-experts
- handle
- scripts
- package.json
- _Watchdog
- .delete_secret
- DeviceSide
- error
- iso
- redact
- query_log.py
- SqlStore
- tsconfig.json
- FakeExecutor
- Invoke-DeployerNative
- query/diff.ts
- install.ps1
- RequestMetricsMiddleware
- docker-entrypoint.sh
- test_big_mongo_document_is_sent_in_a_batch_of_its_own
- vite.config.ts
- Firestore point-in-time recovery and deletes (as built)
- AwsClient
- API runtime dependencies (requirements.txt)
- test_auto_increment_is_persisted_for_restarts_and_repaired_with_a_log
- Settings
- repoLinks.ts
- entrypoint.sh
- upgrade.sh
- env.py
- secrets
- m_tunnel
- Data API with API keys
- test_cli_provider_tools.py
- token
- _fmt_age
- ci.yml
- release.yml
- deployer-api
- test_create_validation
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

## Communities (254 total, 28 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.08
Nodes (15): SettingsDialog, Autostart, KeepAwake, Lan, Port, InputBox, Invalid, Rule (+7 more)

### Community 1 - "react"
Cohesion: 0.05
Nodes (157): api, qk, invalidateProjectSources(), isJobFinished(), useCohostEligibility(), useJob(), usePlacementOptions(), Backup (+149 more)

### Community 2 - "tests/test_query_console.py"
Cohesion: 0.09
Nodes (28): run_sql(), _timeout_statement(), mongo_config(), run_fake(), test_mongosh_cursor_batch_and_truncation(), test_mongosh_errors_are_in_band(), test_mongosh_missing_in_sidecar_or_sidecar_down(), test_mongosh_node_escapes_refused_for_developers() (+20 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (170): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, App, AppBuild, AppCloud, AppCreated (+162 more)

### Community 4 - "App"
Cohesion: 0.05
Nodes (73): conflict(), Domain, _add_cloud_domain(), add_domain(), AppCreate, _audit_cohost(), _audit_database_access(), BuildBody (+65 more)

### Community 5 - "test_auth.py"
Cohesion: 0.03
Nodes (77): random_token(), sha256_hex(), client_ip(), new_id(), RefreshToken, change_password(), LinkIn, login() (+69 more)

### Community 6 - "Button"
Cohesion: 0.05
Nodes (188): refresh(), errorMessage(), saveBlob(), hasLiveReplica(), useApps(), useDataSourcesWithReplicas(), useDevices(), useProject() (+180 more)

### Community 7 - "device_host.py"
Cohesion: 0.03
Nodes (89): _detach(), run_device_job(), run_executor_call(), _apps_method(), CallContext, capabilities(), clear_link(), collect_metrics() (+81 more)

### Community 8 - "test_source_sync.py"
Cohesion: 0.18
Nodes (18): sync_round(), _conflicts(), _replica(), _seed(), test_changes_flow_both_ways_without_echo(), test_concurrent_edit_opens_conflict_and_other_keys_keep_syncing(), test_delete_versus_update_is_a_conflict(), test_mongo_echo_is_suppressed_by_version() (+10 more)

### Community 9 - "FlatButton"
Cohesion: 0.04
Nodes (27): CheckOption, CheckColor, Checked, Description, ChoiceCard, Badge, BadgeColor, Checked (+19 more)

### Community 10 - "models.py"
Cohesion: 0.03
Nodes (106): AppReplica, Device, DeviceEnrollment, role_rank(), approve_enrollment(), _authenticate(), _can_remove_copy(), _deny() (+98 more)

### Community 11 - "routers/transfer.py"
Cohesion: 0.09
Nodes (25): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job(), _owned_projects() (+17 more)

### Community 12 - "ProjectMember"
Cohesion: 0.08
Nodes (36): Base, ApiKey, InstanceSetting, Project, ProjectInvite, ProjectMember, SchemaLink, UserIdentity (+28 more)

### Community 13 - "services/cli_tokens.py"
Cohesion: 0.07
Nodes (46): not_found(), CliLogin, CliToken, approve_login(), create_login(), deny_login(), list_tokens(), login_by_code() (+38 more)

### Community 14 - "rtdb.py"
Cohesion: 0.10
Nodes (27): _as_doc(), call(), check(), check_key(), check_path(), check_value(), _child(), connection_info() (+19 more)

### Community 15 - "DevicesPage.tsx"
Cohesion: 0.07
Nodes (56): useProjects(), Device, DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability, ManagedEngine (+48 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.22
Nodes (24): Platform data model (UUID-keyed MariaDB tables), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), docs/PLATFORMS.md - Platforms and accounts this project uses, AWS hosting and databases, deployer-boundary IAM permissions boundary, Three AWS IAM policies: DeployerHosting, DeployerDatabases, DeployerRoles, Cloudflare tunnel and DNS, Cloudflare API token (four permissions) (+16 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.05
Nodes (86): ConventionIssue, ProjectSchema, SourceSchema, SchemaTab, labels, next, Menu(), MenuItem() (+78 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.05
Nodes (88): useInstanceSettings(), CloudflareZone, Domain, ImportSummary, ProviderSettings, PublicUrlRequest, PublicUrlResponse, RemoteAccess (+80 more)

### Community 19 - "SourceReplica"
Cohesion: 0.09
Nodes (22): SyncConflict, SyncVersion, allocate_offset(), _check_value(), diff(), _drain(), _eq(), _field() (+14 more)

### Community 20 - "deploys.ts"
Cohesion: 0.06
Nodes (80): useApp(), useDataSources(), useDeployment(), useDeployments(), AppDetectDraft, AppPreset, AppReplica, AppTarget (+72 more)

### Community 21 - "GcpClient"
Cohesion: 0.07
Nodes (4): GcpClient, _name(), _secret_id(), handle()

### Community 22 - "mcp.py"
Cohesion: 0.08
Nodes (63): _call_tool(), _check_args(), _confirmed(), Ctx, _dispatch(), _error_result(), _limit(), _mongo() (+55 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.09
Nodes (47): to_api_error(), get_value(), set_value(), _active_hostnames(), add_hostname(), apps_tunnel_name(), _cached_zones(), _client() (+39 more)

### Community 24 - "test_monitoring.py"
Cohesion: 0.17
Nodes (14): active(), evaluate(), _minute(), record_request(), factory(), put_host(), test_alerts_open_hold_and_resolve(), test_backup_failure_and_api_error_rules() (+6 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (19): ControlForm, IsBusy, State, RunState, Busy, Checking, NotResponding, Running (+11 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.07
Nodes (52): _audit(), AwsCredentials, _billing(), CloudBackupCreate, CloudDatabaseConnect, CloudDatabaseCreate, CloudRestore, _confirm_delete() (+44 more)

### Community 27 - "Publish"
Cohesion: 0.04
Nodes (30): cache_control(), check_domain(), cloud_env(), content_type(), _create_cf_records(), _delete_cf_records(), _export(), _merge_records() (+22 more)

### Community 28 - "provisioning.py"
Cohesion: 0.06
Nodes (49): get_settings(), ensure_database(), dispose_all(), database_size(), m_provision(), drop_copy(), provision_target(), cap_mariadb_users() (+41 more)

### Community 29 - "conftest.py"
Cohesion: 0.05
Nodes (41): get_engine(), set_redis(), auth_headers(), factory(), _clean_state(), client(), db(), fake_provisioning() (+33 more)

### Community 30 - "firestore.py"
Cohesion: 0.07
Nodes (49): _and(), _bad(), call(), check(), check_path(), collection_entity(), collection_ids(), composite_indexes() (+41 more)

### Community 31 - "Color"
Cohesion: 0.07
Nodes (25): Logo, Glyphs, IconBadge, Color, Kind, Soft, IconKind, Check (+17 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.09
Nodes (14): CloudflareClient, _cname_body(), test_bearer_header_and_verify(), test_check_permissions_all_ok(), test_check_permissions_missing(), test_check_permissions_no_zones_and_no_accounts(), test_error_mapping(), test_inactive_token_is_auth_failure() (+6 more)

### Community 33 - "shell_runner.py"
Cohesion: 0.09
Nodes (16): _as_uid(), _child_env(), _field(), _kill(), main(), make_server(), do_POST(), _reply() (+8 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "crypto.py"
Cohesion: 0.05
Nodes (37): _derive(), encrypt_secret(), set_docker(), replicate(), sweep(), new_token(), HostDockerCli, test_static_site_end_to_end() (+29 more)

### Community 36 - "WizardForm"
Cohesion: 0.11
Nodes (12): Card, BorderColor, Fill, Radius, TextBlock, RightAlign, SingleLine, TextColor (+4 more)

### Community 37 - "CloudError"
Cohesion: 0.08
Nodes (11): CloudError, _api_error(), release(), API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, New databases (+3 more)

### Community 38 - "BackupPolicy"
Cohesion: 0.12
Nodes (21): BackupPolicy, _bucket_keys(), _default_policy(), delete_artifact_rows(), delete_backup(), delete_segment(), ensure_policy(), gfs_keep() (+13 more)

### Community 39 - "dynamo.py"
Cohesion: 0.10
Nodes (42): aws_for(), backup_name(), _backup_out(), _bad(), call(), check(), create_backups(), _cursor_in() (+34 more)

### Community 40 - "github_actions.py"
Cohesion: 0.04
Nodes (89): App, _actions_report(), enqueue_teardown(), set_factory(), generate_dockerfile(), _shell_quote(), webhook_secret(), artifact_for() (+81 more)

### Community 41 - "FakeSide"
Cohesion: 0.10
Nodes (6): WriteRejected, FakeSide, FakeStore, test_reapplying_a_batch_is_a_no_op(), test_rounds_of_different_copies_run_side_by_side(), changes()

### Community 42 - "NotebookConsole.tsx"
Cohesion: 0.02
Nodes (231): isDeviceOffline(), useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSourceSchema(), DataSourceKind, MongoQueryResponse (+223 more)

### Community 43 - "firestore_admin.py"
Cohesion: 0.07
Nodes (32): backup_delete_summary(), backup_out(), bucket_location(), _call(), clone_spec(), collection_ids(), create_schedule(), database_delete_summary() (+24 more)

### Community 44 - "source_ops.py"
Cohesion: 0.12
Nodes (34): DataSource, create_table(), introspect_sources(), check_status(), connection_info(), create_collection(), create_table(), delete_document() (+26 more)

### Community 45 - "MCP.md"
Cohesion: 0.14
Nodes (31): CI job: Linux installer (install, CLI, update, uninstall), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits, Per-project MCP server (POST /v1/projects/<id>/mcp), MCP server for AI agents (+23 more)

### Community 46 - "README.md"
Cohesion: 0.06
Nodes (56): Linux support work: install.sh, deployer.sh, linux-installer CI, Docker Engine inside the deployer WSL distro (default runtime), Linux server platform (alternative to Windows PC), Windows PC platform (required unless Linux), docs/SETUP.md - Setting up Deployer, Cloudflare API token permissions (Tunnel Edit, Account Settings Read, DNS Edit, Zone Read), Open from any device with your own domain (Cloudflare tunnel), Deploy an app and connect an AI agent (MCP) (+48 more)

### Community 47 - "connections.py"
Cohesion: 0.06
Nodes (40): build_mongo_client(), build_sql_engine(), check_status(), cloud_engine(), _connect_args(), connection_info(), display_for(), _fingerprint() (+32 more)

### Community 48 - "record"
Cohesion: 0.11
Nodes (29): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+21 more)

### Community 49 - "services/backups.py"
Cohesion: 0.06
Nodes (55): BackupCopy, sha256_file(), any_copy(), _artifact_host(), backup_out(), backups_out(), copies_by_artifact(), _copy_destination() (+47 more)

### Community 50 - "json.ts"
Cohesion: 0.05
Nodes (33): _find_user(), main(), _oauth_set(), _oauth_status(), _oauth_write(), _platform_list(), _platform_restore(), _read_json_stdin() (+25 more)

### Community 51 - "ddl_export.py"
Cohesion: 0.05
Nodes (53): reference_base(), build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources() (+45 more)

### Community 52 - "source_sync.py"
Cohesion: 0.06
Nodes (26): apply_changes(), _failed(), _merge_warnings(), _named(), _norm(), origin_server_id(), _parse_gtids(), persist_auto_increment() (+18 more)

### Community 53 - ".RenderChildren"
Cohesion: 0.13
Nodes (4): AppIcon, ThemedForm, IsForcedScale, ResetPasswordDialog

### Community 54 - "BackupExecutor"
Cohesion: 0.08
Nodes (6): BackupExecutor, DeviceExecutorUnavailable, executor_for(), register_device_executor_factory(), run_local_call(), test_executor_for_routes_devices()

### Community 55 - "test_dynamo.py"
Cohesion: 0.07
Nodes (42): aws_statements(), requirements(), _actions(), _resources(), test_boundary_document_caps_roles_to_deployer_resources(), test_deployer_user_may_only_write_roles_that_carry_the_boundary(), test_policy_covers_databases_and_scopes_the_firewall(), test_policy_and_roles_cover_the_secret_stores() (+34 more)

### Community 56 - "services/transfer.py"
Cohesion: 0.05
Nodes (59): decrypt_json(), decrypt_secret(), invalid(), _api_key_out(), _api_key_secret(), _app_model(), _app_out(), _batches() (+51 more)

### Community 57 - "test_setup.py"
Cohesion: 0.09
Nodes (10): test_create_owner_then_already_initialized(), test_health_reports_degraded_when_a_required_service_is_down(), test_instance_settings_roundtrip(), test_is_initialized_false_without_users(), test_is_initialized_is_the_single_setup_check(), test_oauth_cli(), run(), test_owner_disables_user_and_sees_their_projects() (+2 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.10
Nodes (38): Data sources endpoints and DataSourceInput, Error envelope and common error codes, Health and setup endpoints, Projects endpoints, Role hierarchy viewer<developer<admin<owner, Backups, Versions & Recovery, Backups API, Backup data model (jobs, backup_policies, backups, segments, copies) (+30 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.09
Nodes (5): IShellLinkW, ShellLinkCoClass, MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "github.py"
Cohesion: 0.05
Nodes (46): GitHubConnection, github_status(), clone_token(), resync_webhooks(), check_can_build(), _api(), apps_using(), _call() (+38 more)

### Community 61 - "User"
Cohesion: 0.06
Nodes (35): User, AppUpdate, _check_env(), dispatch_env_deployment(), _merge_env(), set_env_vars(), _apps_for(), cancel_input() (+27 more)

### Community 62 - "cloud_db.py"
Cohesion: 0.03
Nodes (97): encrypt_json(), CloudConnection, _cloud_cleanup(), _job_archive(), _job_drop(), _job_finalize_delete(), _job_prune(), _job_restore() (+89 more)

### Community 63 - "AuditLog"
Cohesion: 0.18
Nodes (23): AuditLog, _create(), test_api_key_lifecycle(), test_config_download(), test_reveal(), base(), connected(), gcp() (+15 more)

### Community 64 - "test_cli_inputs.py"
Cohesion: 0.14
Nodes (30): CliInput, cancel(), expire_due(), prune(), bearer(), _create(), _issue(), _poll() (+22 more)

### Community 65 - "common.ps1"
Cohesion: 0.08
Nodes (38): Invoke-StatusJson(), Invoke-Update(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerStateTable(), Get-DeployerComposeServices(), Get-DeployerHealth() (+30 more)

### Community 66 - "make_app"
Cohesion: 0.03
Nodes (88): DockerCli, on(), _kill(), _watch(), DockerError, get_docker(), _git_env(), parse_size() (+80 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.02
Nodes (141): ApiClientOptions, ApiError, buildQuery(), client, codeForStatus(), createApiClient(), download(), emit() (+133 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.08
Nodes (46): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, Checks to run before opening a PR (CI runs the same) (+38 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.11
Nodes (24): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _json_or_text(), list_documents() (+16 more)

### Community 71 - "deps.py"
Cohesion: 0.05
Nodes (36): api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), load_api_key_access(), load_project_access(), ProjectAccess (+28 more)

### Community 72 - "crowsfoot.ts"
Cohesion: 0.18
Nodes (17): RelationshipCardinality, Cardinality, describeEnds(), edgeEnds, EndMarker, MARKER_LABEL, MARKER_NOTATION, markerPath() (+9 more)

### Community 73 - "rtdb.ts"
Cohesion: 0.32
Nodes (10): childPath(), cleanRtdbPath(), isBranch(), isRtdbKey(), parentPath(), preview(), Branch(), Expandable() (+2 more)

### Community 74 - "deployer_cli.py"
Cohesion: 0.06
Nodes (57): test_conftest_removes_its_temp_dir_at_exit(), all_apps(), Api, api_from_config(), app_path(), _app_status(), _apply_hint(), ask_secret() (+49 more)

### Community 75 - "test_firestore.py"
Cohesion: 0.15
Nodes (4): FakeAdmin, FakeFirestore, gcp(), viewer()

### Community 76 - "metrics.py"
Cohesion: 0.17
Nodes (16): _container_rules(), _avg(), container_problem(), containers(), current_host(), _hist(), host_points(), metrics() (+8 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "json.ts"
Cohesion: 0.04
Nodes (50): download_transfer(), iterate(), _transfer_for(), upload_transfer(), apps_tunnel_token(), push_tunnel(), run_replicate(), sweep_device() (+42 more)

### Community 79 - "test_cohosting_api.py"
Cohesion: 0.10
Nodes (27): SourceReplica, fan_out_schema_change(), mark_online(), conflicted(), _replica(), team(), test_conflict_list_diff_and_suggestion(), test_copy_failure_marks_replica_and_drops_partial_copy() (+19 more)

### Community 80 - "Cloud hosting and databases (AWS, Firebase)"
Cohesion: 0.05
Nodes (47): cloud_url(), static(), target(), AppSecrets, local(), API, API, AWS policy split as built: purpose-sized managed policies (+39 more)

### Community 81 - "query_console.py"
Cohesion: 0.09
Nodes (22): _call_shell(), _clamp(), _connect_uri(), _enter_read_only(), _error_text(), _first_keyword(), _first_line(), _is_blank() (+14 more)

### Community 82 - "test_firestore.py"
Cohesion: 0.24
Nodes (16): base(), connect(), docs_url(), _fail(), test_app_runner_app_does_not_get_firestore(), test_browse_page_filter_and_subcollections(), test_cloud_run_app_gets_its_firestore_database(), test_connect_lists_databases_and_never_deletes_them() (+8 more)

### Community 83 - "test_remote_access.py"
Cohesion: 0.09
Nodes (35): add_host(), assert_no_secrets(), desired(), link(), test_add_hostname_dns_failure_rolls_back_ingress(), test_add_hostname_existing_record(), test_add_hostname_new(), test_add_hostname_overwrite_cname_updates_in_place() (+27 more)

### Community 84 - "routers/remote_access.py"
Cohesion: 0.22
Nodes (17): add_hostname(), delete_stale_records(), get_remote_access(), HostnameBody, link(), LinkBody, PublicUrlBody, quick() (+9 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.19
Nodes (19): _callback(), _error_of(), _link_state(), _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error(), test_callback_requires_same_browser(), test_github_requires_primary_verified_email() (+11 more)

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

### Community 91 - "get_redis"
Cohesion: 0.05
Nodes (36): get_redis(), device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none() (+28 more)

### Community 92 - "record"
Cohesion: 0.07
Nodes (47): cohosting_eligibility(), create_replica(), delete_replica(), get_conflict(), _key_param(), list_conflicts(), list_replicas(), _replica() (+39 more)

### Community 93 - ".transfer"
Cohesion: 0.17
Nodes (5): _dt(), _Round, Side, test_import_limit_follows_free_memory(), test_import_over_memory_limit_is_413()

### Community 94 - "test_backups_engine.py"
Cohesion: 0.08
Nodes (18): binlog_name_with_seq(), count_insert_rows(), _count_row_tuples(), DumpScanner, _mongo_build_oplog(), parse_binlog(), rename_oplog_entry(), _event() (+10 more)

### Community 95 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+11 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "DecryptingReader"
Cohesion: 0.19
Nodes (5): DecryptingReader, feed(), rewrite_dump_line(), test_decrypting_reader_is_a_context_manager(), test_rewrite_dump_line()

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (7): CheckResult, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "test_data_sources.py"
Cohesion: 0.10
Nodes (9): fake_connect(), project_setup(), sqlite_engine(), test_check_connection_and_delete(), test_create_external_sql_source(), test_deleting_source_removes_links(), test_internal_network_is_refused_for_non_owners(), test_managed_connection_hint_says_database_access_is_needed() (+1 more)

### Community 101 - "test_backup_crypto.py"
Cohesion: 0.06
Nodes (33): body(), backup_key(), BackupCryptoError, derive_backup_key(), EncryptingWriter, export_key_material(), _hkdf(), import_key_material() (+25 more)

### Community 102 - "delete"
Cohesion: 0.24
Nodes (9): tunnel_cname_target(), delete(), stale(), test_delete_rechecks_and_skips_records_that_are_no_longer_stale(), test_delete_reports_a_record_that_vanished(), test_delete_validates_record_ids(), test_lists_only_unknown_tunnel_cnames(), test_non_owner_forbidden() (+1 more)

### Community 103 - "conventions.py"
Cohesion: 0.12
Nodes (40): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+32 more)

### Community 104 - "ApiError"
Cohesion: 0.05
Nodes (76): ApiError, bad(), check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document() (+68 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.12
Nodes (26): SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query() (+18 more)

### Community 106 - "create_app"
Cohesion: 0.14
Nodes (5): seal_process(), create_app(), lifespan(), setup(), test_unhandled_error_is_enveloped()

### Community 107 - "C2-3 as built: Cloud Firestore"
Cohesion: 0.08
Nodes (27): chunks(), bad(), _sort_types(), key(), cursor(), device_apply(), Add database -> In your Firebase project, API (+19 more)

### Community 108 - "query-shell"
Cohesion: 0.11
Nodes (18): cap_add, cap_drop, command, cpus, entrypoint, extra_hosts, image, init (+10 more)

### Community 109 - ".Ask"
Cohesion: 0.07
Nodes (21): AppInfo, DefaultInstallDir, ExePath, PowerShellExe, Ref, Repo, RepoUrl, TroubleshootingUrl (+13 more)

### Community 110 - "SchemaDiffView.tsx"
Cohesion: 0.11
Nodes (29): DiffChange, Field, FieldDiff, SchemaDiff, SchemaDiffEntity, AttributeChange, CHANGE_LABELS, CHANGE_ORDER (+21 more)

### Community 111 - "test_repo_detect.py"
Cohesion: 0.12
Nodes (21): detect(), _detect_dir(), has(), src(), _dirs(), env_keys(), _find_module(), _join() (+13 more)

### Community 112 - "FakeDynamo"
Cohesion: 0.07
Nodes (6): aws(), FakeDynamo, _missing(), PitrFake, test_retried_delete_skips_the_protection_switch(), viewer()

### Community 113 - "Query Console"
Cohesion: 0.13
Nodes (25): Data browser (SQL rows, MongoDB documents), Query Console, Query API endpoint, query.run audit event, Concurrency, timeout and output limits, Dashboard Query tab, CodeMirror editor and toolbar, In-band query errors vs HTTP errors (+17 more)

### Community 114 - "keepalive.tests.ps1"
Cohesion: 0.07
Nodes (3): Register-DeployerTask(), ConvertTo-DeployerWslPath(), Register-ScheduledTask()

### Community 115 - "AwsClient"
Cohesion: 0.08
Nodes (3): _code(), _wrap(), inner()

### Community 116 - "test_query_log.py"
Cohesion: 0.17
Nodes (11): console(), runs(), test_get_and_delete(), test_list_filters_and_permissions(), test_logged_text_masks_passwords(), test_record_run_caps_text_and_trims_the_project(), add(), test_runs_are_logged_with_outcome() (+3 more)

### Community 118 - "decrypt_with_passphrase"
Cohesion: 0.17
Nodes (9): _b64d(), _b64e(), decrypt_with_passphrase(), encrypt_stream_with_passphrase(), encrypt_with_passphrase(), _master_key(), _passphrase_key(), test_read_export_errors() (+1 more)

### Community 119 - ".ensure_github_role"
Cohesion: 0.20
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "set_transport"
Cohesion: 0.12
Nodes (9): set_transport(), test_real_client_admin_and_storage_urls(), handle(), test_real_client_storage_objects(), test_real_client_builds_firestore_urls_and_shares_tokens(), handle(), test_real_google_client_binding_and_provider_requests(), handle() (+1 more)

### Community 123 - "test_rtdb.py"
Cohesion: 0.12
Nodes (20): base(), connect(), _fail(), FakeRtdb, by(), gcp(), test_browse_lazily_query_and_write_by_path(), test_cloud_run_app_gets_its_realtime_database() (+12 more)

### Community 124 - "data_sources.py"
Cohesion: 0.06
Nodes (27): _body(), install_error_handlers(), _api_error(), _http(), _unhandled(), _validation(), validation_error(), CaddyProxyHeaders (+19 more)

### Community 125 - "worker.py"
Cohesion: 0.12
Nodes (16): ensure_mongo_replica_set(), _redact(), _secrets(), acquire_leadership(), _guard(), _load_plugins(), main(), mongo_replset_loop() (+8 more)

### Community 126 - "sql_read_only_refusal"
Cohesion: 0.19
Nodes (9): mongo_read_only_refusal(), split_sql(), sql_read_only_refusal(), test_mongo_read_only_accepts(), test_mongo_read_only_refuses(), test_read_only_refusals_name_the_word(), test_split_sql_respects_strings_and_comments(), test_sql_read_only_accepts() (+1 more)

### Community 127 - "Any"
Cohesion: 0.21
Nodes (6): enc(), ext(), _mongo_change(), MongoStore, unext(), _valid_collection()

### Community 128 - "test_cli_client.py"
Cohesion: 0.10
Nodes (33): env_of(), _fill(), _http_error(), _login(), call(), _no_input_request(), _pipe(), test_a_deleted_app_stops_the_wait_and_cancels() (+25 more)

### Community 130 - "test_backups_pitr.py"
Cohesion: 0.24
Nodes (15): archive_source_logs(), consistent_at(), logs_prefix(), parse_time(), invalidate(), _iso(), _pause(), _restore() (+7 more)

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
Cohesion: 0.07
Nodes (13): register_copy_target(), copy_artifact(), DeviceExecutor, register(), _sized(), unregister(), cleanup_transfers(), agent_task() (+5 more)

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "integration/test_query_console.py"
Cohesion: 0.14
Nodes (20): mariadb(), mongo(), run(), sh(), test_mariadb_error_mid_way_keeps_earlier_results(), test_mariadb_multi_statement_script(), test_mariadb_read_only_session(), test_mariadb_session_state_does_not_leak() (+12 more)

### Community 139 - "make_app"
Cohesion: 0.03
Nodes (116): Deployment, free_blocks(), _public_subnet(), set_factory(), instance_role_name(), resource_name(), site_id(), set_enabled() (+108 more)

### Community 140 - "schema_diff.py"
Cohesion: 0.18
Nodes (15): diff(), schema_at(), apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view() (+7 more)

### Community 141 - "_fake_binlog"
Cohesion: 0.18
Nodes (6): _fake_binlog(), gtid(), __init__(), _read_all(), test_big_row_is_sent_in_a_batch_of_its_own(), test_transaction_bigger_than_a_batch_is_split_across_rounds()

### Community 142 - "MarkerKind"
Cohesion: 0.17
Nodes (11): Marker, MarkerKind, Check, Done, Error, None, Other, RebootRequired (+3 more)

### Community 143 - "docs/ARCHITECTURE.md - Deployer Architecture"
Cohesion: 0.09
Nodes (25): Ground rules, Deployer HTTP API v1, Project API keys (dpl_role_random), Auth endpoints (signup, login, refresh, OAuth), Export and import endpoints, Instance settings and users endpoints, Members and invites endpoints, OAuth callback redirect flow (+17 more)

### Community 144 - "Core.cs"
Cohesion: 0.15
Nodes (4): DeployerSetup, DeployerCli, Internet, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 146 - "Backup"
Cohesion: 0.12
Nodes (25): Backup, BackupLogSegment, _columns(), contiguous(), _covers(), covers_anchor(), _follows(), _gap_marker() (+17 more)

### Community 147 - "mongo_snapshot"
Cohesion: 0.10
Nodes (22): BackupEngineError, _check_exit(), _fetch_binlog(), _load_dump(), mariadb_defaults_file(), mongo_config_file(), mongo_root_uri(), _mongorestore() (+14 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "FakeCloudflare"
Cohesion: 0.14
Nodes (6): set_transport(), fake_cf(), _err(), fake_cf(), FakeCloudflare, _ok()

### Community 150 - "test_mcp.py"
Cohesion: 0.13
Nodes (4): _route_role(), test_every_tool_needs_at_least_its_routes_role(), test_malformed_requests(), test_tools_list_depends_on_role()

### Community 151 - "cli"
Cohesion: 0.13
Nodes (6): cli(), urlopen(), _fail_on(), test_ctrl_c_cancels_the_request(), interrupt(), test_ctrl_c_exits_130_even_when_the_cancel_fails()

### Community 152 - "sample"
Cohesion: 0.20
Nodes (7): _iso(), sample(), sample_loop(), FakeDocker, host_point(), test_docker_stats_parses_ps_inspect_and_stats(), test_sample_writes_bounded_host_series_and_containers()

### Community 153 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.26
Nodes (16): Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME), Remote access API, Cloudflare API token requirements, Remote access data model (settings, domains), desired.json / status.json handshake, Remote access error codes, Link step (find or create tunnel, fetch connector token) (+8 more)

### Community 154 - "test_transfer_devices.py"
Cohesion: 0.17
Nodes (17): DeviceProjectGrant, hosted(), team(), _export_handler(), handler(), fake_provision(), provision_managed_source(), _payload() (+9 more)

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.06
Nodes (44): CI job: Windows installer checks and DeployerSetup.exe, Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests (+36 more)

### Community 157 - "get_summary"
Cohesion: 0.47
Nodes (4): get_metrics(), get_summary(), list_alerts(), visible()

### Community 158 - "backup_engine.py"
Cohesion: 0.10
Nodes (47): ArtifactWriter, binlog_seq(), check_db_name(), compare_counts(), _index_path(), _latest_oplog_ts(), _load_index(), _managed_user_for() (+39 more)

### Community 159 - "AppFields"
Cohesion: 0.27
Nodes (4): AppFields, _one_line(), _valid_branch(), 6. Push-to-deploy apps, GitHub integration, MCP, monitoring/alerts, remote access

### Community 160 - "test_apps_api.py"
Cohesion: 0.15
Nodes (16): create(), env(), sign(), test_app_hostnames(), test_create_list_get_and_roles(), test_database_access_is_admin_only(), test_delete_app_when_cloudflare_fails(), test_env_set_and_unset_merge_without_sending_the_rest() (+8 more)

### Community 161 - "CheckRow"
Cohesion: 0.17
Nodes (12): CheckRow, Detail, SingleLine, State, TextLeft, Title, CheckStatus, Fail (+4 more)

### Community 162 - "LocalExecutor"
Cohesion: 0.13
Nodes (3): node_for(), backup_root(), LocalExecutor

### Community 163 - "services"
Cohesion: 0.18
Nodes (10): command, volumes, volumes, volumes, services, api, migrate, query-shell (+2 more)

### Community 164 - "test_source_sync_live.py"
Cohesion: 0.21
Nodes (5): CopySide, replica(), _sql(), test_mariadb_two_way_sync(), test_mongodb_two_way_sync()

### Community 165 - "audit.py"
Cohesion: 0.08
Nodes (9): github_connect(), github_disconnect(), github_repos(), cancel_job(), get_job(), _get_job(), list_jobs(), prune() (+1 more)

### Community 168 - "volumes"
Cohesion: 0.18
Nodes (11): volumes, backups, caddy_apps, caddy_config, caddy_data, mariadb_conf, mariadb_data, mongodb_config (+3 more)

### Community 169 - "steps"
Cohesion: 0.36
Nodes (11): steps, steps, steps, steps, steps, steps, if, name (+3 more)

### Community 170 - "bundle"
Cohesion: 0.20
Nodes (11): name, needs, permissions, runs-on, jobs, bundle, tests, contents (+3 more)

### Community 171 - "_clean_up_slot"
Cohesion: 0.22
Nodes (5): _clean_up_slot(), _slot_pids(), _fake_proc(), test_clean_up_slot_kills_a_real_process(), test_slot_pids_reads_proc_without_forking()

### Community 172 - "connection_out"
Cohesion: 0.15
Nodes (9): check_connection(), ConnectionCreate, create_connection(), list_connections(), requirements(), connection_out(), get_connection(), list_connections() (+1 more)

### Community 173 - "images"
Cohesion: 0.18
Nodes (11): name, needs, permissions, runs-on, strategy, component, context, images (+3 more)

### Community 174 - "SetupOptions"
Cohesion: 0.18
Nodes (8): SetupOptions, Autostart, DesktopShortcut, EnableLan, InstallDir, KeepAwake, Port, Runtime

### Community 175 - "By section"
Cohesion: 0.14
Nodes (13): _outcome(), 10. Dashboard data features: databases, data browser, schema, query notebook/terminal, backups, devices, co-hosting, jobs, deploys, 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 3. Query console, query log, saved queries (+5 more)

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
Cohesion: 0.15
Nodes (9): _random_suffix(), slugify(), unique_slug(), test_create_and_list(), test_create_provisioning_failure_rolls_back(), test_create_with_provisioning(), test_delete(), test_slugify() (+1 more)

### Community 185 - "test_transfer_stream.py"
Cohesion: 0.09
Nodes (13): _JsonReader, read_data_entry(), restore_file(), _stream_parts(), _dump(), fake_engine(), FakeConn, materialize() (+5 more)

### Community 186 - "sqlalchemy"
Cohesion: 0.05
Nodes (25): upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+17 more)

### Community 187 - "ScriptRunner"
Cohesion: 0.09
Nodes (8): LogWindow, ToolbarHeight, OutputWindow, ToolbarHeight, Payload, ScriptRunner, Cancelled, IsRunning

### Community 188 - "alerts.py"
Cohesion: 0.44
Nodes (8): _api_rule(), _cloud_cleanup_rule(), Condition, conditions(), _fmt_gb(), _host_rules(), _replica_rules(), _tunnel_rule()

### Community 189 - "utcnow"
Cohesion: 0.03
Nodes (92): Job, utcnow(), _backup_rules(), enqueue_detached_finalize(), prune_all(), prune_jobs(), reconcile_interrupted(), _redis_due() (+84 more)

### Community 190 - "mariadb"
Cohesion: 0.29
Nodes (7): command, image, mem_limit, networks, restart, volumes, mariadb

### Community 191 - "mongodb-upgrade-6"
Cohesion: 0.29
Nodes (7): entrypoint, image, mem_limit, network_mode, profiles, volumes, mongodb-upgrade-6

### Community 192 - "env"
Cohesion: 0.22
Nodes (8): run(), env(), call(), rpc(), test_data_tools(), test_document_tools(), recorder(), fn()

### Community 193 - "mongodb-upgrade-8"
Cohesion: 0.29
Nodes (7): entrypoint, image, mem_limit, network_mode, profiles, volumes, mongodb-upgrade-8

### Community 195 - "C2-2 as built: DynamoDB"
Cohesion: 0.17
Nodes (10): engine(), Add database -> In your AWS account -> NoSQL, API, Apps on App Runner, Backups (Backups tab), C2-2 as built: DynamoDB, Data model, Not verified against real clouds (+2 more)

### Community 196 - "Invoke-Preflight"
Cohesion: 0.57
Nodes (5): Invoke-Preflight(), Get-DeployerAppPortUsers(), Test-DeployerAppPort(), Get-NetTCPConnection(), Get-Process()

### Community 198 - "eslint.config.js"
Cohesion: 0.18
Nodes (10): @eslint/js@^10.0.1, eslint-plugin-react-hooks@^7.1.1, eslint-plugin-react-refresh@^0.5.7, globals@^17.12.0, typescript-eslint@^8.70.0, @eslint/js, eslint-plugin-react-hooks, eslint-plugin-react-refresh (+2 more)

### Community 199 - "re"
Cohesion: 0.05
Nodes (26): _documented(), _norm(), _paths(), _routes(), test_documented_endpoints_exist(), read(), test_api_healthcheck_and_backup_dir_live_in_compose_only(), test_caddy_lets_every_import_upload_through() (+18 more)

### Community 200 - "Deployer audit - 2026-09-28"
Cohesion: 0.18
Nodes (11): Checklist, Critical, Deployer audit - 2026-09-28, Executive summary, High, Low, Medium, Not reviewed (+3 more)

### Community 201 - "oauth.py"
Cohesion: 0.04
Nodes (58): get_settings_(), list_all_projects(), list_audit(), list_users(), settings_out(), provider(), SettingsUpdate, update_settings() (+50 more)

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
Cohesion: 0.09
Nodes (9): _nat_alive(), nat_name(), _ours(), _unless_gone(), test_ensure_vpc_connector_runs_against_the_real_botocore_models(), test_nat_network_runs_against_the_real_botocore_models(), subnet(), Permissions added (`DeployerDatabases` and `DeployerHosting`, shown in Settings -> Cloud accounts) (+1 more)

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 210 - "Usability for non-experts"
Cohesion: 0.20
Nodes (10): Journey 1: Install on an old PC, Journey 2: First run and owner account, Journey 3: Create a project, a table and some rows, Journey 4: Invite a friend, Journey 5: Deploy a website, Journey 6: Put it on the internet or the LAN, Journey 7: Backups and recovery, Journey 8: Day-to-day running (+2 more)

### Community 212 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 213 - "package.json"
Cohesion: 0.22
Nodes (8): @types/node@^22.20.3, typescript@~6.0.3, name, private, type, version, @types/node, typescript

### Community 214 - "_Watchdog"
Cohesion: 0.25
Nodes (3): _Watchdog, 3. Running a query in the console or notebook, SQL

### Community 216 - "DeviceSide"
Cohesion: 0.32
Nodes (3): DeviceSide, full(), test_device_side_speaks_rpc_and_drops_unexpected_fields()

### Community 217 - "error"
Cohesion: 0.13
Nodes (16): error(), primary(), text(), 8. Windows setup wizard and Deployer Control (C# WinForms), API (`/v1/projects/{pid}`), Co-hosting: live two-way database copies and failover websites, Dashboard (for whoever builds it), Honest limits (shown in the dashboard where they matter) (+8 more)

### Community 218 - "iso"
Cohesion: 0.06
Nodes (35): api_key_config(), api_key_out(), ApiKeyCreate, create_api_key(), generate_secret(), keys_to_rotate(), list_api_keys(), _project_key() (+27 more)

### Community 219 - "redact"
Cohesion: 0.33
Nodes (3): redact(), test_redact(), test_redact_is_linear()

### Community 220 - "query_log.py"
Cohesion: 0.22
Nodes (10): QueryRun, delete_before(), get_run(), list_runs(), prune(), record_run(), serialize(), _trim_project() (+2 more)

### Community 221 - "SqlStore"
Cohesion: 0.19
Nodes (6): dec(), enc_row(), _q(), SchemaMismatch, SqlStore, test_value_encoding_round_trips_and_hashes_stably()

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

### Community 231 - "Firestore point-in-time recovery and deletes (as built)"
Cohesion: 0.33
Nodes (6): API, Deletes (Backups tab; typed name), Firestore point-in-time recovery and deletes (as built), MCP, Not verified against real clouds, Point-in-time recovery (Backups tab -> Point-in-time recovery)

### Community 233 - "API runtime dependencies (requirements.txt)"
Cohesion: 0.20
Nodes (12): API runtime dependencies (requirements.txt), alembic, argon2-cffi (password hashing), cryptography, API dev and test dependencies (requirements-dev.txt), fakeredis, pytest, ruff (+4 more)

### Community 236 - "repoLinks.ts"
Cohesion: 0.50
Nodes (3): blob, raw, repoLinks()

### Community 239 - "env.py"
Cohesion: 0.60
Nodes (3): run_migrations_offline(), run_migrations_online(), _url()

### Community 241 - "m_tunnel"
Cohesion: 0.17
Nodes (9): m_tunnel(), fix_state_ownership(), _read_json(), read_status(), state_dir(), sync_desired(), sync_on_startup(), write_desired() (+1 more)

### Community 242 - "Data API with API keys"
Cohesion: 0.20
Nodes (10): order(), rows(), Calling from a browser, Config file, Data API with API keys, Queries, Rotating a key, Rows (SQL sources) (+2 more)

### Community 243 - "test_cli_provider_tools.py"
Cohesion: 0.26
Nodes (7): _fake_run(), run(), test_google_apis_needs_gcloud_signed_in(), test_google_apis_takes_the_project_from_the_apps_client_id(), answers(), test_webhook_through_gh_sends_the_secret_on_stdin_only(), test_webhook_without_a_connection_or_gh_says_what_to_do()

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
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2555 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `test_backups_pitr.py`, `tests/test_query_console.py`, `App`, `test_auth.py`, `device_host.py`, `device_executor.py`, `test_source_sync.py`, `models.py`, `routers/transfer.py`, `schema_diff.py`, `services/cli_tokens.py`, `rtdb.py`, `integration/test_query_console.py`, `ProjectMember`, `SourceReplica`, `mcp.py`, `services/remote_access.py`, `routers/cloud.py`, `Publish`, `provisioning.py`, `conftest.py`, `backup_engine.py`, `firestore.py`, `test_transfer_devices.py`, `crypto.py`, `CloudError`, `BackupPolicy`, `dynamo.py`, `github_actions.py`, `firestore_admin.py`, `connection_out`, `source_ops.py`, `connections.py`, `record`, `services/backups.py`, `json.ts`, `By section`, `source_sync.py`, `services/transfer.py`, `github.py`, `User`, `cloud_db.py`, `utcnow`, `test_cli_inputs.py`, `make_app`, `data.py`, `deps.py`, `oauth.py`, `json.ts`, `test_cohosting_api.py`, `query_console.py`, `DeviceSide`, `iso`, `get_redis`, `record`, `query_log.py`, `SqlStore`, `.transfer`, `saved_queries.py`, `test_auto_increment_is_persisted_for_restarts_and_repaired_with_a_log`, `C2-3 as built: Cloud Firestore`, `m_tunnel`, `test_query_log.py`, `decrypt_with_passphrase`, `data_sources.py`, `Any`?**
  _High betweenness centrality (0.120) - this node is a cross-community bridge._
- **Are the 149 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 149 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.07814207650273224 - nodes in this community are weakly interconnected._
- **Why does `WizardForm` connect `WizardForm` to `Ui`, `CheckRow`, `.TestMarkers`, `FlatButton`, `IShellLinkW`, `.Ask`, `SetupOptions`, `Core.cs`, `.RenderChildren`, `UninstallForm`, `ControlForm`, `sqlalchemy`, `ScriptRunner`, `WizardPage`, `Color`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `react` be split into smaller, more focused modules?**
  _Cohesion score 0.04636450992953235 - nodes in this community are weakly interconnected._