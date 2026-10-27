# Graph Report - deployer  (2026-10-27)

## Corpus Check
- 519 files · ~645,670 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 19 file(s) not represented in the graph (top: (none) 11, .conf 2, .toml 1)

## Summary
- 9642 nodes · 34339 edges · 243 communities (212 shown, 31 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3337 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `449efc79`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Ui
- react
- Button
- types.ts
- source_sync.py
- oauth.py
- Badge
- ApiError
- apps.py
- FlatButton
- Device
- react
- utcnow
- get_connection
- rtdb.py
- Alert
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
- get_settings
- conftest.py
- firestore.py
- Job
- CloudflareClient
- device_rpc.py
- deployer.sh
- make_app
- WizardForm
- ThemedForm
- services/__init__.py
- dynamo.py
- App
- deployer_cli.py
- NotebookConsole.tsx
- json.ts
- test_source_sync.py
- MCP.md
- README.md
- re
- routers/backups.py
- data_sources.py
- post
- ddl_export.py
- forbidden
- .RenderChildren
- BackupExecutor
- CONTRIBUTING.md
- models.py
- introspection.py
- Deployer HTTP API v1
- IShellLinkW
- test_backup_crypto.py
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
- github.py
- deployments.py
- sqlalchemy
- DataSource
- FakeFirestore
- cloud_deploy.py
- services
- device_moves.py
- QueryEditor.tsx
- Deployments (push-to-deploy) — phase 4
- tests/test_query_console.py
- run_query
- test_remote_access.py
- schema_ops.py
- test_oauth.py
- deployer.ps1
- UninstallForm
- caddy
- options
- install.ps1
- test_agent_skips_calls_whose_deadline_passed_and_keeps_short_calls_free
- export_firestore
- Usability for non-experts
- DumpScanner
- connections.py
- migrate
- BaseModel
- .TestMarkers
- with
- schema.py
- EncryptingWriter
- device_local.py
- conventions.py
- call
- saved_queries.py
- test_firestore.py
- PitrFake
- query-shell
- .Ask
- crowsfoot.ts
- test_repo_detect.py
- FakeDynamo
- Query Console
- keepalive.tests.ps1
- _wrap
- mongo_snapshot
- AwsClient
- fake_primary
- approve_login
- with
- compilerOptions
- shared_fixtures.py
- test_rtdb.py
- not_found
- test_firestore_admin.py
- dependencies
- test_backups_engine.py
- test_cli_client.py
- FakeDockerCli
- pytest
- package.json
- Get-DeployerSource
- mongodb
- compilerOptions
- tunnel
- AuditLog
- worker
- aws_for
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
- test_mcp.py
- test_github_integration.py
- _call_tool
- query_log.py
- FakeSide
- apiSnippets.ts
- HANDOVER.md
- SourceReplica
- backup_engine.py
- readOnly.ts
- error
- client
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
- test_cli_tokens.py
- api
- lan.tests.ps1
- jobs
- SyncConflict
- healthcheck
- redis
- steps
- WizardPage
- apply_changes
- _fake_binlog
- test_api_docs_routes.py
- .ensure_github_role
- test_query_log.py
- FakeExecutor
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
- test_version.py
- linux-installer
- setup-exe
- setup-engine.sh
- test_argon2_runs_at_most_two_at_once
- test_nat_network_runs_against_the_real_botocore_models
- test_real_aws_client_lists_only_tagged_github_roles
- env
- create_input
- key_of
- Schema endpoints, SchemaLink and ConventionIssue
- run_console
- CloudflareError
- record_run
- scripts
- .delete_secret
- test_pagination_accounts_zones_and_records
- services/cli_tokens.py
- redact
- Firestore point-in-time recovery and deletes (as built)
- test_auto_increment_is_persisted_for_restarts_and_repaired_with_a_log
- tsconfig.json
- Invoke-DeployerNative
- vite.config.ts
- runtime.tests.ps1
- KeyRoutesCORS
- docker-entrypoint.sh
- head_db_url
- test_query_route_refuses_anon_keys
- entrypoint.sh
- upgrade.sh
- ci.yml
- release.yml
- deployer-api
- handle
- C2-4 as built: Firebase Realtime Database
- Firestore backups as built: new databases, managed exports, scheduled backups, restores
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

## Communities (243 total, 31 thin omitted)

### Community 0 - "Ui"
Cohesion: 0.07
Nodes (15): Card, BorderColor, Fill, Radius, Glyphs, InputBox, Invalid, ProgressLine (+7 more)

### Community 1 - "react"
Cohesion: 0.05
Nodes (126): isApiError(), isApiStarting(), api, qk, isJobFinished(), useApp(), useApps(), useDeployments() (+118 more)

### Community 2 - "Button"
Cohesion: 0.05
Nodes (149): refresh(), errorMessage(), useDataSources(), ColumnSpec, ForeignKeyAction, JsonValue, Button, ConfirmDialog() (+141 more)

### Community 3 - "types.ts"
Cohesion: 0.02
Nodes (142): ApiKey, ApiKeyConfig, ApiKeyCreateResponse, ApiKeyRole, AppBuild, AppCloud, AppCreated, AppInput (+134 more)

### Community 4 - "source_sync.py"
Cohesion: 0.04
Nodes (32): dec(), enc(), enc_row(), ext(), _failed(), _mongo_change(), MongoStore, _named() (+24 more)

### Community 5 - "oauth.py"
Cohesion: 0.03
Nodes (96): random_token(), sha256_hex(), client_ip(), CaddyProxyHeaders, RefreshToken, change_password(), LinkIn, login() (+88 more)

### Community 6 - "Badge"
Cohesion: 0.06
Nodes (94): useSyncConflict(), useSyncConflicts(), useSyncHistory(), CohostEligibility, ConflictField, DataSource, JsonObject, Replica (+86 more)

### Community 7 - "ApiError"
Cohesion: 0.04
Nodes (94): _detach(), ApiError, _apps_method(), CallContext, capabilities(), clear_link(), collect_metrics(), _cpu_percent() (+86 more)

### Community 8 - "apps.py"
Cohesion: 0.04
Nodes (75): _actions_report(), add_domain(), AppCreate, AppFields, AppUpdate, _audit_cohost(), _audit_database_access(), BuildBody (+67 more)

### Community 9 - "FlatButton"
Cohesion: 0.03
Nodes (40): CheckOption, CheckColor, Checked, Description, CheckRow, Detail, SingleLine, State (+32 more)

### Community 10 - "Device"
Cohesion: 0.05
Nodes (69): AppReplica, Device, DeviceEnrollment, DeviceProjectGrant, approve_enrollment(), _can_remove_copy(), deny_enrollment(), enrollment_by_code_query() (+61 more)

### Community 11 - "react"
Cohesion: 0.04
Nodes (106): hasLiveReplica(), invalidateProjectSources(), useCohostEligibility(), useDataSourcesWithReplicas(), usePlacementOptions(), Backup, BackupCopy, BackupSchedule (+98 more)

### Community 12 - "utcnow"
Cohesion: 0.02
Nodes (187): Backup, BackupCopy, BackupLogSegment, BackupPolicy, new_id(), utcnow(), iso(), _backup_rules() (+179 more)

### Community 13 - "get_connection"
Cohesion: 0.09
Nodes (19): GitHubConnection, github_connect(), github_disconnect(), github_repos(), github_status(), clone_token(), check_can_build(), apps_using() (+11 more)

### Community 14 - "rtdb.py"
Cohesion: 0.10
Nodes (27): _as_doc(), call(), check(), check_key(), check_path(), check_value(), _child(), connection_info() (+19 more)

### Community 15 - "Alert"
Cohesion: 0.05
Nodes (77): useDevices(), CliInputField, Device, DeviceCapabilities, DeviceMetrics, DeviceRole, DeviceSharingMode, EngineAvailability (+69 more)

### Community 16 - "docs/PLATFORMS.md - Platforms and accounts this project uses"
Cohesion: 0.25
Nodes (21): Platform data model (UUID-keyed MariaDB tables), Cloud phases C1-C3 (AWS, Firebase, cloud databases, Actions builds), docs/PLATFORMS.md - Platforms and accounts this project uses, AWS hosting and databases, deployer-boundary IAM permissions boundary, Three AWS IAM policies: DeployerHosting, DeployerDatabases, DeployerRoles, Cloudflare tunnel and DNS, Cloudflare API token (four permissions) (+13 more)

### Community 17 - "SchemaTab.tsx"
Cohesion: 0.05
Nodes (84): useSchema(), ConventionIssue, SourceSchema, SchemaTab, AlertBadge(), AppLayout(), navClass(), Avatar() (+76 more)

### Community 18 - "CloudflareSetup.tsx"
Cohesion: 0.05
Nodes (92): useInstanceSettings(), CloudflareZone, Domain, ImportSummary, ProviderName, ProviderSettings, PublicUrlRequest, PublicUrlResponse (+84 more)

### Community 19 - "ApiError"
Cohesion: 0.09
Nodes (40): check_forbidden(), _coerce_for_column(), _collection(), _db_error(), decode_input(), delete_document(), delete_row(), encode_value() (+32 more)

### Community 20 - "deploys.ts"
Cohesion: 0.07
Nodes (61): useDeployment(), App, AppDetectDraft, AppPatch, AppPreset, AppReplica, AppTarget, CloudTarget (+53 more)

### Community 21 - "GcpClient"
Cohesion: 0.05
Nodes (10): CloudError, _api_error(), GcpClient, _name(), _secret_id(), release(), call(), test_real_google_client_binding_and_provider_requests() (+2 more)

### Community 22 - "mcp.py"
Cohesion: 0.12
Nodes (41): _confirmed(), Ctx, _limit(), _mongo(), _p(), _sql(), t_app_logs(), t_cloud_database_options() (+33 more)

### Community 23 - "services/remote_access.py"
Cohesion: 0.07
Nodes (53): switch_public_url(), tunnel_cname_target(), resync_webhooks(), get_value(), set_value(), _active_hostnames(), add_hostname(), apps_tunnel_name() (+45 more)

### Community 24 - "metrics.py"
Cohesion: 0.05
Nodes (61): get_redis(), dismiss_alert(), get_metrics(), get_summary(), list_alerts(), active(), alert_out(), _api_rule() (+53 more)

### Community 25 - "ControlForm"
Cohesion: 0.05
Nodes (22): ControlForm, IsBusy, State, LogWindow, ToolbarHeight, OutputWindow, ToolbarHeight, RunState (+14 more)

### Community 26 - "routers/cloud.py"
Cohesion: 0.13
Nodes (30): _audit(), _billing(), _confirm_delete(), connect_database(), connection_databases(), create_cloud_backup(), create_connection(), create_database() (+22 more)

### Community 27 - "cloud_deploy.py"
Cohesion: 0.05
Nodes (28): cloud_env(), _export(), instance_role_name(), Publish, poll(), poll(), poll(), resource_name() (+20 more)

### Community 28 - "get_settings"
Cohesion: 0.03
Nodes (68): get_settings(), seal_process(), Settings, get_db(), _check_mariadb(), _check_mongodb(), _check_redis(), health() (+60 more)

### Community 29 - "conftest.py"
Cohesion: 0.06
Nodes (43): get_engine(), set_redis(), auth_headers(), factory(), _clean_state(), client(), db(), fake_provisioning() (+35 more)

### Community 30 - "firestore.py"
Cohesion: 0.07
Nodes (47): _and(), _bad(), call(), check(), check_path(), collection_entity(), collection_ids(), composite_indexes() (+39 more)

### Community 31 - "Job"
Cohesion: 0.05
Nodes (43): Job, cancel_job(), get_job(), _get_job(), list_jobs(), claim(), _clamp(), _error_text() (+35 more)

### Community 32 - "CloudflareClient"
Cohesion: 0.12
Nodes (5): CloudflareClient, _cname_body(), ensure_apps_tunnel(), test_bearer_header_and_verify(), test_tunnel_and_cname_calls()

### Community 33 - "device_rpc.py"
Cohesion: 0.02
Nodes (103): _b64d(), _b64e(), decrypt_secret(), _derive(), encrypt_secret(), encrypt_with_passphrase(), _master_key(), _passphrase_key() (+95 more)

### Community 34 - "deployer.sh"
Cohesion: 0.11
Nodes (78): api_cli(), ask(), assert_restore_folder(), check_port(), cmd_actions(), cmd_autostart(), cmd_backup(), cmd_cli_token() (+70 more)

### Community 35 - "make_app"
Cohesion: 0.06
Nodes (64): Deployment, allocate_port(), _enqueue_job(), handle_push(), logs_key(), rollback(), runtime_logs(), start_deployment() (+56 more)

### Community 36 - "WizardForm"
Cohesion: 0.09
Nodes (22): SettingsDialog, Autostart, KeepAwake, Lan, Port, IconBadge, Color, Kind (+14 more)

### Community 37 - "ThemedForm"
Cohesion: 0.10
Nodes (7): Json, ThemedForm, IsForcedScale, ResetPasswordDialog, SignInAppsDialog, Current, ProviderName

### Community 38 - "services/__init__.py"
Cohesion: 0.03
Nodes (81): _oauth_status(), api_key_not_allowed(), bearer_token(), check_api_key_rate(), decode_access_token(), get_current_user(), require_project_creator(), require_session() (+73 more)

### Community 39 - "dynamo.py"
Cohesion: 0.13
Nodes (17): backup_name(), _backup_out(), check(), connection_info(), display(), entity(), _error(), export_script() (+9 more)

### Community 40 - "App"
Cohesion: 0.05
Nodes (73): App, cloud_url(), generate_dockerfile(), _shell_quote(), artifact_for(), audience(), builds_on_github(), cancel_setup() (+65 more)

### Community 41 - "deployer_cli.py"
Cohesion: 0.06
Nodes (46): _JsonReader, fill_once(), all_apps(), Api, api_from_config(), app_path(), _app_status(), _apply_hint() (+38 more)

### Community 42 - "NotebookConsole.tsx"
Cohesion: 0.03
Nodes (201): isDeviceOffline(), saveBlob(), useQueryLog(), useSavedQueries(), useSavedQueryVersion(), useSavedQueryVersions(), useSourceSchema(), DataSourceKind (+193 more)

### Community 43 - "json.ts"
Cohesion: 0.06
Nodes (27): _find_user(), main(), _oauth_set(), _oauth_write(), _platform_list(), _platform_restore(), _read_json_stdin(), _reset_password() (+19 more)

### Community 44 - "test_source_sync.py"
Cohesion: 0.19
Nodes (17): sync_round(), _conflicts(), _replica(), _seed(), test_changes_flow_both_ways_without_echo(), test_concurrent_edit_opens_conflict_and_other_keys_keep_syncing(), test_delete_versus_update_is_a_conflict(), test_mongo_echo_is_suppressed_by_version() (+9 more)

### Community 45 - "MCP.md"
Cohesion: 0.09
Nodes (49): CI job: Linux installer (install, CLI, update, uninstall), Notes for AI agents (skill copy, MCP, graphify), anon API key (read-only but reads all project data), mcp.call audit logging (tool name, key id, outcome, never arguments), Connecting, JSON-RPC errors, Limits, Per-project MCP server (POST /v1/projects/<id>/mcp) (+41 more)

### Community 46 - "README.md"
Cohesion: 0.06
Nodes (58): Linux support work: install.sh, deployer.sh, linux-installer CI, Docker Engine inside the deployer WSL distro (default runtime), Linux server platform (alternative to Windows PC), Windows PC platform (required unless Linux), docs/SETUP.md - Setting up Deployer, Cloudflare API token permissions (Tunnel Edit, Account Settings Read, DNS Edit, Zone Read), Open from any device with your own domain (Cloudflare tunnel), Deploy an app and connect an AI agent (MCP) (+50 more)

### Community 47 - "re"
Cohesion: 0.07
Nodes (35): backup_delete_summary(), backup_out(), bucket_location(), _call(), check_input_uri(), clone_spec(), collection_ids(), create_schedule() (+27 more)

### Community 48 - "routers/backups.py"
Cohesion: 0.11
Nodes (28): backup_schema(), BackupPatch, create_backup(), _decrypted_download(), delete_backup(), diff_backups(), download_backup(), download_deleted_project_backup() (+20 more)

### Community 49 - "data_sources.py"
Cohesion: 0.10
Nodes (24): validation_error(), check_data_source(), _config_hosts(), create_data_source(), data_source_connection(), DataSourceInput, DataSourceUpdate, delete_data_source() (+16 more)

### Community 50 - "post"
Cohesion: 0.09
Nodes (27): cancel_transfer(), download_transfer(), instance_export(), instance_export_job(), InstanceExportInput, list_transfers(), _my_transfer_job(), _owned_projects() (+19 more)

### Community 51 - "ddl_export.py"
Cohesion: 0.08
Nodes (31): build_bundle(), _comment_safe(), _commented(), ejson(), export_mongo_source(), export_source(), export_sources(), export_sql_source() (+23 more)

### Community 52 - "forbidden"
Cohesion: 0.09
Nodes (25): require_instance_owner(), forbidden(), role_rank(), accept_invite(), create_invite(), get_invite(), _get_member(), InviteCreate (+17 more)

### Community 55 - "CONTRIBUTING.md"
Cohesion: 0.19
Nodes (12): CI job: Windows installer checks and DeployerSetup.exe, Checks (run before opening a PR - CI runs the same), Commits and PRs (tests, Alembic migration, MIT license), Commits and pull requests, Contributing to Deployer, Development setup, Layout, PowerShell conventions (+4 more)

### Community 56 - "models.py"
Cohesion: 0.03
Nodes (122): decrypt_json(), decrypt_with_passphrase(), encrypt_stream_with_passphrase(), Base, load_api_key_access(), load_project_access(), ProjectAccess, require_role() (+114 more)

### Community 57 - "introspection.py"
Cohesion: 0.08
Nodes (36): chunks(), match_entity(), reference_base(), analyze_documents(), visit(), apply_mongo_indexes(), approximate_row_counts(), bson_type_name() (+28 more)

### Community 58 - "Deployer HTTP API v1"
Cohesion: 0.06
Nodes (57): Ground rules, Deployer HTTP API v1, Project API keys (dpl_role_random), Auth endpoints (signup, login, refresh, OAuth), Data sources endpoints and DataSourceInput, Error envelope and common error codes, Export and import endpoints, Health and setup endpoints (+49 more)

### Community 59 - "IShellLinkW"
Cohesion: 0.09
Nodes (5): IShellLinkW, ShellLinkCoClass, MEMORYSTATUSEX, NativeMethods, RECT

### Community 60 - "test_backup_crypto.py"
Cohesion: 0.12
Nodes (23): backup_key(), derive_backup_key(), export_key_material(), import_key_material(), _key_for(), key_id(), _keys_file(), _load_extra_keys() (+15 more)

### Community 61 - "services/cli_inputs.py"
Cohesion: 0.10
Nodes (24): CliInput, get_input(), submit_input(), apps_out(), cancel(), cancel_for_token(), check_pending(), clean_values() (+16 more)

### Community 62 - "deployments.py"
Cohesion: 0.04
Nodes (69): _job_archive(), _job_drop(), _job_prune(), _job_restore(), _job_snapshot(), _job_verify(), client(), _backup_status() (+61 more)

### Community 63 - "cloud_db.py"
Cohesion: 0.04
Nodes (81): encrypt_json(), CloudConnection, DataSource, check_connection(), _cloud_cleanup(), _bad(), check_connection(), config_of() (+73 more)

### Community 64 - "test_cli_inputs.py"
Cohesion: 0.15
Nodes (28): bearer(), _create(), _issue(), _poll(), _submit(), test_app_ids_need_developer(), test_app_ids_submit_with_nothing_typed_changes_nothing(), test_app_ids_write_the_environment() (+20 more)

### Community 65 - "common.ps1"
Cohesion: 0.07
Nodes (45): Invoke-Update(), Get-SystemFacts(), Add-DeployerUserPath(), Assert-DeployerMongoRef(), Assert-DeployerRestoreFolder(), ConvertTo-DeployerArgument(), ConvertTo-DeployerRuntimePath(), ConvertTo-DeployerStateTable() (+37 more)

### Community 66 - "connection"
Cohesion: 0.05
Nodes (71): set_factory(), aws_statements(), site_id(), aws(), aws_key_id(), aws_secret(), _actions(), aws() (+63 more)

### Community 67 - "toast-context.ts"
Cohesion: 0.02
Nodes (80): ApiClientOptions, ApiError, buildQuery(), client, codeForStatus(), createApiClient(), download(), emit() (+72 more)

### Community 68 - "docker-compose.yml"
Cohesion: 0.07
Nodes (50): CI workflow (ci.yml), CI job: API (pytest, ruff), CI job: compose file validation, CI job: dashboard lint, typecheck, test, build, CI job: dashboard and tunnel Docker images, CI job: API image + integration tests (MariaDB, MongoDB, Docker), MongoDB 5.0 to 8.0 upgrade path test, API runtime dependencies (requirements.txt) (+42 more)

### Community 69 - "environment"
Cohesion: 0.13
Nodes (38): environment, ALLOW_SIGNUP, APP_DB_NETWORK, APP_MEM_LIMIT, APP_NETWORK, BACKUP_DIR, CADDY_APPS_DIR, DEPLOYER_ALLOW_INSECURE_PRIMARY (+30 more)

### Community 70 - "data.py"
Cohesion: 0.11
Nodes (24): delete_document(), delete_row(), DocumentInsert, DocumentUpdate, insert_document(), insert_row(), _json_or_text(), list_documents() (+16 more)

### Community 71 - "github.py"
Cohesion: 0.11
Nodes (16): _is_ip(), local_url(), _api(), _call(), _check_token_status(), delete_file(), dispatch_workflow(), GitHubError (+8 more)

### Community 72 - "deployments.py"
Cohesion: 0.03
Nodes (57): get_sessionmaker(), receive_messages(), _record_heartbeat(), _record_progress(), DockerCli, on(), _kill(), _watch() (+49 more)

### Community 73 - "sqlalchemy"
Cohesion: 0.06
Nodes (26): run_migrations_offline(), run_migrations_online(), _url(), upgrade(), upgrade(), upgrade(), upgrade(), upgrade() (+18 more)

### Community 74 - "DataSource"
Cohesion: 0.10
Nodes (32): check_status(), connection_info(), create_collection(), create_table(), delete_document(), delete_row(), drop_collection(), drop_table() (+24 more)

### Community 75 - "FakeFirestore"
Cohesion: 0.12
Nodes (7): set_factory(), FakeAdmin, gcp(), viewer(), FakeFirestore, gcp(), viewer()

### Community 76 - "cloud_deploy.py"
Cohesion: 0.12
Nodes (17): conflict(), Domain, _add_cloud_domain(), add_domain(), cache_control(), check_domain(), _client_for(), content_type() (+9 more)

### Community 77 - "services"
Cohesion: 0.09
Nodes (24): build, extra_hosts, image, mem_limit, networks, restart, volumes, context (+16 more)

### Community 78 - "device_moves.py"
Cohesion: 0.06
Nodes (35): create_move_job(), _device_removed(), dump_source(), _forget_lock(), release_stale_locks(), restore_into(), run_due_cleanups(), run_move() (+27 more)

### Community 79 - "QueryEditor.tsx"
Cohesion: 0.14
Nodes (19): COLLECTION_METHODS, CURSOR_METHODS, cursorLine(), DB_METHODS, editorKeys, EditorMode, editorTheme(), emit() (+11 more)

### Community 80 - "Deployments (push-to-deploy) — phase 4"
Cohesion: 0.11
Nodes (22): static(), mariadb(), target(), local(), API, C1 as built, Cloud connections, Custom domains (+14 more)

### Community 81 - "tests/test_query_console.py"
Cohesion: 0.03
Nodes (82): _call_shell(), _canceller(), _clamp(), _connect_uri(), _enter_read_only(), _error_text(), _first_keyword(), _first_line() (+74 more)

### Community 82 - "run_query"
Cohesion: 0.13
Nodes (6): delete_query_log(), get_query_run(), list_query_log(), _naive_utc(), QueryRequest, run_query()

### Community 83 - "test_remote_access.py"
Cohesion: 0.09
Nodes (36): test_apps_tunnel_created_once_cname_moves_and_ingress(), add_host(), assert_no_secrets(), desired(), link(), test_add_hostname_dns_failure_rolls_back_ingress(), test_add_hostname_existing_record(), test_add_hostname_new() (+28 more)

### Community 84 - "schema_ops.py"
Cohesion: 0.13
Nodes (21): build_create_table(), check_collection_name(), check_identifier(), check_type(), _constraint_name(), create_collection(), create_table(), drop_collection() (+13 more)

### Community 85 - "test_oauth.py"
Cohesion: 0.20
Nodes (18): _callback(), _error_of(), _link_state(), _start(), test_callback_invalid_or_reused_state(), test_callback_provider_error(), test_callback_requires_same_browser(), test_github_requires_primary_verified_email() (+10 more)

### Community 86 - "deployer.ps1"
Cohesion: 0.15
Nodes (44): Assert-Admin(), Get-Context(), Get-OnOffArgument(), Initialize-Engine(), Invoke-Autostart(), Invoke-Backup(), Invoke-Compose(), Invoke-Config() (+36 more)

### Community 87 - "UninstallForm"
Cohesion: 0.06
Nodes (11): Payload, ProcessResult, ScriptOutput, Integration, StartMenuDir, Phase, Confirm, Done (+3 more)

### Community 88 - "caddy"
Cohesion: 0.10
Nodes (22): internal, internal, command, depends_on, entrypoint, image, mem_limit, networks (+14 more)

### Community 89 - "options"
Cohesion: 0.16
Nodes (21): logging, logging, logging, driver, options, logging, logging, logging (+13 more)

### Community 90 - "install.ps1"
Cohesion: 0.13
Nodes (33): Get-InstallerArgumentString(), Get-UbuntuWslImage(), Initialize-WslPlatform(), Install-DockerDesktopRuntime(), Install-WslEngine(), Invoke-DryRun(), Register-ResumeAfterReboot(), Request-Reboot() (+25 more)

### Community 92 - "export_firestore"
Cohesion: 0.10
Nodes (12): database_options(), delete_database(), export_firestore(), export_rtdb(), firestore_backups(), list_cloud_backups(), list_connections(), project_targets() (+4 more)

### Community 93 - "Usability for non-experts"
Cohesion: 0.06
Nodes (31): 11. Docs and the deploy-website skill vs the code, 12. Test suite, CI health, dead code, 13. Non-expert usability walkthrough, 1. API core: auth, sessions, OAuth, invites, members, setup, instance settings, errors, rate limits, 2. Data sources, connections, provisioning, schema, data browser, DDL export, 4. Backups, PITR, jobs, worker, export/import, 5. Host devices, device RPC/agent, co-hosting sync and co-host apps, 7. Installer scripts, WSL engine, compose stack, Caddy, tunnel sidecar, Dockerfiles, CI workflows (+23 more)

### Community 94 - "DumpScanner"
Cohesion: 0.19
Nodes (9): count_insert_rows(), _count_row_tuples(), DumpScanner, test_count_insert_rows_ignores_parens_inside_strings(), test_dump_scanner_collects_point_and_counts(), _scan(), test_count_insert_rows_first_line_only(), test_multi_line_extended_insert_as_written_by_mariadb_11() (+1 more)

### Community 95 - "connections.py"
Cohesion: 0.06
Nodes (40): build_mongo_client(), build_sql_engine(), check_status(), cloud_engine(), _connect_args(), connection_info(), display_for(), _fingerprint() (+32 more)

### Community 96 - "migrate"
Cohesion: 0.11
Nodes (20): condition, depends_on, api, mariadb, migrate, mongodb, redis, condition (+12 more)

### Community 97 - "BaseModel"
Cohesion: 0.09
Nodes (24): AwsCredentials, CloudBackupCreate, CloudDatabaseConnect, CloudDatabaseCreate, CloudRestore, ConnectionCreate, FirebaseCredentials, FirestoreClone (+16 more)

### Community 98 - ".TestMarkers"
Cohesion: 0.11
Nodes (7): CheckResult, Ports, SystemChecks, SystemReport, HasBlocking, HasWarnings, SelfTest

### Community 99 - "with"
Cohesion: 0.10
Nodes (20): with, body, build-args, cache-from, cache-to, context, files, flavor (+12 more)

### Community 100 - "schema.py"
Cohesion: 0.14
Nodes (18): CollectionInput, ColumnReference, ColumnSpec, create_collection(), create_link(), create_table(), delete_link(), _drop() (+10 more)

### Community 101 - "EncryptingWriter"
Cohesion: 0.08
Nodes (12): body(), BackupCryptoError, DecryptingReader, EncryptingWriter, _hkdf(), iter_decrypt(), _nonce(), _read_exact() (+4 more)

### Community 102 - "device_local.py"
Cohesion: 0.13
Nodes (19): device_status(), enroll_cancel(), enroll_start(), enroll_status(), EnrollStart, _ensure_poller(), _link_or_none(), _linked_to() (+11 more)

### Community 103 - "conventions.py"
Cohesion: 0.13
Nodes (38): check_conventions(), check_links(), check_naming(), check_structure(), _field_is_indexed(), _find_field(), is_boolean_type(), is_plural() (+30 more)

### Community 104 - "call"
Cohesion: 0.06
Nodes (23): DeviceExecutor, call(), CallListener, calls_channel(), _error_from(), progress_channel(), publish_control(), publish_progress() (+15 more)

### Community 105 - "saved_queries.py"
Cohesion: 0.12
Nodes (27): SavedQuery, SavedQueryVersion, _add_version(), _check_source(), _check_version(), create_saved_query(), delete_saved_query(), get_saved_query() (+19 more)

### Community 106 - "test_firestore.py"
Cohesion: 0.18
Nodes (20): requirements(), test_google_requirements_include_firestore_backups(), base(), connect(), docs_url(), _fail(), test_app_runner_app_does_not_get_firestore(), test_browse_page_filter_and_subcollections() (+12 more)

### Community 108 - "query-shell"
Cohesion: 0.11
Nodes (18): cap_add, cap_drop, command, cpus, entrypoint, extra_hosts, image, init (+10 more)

### Community 109 - ".Ask"
Cohesion: 0.05
Nodes (34): AppInfo, DefaultInstallDir, ExePath, PowerShellExe, Ref, Repo, RepoUrl, TroubleshootingUrl (+26 more)

### Community 110 - "crowsfoot.ts"
Cohesion: 0.19
Nodes (16): LinkCardinality, RelationshipCardinality, describeEnds(), EndMarker, MARKER_LABEL, MARKER_NOTATION, markerPath(), Vec (+8 more)

### Community 111 - "test_repo_detect.py"
Cohesion: 0.12
Nodes (21): detect(), _detect_dir(), has(), src(), _dirs(), env_keys(), _find_module(), _join() (+13 more)

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
Cohesion: 0.17
Nodes (24): ArtifactWriter, check_db_name(), _index_path(), _latest_oplog_ts(), _load_index(), mariadb_archive_logs(), mariadb_snapshot(), mongo_archive_logs() (+16 more)

### Community 118 - "fake_primary"
Cohesion: 0.18
Nodes (6): fake_primary(), FakePrimary, test_enrollment_poll_never_overwrites_a_cancel(), cancelled_meanwhile(), test_enrollment_poll_race_keeps_approved(), slow_primary()

### Community 119 - "approve_login"
Cohesion: 0.19
Nodes (11): approve_login(), deny_login(), list_tokens(), login_by_code(), LoginAction, LoginPoll, poll_login(), revoke_current() (+3 more)

### Community 120 - "with"
Cohesion: 0.13
Nodes (15): with, cache, cache-dependency-path, cache-from, cache-to, context, if-no-files-found, load (+7 more)

### Community 121 - "compilerOptions"
Cohesion: 0.09
Nodes (21): compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, jsx, lib, module, moduleDetection, moduleResolution (+13 more)

### Community 122 - "shared_fixtures.py"
Cohesion: 0.08
Nodes (17): set_docker(), publish_reply(), reply_channel(), fake_device(), factory(), FakeDevice, add_source(), docker() (+9 more)

### Community 123 - "test_rtdb.py"
Cohesion: 0.12
Nodes (19): base(), connect(), _fail(), FakeRtdb, by(), gcp(), test_browse_lazily_query_and_write_by_path(), test_cloud_run_app_gets_its_realtime_database() (+11 more)

### Community 124 - "not_found"
Cohesion: 0.07
Nodes (51): not_found(), SourceReplica, SyncConflict, SyncVersion, cohosting_eligibility(), create_replica(), delete_replica(), get_conflict() (+43 more)

### Community 125 - "test_firestore_admin.py"
Cohesion: 0.28
Nodes (16): base(), connected(), run_job(), test_backup_schedules_backups_and_restore(), test_create_a_named_firestore_database(), test_delete_a_backup_and_an_export(), test_delete_a_firestore_database_needs_its_name_and_no_protection(), test_failed_operation_leaves_the_source_in_error() (+8 more)

### Community 126 - "dependencies"
Cohesion: 0.11
Nodes (19): dependencies, @codemirror/autocomplete@^6.20.3, @codemirror/lang-javascript@^6.2.5, @codemirror/lang-sql@^6.10.0, @codemirror/language@^6.12.4, @dagrejs/dagre@^3.1.1, lucide-react@^1.46.0, react@^19.3.0 (+11 more)

### Community 127 - "test_backups_engine.py"
Cohesion: 0.15
Nodes (9): binlog_name_with_seq(), binlog_seq(), _mongo_build_oplog(), parse_binlog(), rename_oplog_entry(), _event(), test_binlog_names(), test_parse_binlog_extracts_databases_and_times() (+1 more)

### Community 128 - "test_cli_client.py"
Cohesion: 0.07
Nodes (34): env_of(), cli(), urlopen(), _fail_on(), _fill(), _http_error(), _login(), approve_once() (+26 more)

### Community 130 - "pytest"
Cohesion: 0.20
Nodes (11): to_api_error(), _err(), test_check_permissions_all_ok(), test_check_permissions_missing(), test_check_permissions_no_zones_and_no_accounts(), test_error_mapping(), test_inactive_token_is_auth_failure(), test_invalid_token_maps_to_auth_failed() (+3 more)

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

### Community 136 - "AuditLog"
Cohesion: 0.03
Nodes (46): AuditLog, prune(), create_invite(), create(), env(), sign(), test_app_hostnames(), test_create_list_get_and_roles() (+38 more)

### Community 137 - "worker"
Cohesion: 0.15
Nodes (13): disable, worker, command, entrypoint, extra_hosts, healthcheck, image, mem_limit (+5 more)

### Community 138 - "aws_for"
Cohesion: 0.29
Nodes (14): aws_for(), call(), create_backups(), delete_document(), describe(), insert_document(), _json_object(), key_names() (+6 more)

### Community 139 - "CloudError"
Cohesion: 0.17
Nodes (6): free_blocks(), _nat_alive(), _ours(), _public_subnet(), test_nat_helpers(), What the deploy makes (`cloud_deploy.Publish.nat_connector`, `cloud_aws.ensure_nat_network`)

### Community 140 - "schema_diff.py"
Cohesion: 0.22
Nodes (13): apply_row_counts(), _by_name(), diff_entities(), diff_schemas(), _field_view(), _index_view(), entity(), field() (+5 more)

### Community 141 - "Remote Access & Custom Domains (Cloudflare)"
Cohesion: 0.16
Nodes (22): Commands, Google sign-in for your apps, How it works, Input requests, Sign in, The `deployer` command line (no browser, no sudo), Remote Access & Custom Domains (Cloudflare), Add hostname (ingress rules and proxied CNAME) (+14 more)

### Community 142 - "MarkerKind"
Cohesion: 0.17
Nodes (11): Marker, MarkerKind, Check, Done, Error, None, Other, RebootRequired (+3 more)

### Community 143 - "test_transfer_stream.py"
Cohesion: 0.15
Nodes (9): _dump(), fake_engine(), FakeConn, materialize(), test_bare_numbers_cut_by_the_buffer(), test_lazy_entry_matches_json_load(), test_restore_file_streams_in_bounded_memory(), test_unread_rows_are_skipped_in_order() (+1 more)

### Community 144 - "Core.cs"
Cohesion: 0.15
Nodes (4): DeployerSetup, DeployerCli, Internet, Shell

### Community 145 - "supervisor.sh"
Cohesion: 0.37
Nodes (17): capture_quick_url(), child_alive(), forward_file(), forward_logs(), log(), now_epoch(), now_iso(), pid_alive() (+9 more)

### Community 147 - "tempfile"
Cohesion: 0.09
Nodes (22): BackupEngineError, _check_exit(), _fetch_binlog(), mariadb_defaults_file(), mongo_config_file(), _mongo_load_archive(), mongo_root_uri(), _mongorestore() (+14 more)

### Community 148 - "images"
Cohesion: 0.18
Nodes (12): name, runs-on, steps, strategy, component, context, images, strategy (+4 more)

### Community 149 - "FakeCloudflare"
Cohesion: 0.15
Nodes (5): set_transport(), fake_cf(), fake_cf(), FakeCloudflare, _ok()

### Community 150 - "test_mcp.py"
Cohesion: 0.10
Nodes (11): run(), env(), call(), rpc(), _route_role(), test_data_tools(), test_document_tools(), recorder() (+3 more)

### Community 151 - "test_github_integration.py"
Cohesion: 0.13
Nodes (15): b64(), connect(), docker(), env(), fake_token(), gh(), serve_repo(), test_connect_stores_encrypted_token_and_never_signs_in() (+7 more)

### Community 152 - "_call_tool"
Cohesion: 0.25
Nodes (7): _call_tool(), _check_args(), _dispatch(), _error_result(), RpcError, _text_result(), _visible()

### Community 153 - "query_log.py"
Cohesion: 0.26
Nodes (8): QueryRun, delete_before(), get_run(), list_runs(), prune(), serialize(), _trim_project(), test_prune()

### Community 154 - "FakeSide"
Cohesion: 0.15
Nodes (4): FakeSide, FakeStore, test_reapplying_a_batch_is_a_no_op(), changes()

### Community 155 - "apiSnippets.ts"
Cohesion: 0.23
Nodes (14): buildMcpSnippets(), buildSnippets(), joinUrl(), KEY_PLACEHOLDER, McpInput, render(), Req, requests() (+6 more)

### Community 156 - "HANDOVER.md"
Cohesion: 0.09
Nodes (31): Release workflow (release.yml), Release job: build and push GHCR images, Release job: build, self-test and sign DeployerSetup.exe, Release job: CI gate (calls ci.yml), Everyday commands, Fable 5.1 vetting pass (Fix V-01..V-07, L-01..L-09), For AI agents, Full codebase audit (198 findings, all ticked) (+23 more)

### Community 157 - "SourceReplica"
Cohesion: 0.09
Nodes (27): mark_online(), _merge_warnings(), conflicted(), _replica(), team(), test_conflict_list_diff_and_suggestion(), test_copy_failure_marks_replica_and_drops_partial_copy(), broken_dump() (+19 more)

### Community 158 - "backup_engine.py"
Cohesion: 0.13
Nodes (27): compare_counts(), _load_dump(), feed(), _managed_user_for(), _mariadb_clear(), _mariadb_create_db(), mariadb_current_point(), _mariadb_drop_db() (+19 more)

### Community 159 - "readOnly.ts"
Cohesion: 0.35
Nodes (9): checkMongoReadOnly(), checkReadOnly(), checkSqlReadOnly(), firstKeyword(), MONGO_WRITE_NAMES, MONGO_WRITE_RE, ReadOnlyCheck, splitSqlStatements() (+1 more)

### Community 160 - "error"
Cohesion: 0.05
Nodes (38): rows(), error(), primary(), text(), 8. Windows setup wizard and Deployer Control (C# WinForms), API, C2-1 as built: cloud databases in AWS (RDS / Aurora), Data model (+30 more)

### Community 161 - "client"
Cohesion: 0.17
Nodes (10): client(), set_transport(), test_secret_manager_rest_shapes(), test_firebase_connection_token_exchange_ignores_key_token_uri(), handle(), test_real_client_admin_and_storage_urls(), handle(), test_real_client_storage_objects() (+2 more)

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
Cohesion: 0.07
Nodes (27): save_state(), AppSecrets, failure(), API, API, dashboard, MCP, AWS policy split as built: purpose-sized managed policies, C2-6 as built: internet access for App Runner apps linked to a database (NAT gateway), C2 - cloud databases (what is left) (+19 more)

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
Cohesion: 0.08
Nodes (21): test_mysql_canceller_kills_the_query_from_a_private_pool(), cursor(), Add database -> In your Firebase project, API, Apps on Cloud Run, Browsing, editing, querying, C2-3 as built: Cloud Firestore, C2-5 as built: MCP, transfer, project delete (+13 more)

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

### Community 179 - "SyncConflict"
Cohesion: 0.12
Nodes (12): add_version(), _dt(), key_hash(), latest_versions(), owed_echoes(), _Round, row_hash(), test_history_and_restore() (+4 more)

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
Cohesion: 0.18
Nodes (6): apply_changes(), _project(), same(), Side, Store, 10. Dashboard data features: databases, data browser, schema, query notebook/terminal, backups, devices, co-hosting, jobs, deploys

### Community 185 - "_fake_binlog"
Cohesion: 0.15
Nodes (6): _fake_binlog(), gtid(), __init__(), _read_all(), test_big_row_is_sent_in_a_batch_of_its_own(), test_transaction_bigger_than_a_batch_is_split_across_rounds()

### Community 186 - "test_api_docs_routes.py"
Cohesion: 0.43
Nodes (5): _documented(), _norm(), _paths(), _routes(), test_documented_endpoints_exist()

### Community 187 - ".ensure_github_role"
Cohesion: 0.20
Nodes (5): Dashboard, API, G3 as built: a permissions boundary for the roles Deployer creates, Not verified against real clouds, The fix: `deployer-boundary`, The threat

### Community 188 - "test_query_log.py"
Cohesion: 0.20
Nodes (9): console(), runs(), test_get_and_delete(), test_list_filters_and_permissions(), test_logged_text_masks_passwords(), test_record_run_caps_text_and_trims_the_project(), test_runs_are_logged_with_outcome(), boom() (+1 more)

### Community 189 - "FakeExecutor"
Cohesion: 0.17
Nodes (4): env(), FakeExecutor, test_restore_deleted_source_can_be_retried_after_a_failure(), create()

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
Cohesion: 0.13
Nodes (11): aws(), engine(), Add database -> In your AWS account -> NoSQL, API, Apps on App Runner, Backups (Backups tab), C2-2 as built: DynamoDB, Data model (+3 more)

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

### Community 206 - "test_nat_network_runs_against_the_real_botocore_models"
Cohesion: 0.11
Nodes (7): nat_name(), _unless_gone(), test_ensure_vpc_connector_runs_against_the_real_botocore_models(), test_nat_network_runs_against_the_real_botocore_models(), subnet(), Permissions added (`DeployerDatabases` and `DeployerHosting`, shown in Settings -> Cloud accounts), Shared, reference-counted, removed with the last user

### Community 208 - "env"
Cohesion: 0.67
Nodes (3): WINDOWS_SIGNING_PASSWORD, WINDOWS_SIGNING_PFX, env

### Community 209 - "create_input"
Cohesion: 0.36
Nodes (5): _apps_for(), cancel_input(), _cli_row(), create_input(), poll_input()

### Community 210 - "key_of"
Cohesion: 0.29
Nodes (8): _bad(), _cursor_in(), key_of(), equals(), serialize(), serialize_item(), to_python(), test_values_round_trip()

### Community 211 - "Schema endpoints, SchemaLink and ConventionIssue"
Cohesion: 0.44
Nodes (8): Schema endpoints, SchemaLink and ConventionIssue, Database Planning Conventions, Cross-database link (SQL to NoSQL), Cross-database link rules X1-X3, DDL export (SQL, MongoDB, bundle), ERD crow's-foot notation, Naming rules N1-N6, Structure rules S1-S8

### Community 212 - "run_console"
Cohesion: 0.29
Nodes (4): _cursor_out(), item_out(), plain(), run_console()

### Community 214 - "record_run"
Cohesion: 0.29
Nodes (5): _outcome(), record_run(), add(), add(), 3. Query console, query log, saved queries

### Community 215 - "scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, lint, preview, test, typecheck

### Community 218 - "services/cli_tokens.py"
Cohesion: 0.12
Nodes (19): CliLogin, CliToken, approve(), authenticate(), _clean(), create_login(), expire_if_needed(), issue_token() (+11 more)

### Community 219 - "redact"
Cohesion: 0.33
Nodes (3): redact(), test_redact(), test_redact_is_linear()

### Community 220 - "Firestore point-in-time recovery and deletes (as built)"
Cohesion: 0.33
Nodes (6): API, Deletes (Backups tab; typed name), Firestore point-in-time recovery and deletes (as built), MCP, Not verified against real clouds, Point-in-time recovery (Backups tab -> Point-in-time recovery)

### Community 224 - "Invoke-DeployerNative"
Cohesion: 0.16
Nodes (15): Disable-DeployerLanAccess(), Get-DeployerAcPowerIndex(), Get-DeployerAcPowerTimeoutMinutes(), Get-DeployerLanAddresses(), Get-DeployerLanPorts(), Get-DeployerLanUrls(), Get-DeployerWslIp(), Invoke-DeployerNative() (+7 more)

### Community 225 - "vite.config.ts"
Cohesion: 0.40
Nodes (4): @tailwindcss/vite@^4.3.3, @vitejs/plugin-react@^6.1.1, @tailwindcss/vite, @vitejs/plugin-react

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
Cohesion: 0.22
Nodes (9): Add database -> In your Firebase project -> Realtime Database, API, Apps on Cloud Run, Browsing, editing, querying, C2-4 as built: Firebase Realtime Database, Data model, MCP, Not verified against real clouds (+1 more)

### Community 255 - "Firestore backups as built: new databases, managed exports, scheduled backups, restores"
Cohesion: 0.29
Nodes (7): API, Firestore backups as built: new databases, managed exports, scheduled backups, restores, Managed exports and imports (Backups tab -> Exports to Cloud Storage), MCP, Not verified against real clouds, Permissions added (Settings -> Cloud accounts guide), Scheduled backups and restores (Backups tab)

## Knowledge Gaps
- **145 isolated node(s):** `deployer-api`, `RFC-5987`, `RFC-4180`, `Checking`, `Running` (+140 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 2551 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **31 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ApiError` connect `ApiError` to `pytest`, `source_sync.py`, `oauth.py`, `apps.py`, `AuditLog`, `Device`, `aws_for`, `utcnow`, `get_connection`, `rtdb.py`, `ApiError`, `GcpClient`, `mcp.py`, `services/remote_access.py`, `_call_tool`, `metrics.py`, `routers/cloud.py`, `query_log.py`, `get_settings`, `conftest.py`, `backup_engine.py`, `firestore.py`, `Job`, `device_rpc.py`, `SourceReplica`, `services/__init__.py`, `dynamo.py`, `App`, `json.ts`, `test_source_sync.py`, `re`, `routers/backups.py`, `data_sources.py`, `post`, `SyncConflict`, `forbidden`, `models.py`, `introspection.py`, `test_query_log.py`, `services/cli_inputs.py`, `FakeExecutor`, `cloud_db.py`, `test_cli_inputs.py`, `data.py`, `github.py`, `deployments.py`, `DataSource`, `cloud_deploy.py`, `device_moves.py`, `create_input`, `run_query`, `key_of`, `run_console`, `tests/test_query_console.py`, `record_run`, `schema_ops.py`, `services/cli_tokens.py`, `export_firestore`, `test_auto_increment_is_persisted_for_restarts_and_repaired_with_a_log`, `connections.py`, `schema.py`, `device_local.py`, `call`, `saved_queries.py`, `approve_login`, `test_github_integration.py`, `shared_fixtures.py`, `not_found`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Are the 149 inferred relationships involving `ApiError` (e.g. with `_oauth_set()` and `_platform_restore()`) actually correct?**
  _`ApiError` has 149 INFERRED edges - model-reasoned connections that need verification._
- **What connects `deployer-api`, `RFC-5987`, `RFC-4180` to the rest of the system?**
  _145 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Ui` be split into smaller, more focused modules?**
  _Cohesion score 0.074034902168165 - nodes in this community are weakly interconnected._
- **Why does `WizardForm` connect `WizardForm` to `Ui`, `.TestMarkers`, `ThemedForm`, `FlatButton`, `.Ask`, `SetupOptions`, `Core.cs`, `UninstallForm`, `ControlForm`, `IShellLinkW`, `WizardPage`, `Job`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 300 inferred relationships involving `DataSource` (e.g. with `create_replica()` and `_replica()`) actually correct?**
  _`DataSource` has 300 INFERRED edges - model-reasoned connections that need verification._
- **Should `react` be split into smaller, more focused modules?**
  _Cohesion score 0.05314357773374167 - nodes in this community are weakly interconnected._