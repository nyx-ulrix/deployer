# Security review - 2026-09-28

**Scope:** push-to-deploy apps and co-hosting: `api/app/routers/apps.py`, `routers/integrations.py`,
`routers/mcp.py`, `services/deployments.py`, `app_runner.py`, `cohost_apps.py`, `device_apps.py`,
`cohosting.py`, `source_sync.py`, `github.py`, the apps-tunnel parts of `services/remote_access.py`
(`ensure_apps_tunnel`, `move_app_hostnames`, `desired_state`, `on_apps_tunnel`, `add_hostname`) and
`deploy/tunnel/supervisor.sh`.

**Method:** manual code review against the documented behaviour (`SECURITY.md`, `docs/DEPLOYMENTS.md`,
`docs/COHOSTING.md`, `docs/MCP.md`), following user input from the HTTP/MCP/webhook/device-RPC
boundary to git, docker, Caddy files, GitHub/Cloudflare calls and logs. Checked for authorization
gaps, cross-project ids, secret leaks, SSRF, argument injection, path traversal, header injection
and unbounded inputs. Every fix has a regression test (in `api/tests/`).

## Findings

| ID | Area / file | Finding | Severity | Status |
|---|---|---|---|---|
| SR-1 | `services/deployments.py` `build_image` (main server and co-host devices) | `root_dir` was checked lexically only: a symlink in the repository (`root_dir` -> `/`) or a `Dockerfile` symlink could point the build context or the Dockerfile at the worker's own filesystem. The worker is root and would send those files to BuildKit (a Dockerfile can then `COPY` them into the served image) or echo them in build errors. | High | Fixed: both paths are resolved with `realpath` and must stay inside the checkout. Test `test_deployments.py::test_build_image_refuses_symlinks_out_of_the_checkout` |
| SR-2 | `services/deployments.py` `handle_push`, `services/app_runner.py` `git_checkout` | The webhook's `after` value went unvalidated into `git fetch --depth 1 origin <sha>` and `git checkout --detach <sha>` in the root worker. Developers can reveal the webhook secret, so a signed payload could inject git options (`--upload-pack=...`, `--pathspec-from-file=...`). | Medium | Fixed: `handle_push` keeps only a 40-hex sha (otherwise the branch head is deployed); `git_checkout` refuses anything but 7-40 hex characters. Test `test_deployments.py::test_commit_sha_never_reaches_git_as_an_option` |
| SR-3 | `routers/apps.py` `update_app` | A developer could point `repo_url` at a host they control: the stored `repo_token` (set by someone else, never returned by the API) would be sent there by git's credential helper. | Medium | Fixed: moving the repository to another host without sending a token in the same request drops the stored token. Test `test_apps_api.py::test_repo_token_is_dropped_when_the_repository_host_changes` |
| SR-4 | `routers/mcp.py` | The app tools (`list_apps`, `get_app`, `deployment_status`, `app_logs`) were open to `anon` keys, which are meant for public clients, while the HTTP app routes refuse API keys. Anyone holding a site's anon key could read build logs, runtime logs and app settings. | Medium | Fixed: the app tools need a `service` key (or a developer+ session). Test `test_mcp.py::test_app_tools` (and `test_tools_list_depends_on_role`) |
| SR-5 | `routers/apps.py` GitHub webhook, `routers/mcp.py` | The unauthenticated webhook read the whole body into memory before checking its HMAC; the MCP endpoint read the whole body before its 1 MB check. | Medium | Fixed: bodies are streamed and cut at 5 MB (webhook, 413 `payload_too_large`) / 1 MB (MCP). Tests `test_apps_api.py::test_webhook_body_is_capped`, `test_mcp.py::test_malformed_requests` |
| SR-6 | `services/github.py` `parse_repo` | Owner/repository names `.` and `..` were accepted, so dot segments could re-route GitHub API paths (`/repos/{o}/{r}/hooks`). Only the caller's own GitHub token was ever used. | Low | Fixed: such URLs are not GitHub repositories. Test `test_github_integration.py::test_parse_repo_refuses_dot_segments` |
| SR-7 | `services/app_runner.py` `run_container` | App variables are handed to `docker run -e KEY` through the docker CLI's own environment, so names like `PATH`, `LD_PRELOAD` or `DOCKER_HOST` also affect that CLI process in the worker. | Low | Accepted: turning this into code execution needs an attacker-controlled file at a known path in the worker (build directories are random and not shared); `DOCKER_HOST` only redirects the app's own environment, which its code already sees. Revisit if such a path appears. |
| SR-8 | `routers/apps.py` `repo_url` | Any `https://` host is accepted, including private addresses, so git in the worker can be pointed at internal HTTPS services. | Low | Accepted: https only (no `file://`, `ext::`, ssh), no submodules, git output is short and redacted; creating apps already requires the developer role. |
| SR-9 | apps (design) | Revealing env values is admin-only, but developers can edit build/start commands and read the app's variables, `DEPLOYER_API_KEY` and (with database access) `DEPLOYER_DB_*` from inside the running app. | Info | Accepted: developers are trusted to run code in their apps (`SECURITY.md` "Worker trust", "App database access"); the admin-only switches decide what the app receives. |
| SR-10 | `routers/apps.py` `add_domain`, `remote_access.add_hostname` | Project admins add app hostnames through the instance owner's Cloudflare link, in any zone of that account, and may overwrite existing DNS records (`overwrite: true`). | Info | Accepted: documented (`docs/DEPLOYMENTS.md` API table); hostnames already configured in Deployer cannot be taken over (409 `domain_exists`). Link only accounts whose zones project admins may use. |

## Hardening added in the same phase

- Per-API-key rate limit in `deps.load_api_key_access` (default 600/min, instance setting
  `api_key_rate_limit`), separate from the MCP tool-call limit; every `429 rate_limited` now also sends
  `Retry-After`. Test `test_data_api_keys.py::test_per_key_rate_limit`.
- Alert webhook URL (`alert_webhook_url`): https only, no userinfo/fragment, max 500 characters,
  stored encrypted, no redirects followed, URL never logged, payload without job error text.
  Tests in `test_monitoring.py`.

## Checked and found OK

- **Cross-project ids:** apps, deployments (including the `before` cursor), app domains, replicas
  (`device_id` on logs) and `api_key_id` are all checked against their parent project/app.
- **Roles:** `database_access`, `cohost` and `cohost_share_repo_access` are admin-only on create and
  update; env reveal, delete and hostnames are admin+; the GitHub connection is only ever the caller's
  own. MCP tools call the same route functions, audit the tool name without arguments.
- **Co-host devices:** `apps.deploy` validates every parameter (uuid ids, hex sha, https URL, branch,
  `root_dir`, env names, token shape, sizes) and refuses `DEPLOYER_API_KEY` / `DEPLOYER_DB_*`; the
  main server withholds those plus any value containing its database secrets; a device only reports
  a tunnel token fingerprint. `sync.*` input: table/column names checked against
  `information_schema` and quoted, values bound, `force` cannot come from a device.
- **git/docker argv:** no shell; `git clone ... --branch <b> -- <url>`, branch names cannot start with
  `-`; the clone token travels through a credential-helper environment variable and is redacted from
  logs and job errors; labels and container names come from uuids and slugs.
- **Caddy files and headers:** hostnames are IDNA-normalized and label-checked (no CR/LF, `/`, `:` or
  `*`), ports are integers, so generated site blocks cannot be injected into.
- **Tunnel sidecar:** connector tokens reach cloudflared only as `TUNNEL_TOKEN`, `desired.json` is
  0600, devices receive only the apps tunnel's token (validated), never the dashboard tunnel token or
  the Cloudflare API token.
- **Bounds:** app fields have `max_length`s, env is capped at 64 KB, logs at 1 MB (deployment) / 500
  lines (runtime), device RPC lists and env are bounded.
- **Build sandbox:** a repository `Dockerfile` can use any `RUN` flags, but `--network=host` and
  `--security=insecure` need BuildKit entitlements that Deployer never requests (`docker build`
  runs without `--allow`).
