# Contributing to Deployer

Thanks for helping! Deployer is built to run on ordinary Windows PCs owned by people who may not be
developers, so reliability, low resource use and clear error messages matter as much as features.

## Ground rules

- **No credentials in the repository or images** - no API keys, OAuth client IDs, tokens or default
  passwords. Everything secret is generated at install time or entered by the person installing.
- Nothing phones home.
- The dashboard, webhooks and AI agents all go through the HTTP API (`docs/API.md`). Keep the API
  contract and the docs in sync in the same pull request.

## Layout

| Path | What |
|---|---|
| `api/` | FastAPI control plane (Python 3.12), Alembic migrations, tests |
| `dashboard/` | React + TypeScript + Vite SPA |
| `deploy/` | `docker-compose.yml`, `docker-compose.dev.yml`, `Caddyfile`, `.env.example`, `mongodb/` (replica-set entrypoint), `tunnel/` (cloudflared sidecar image) |
| `installer/` | `install.ps1`, `deployer.ps1`, `lib/common.ps1`, `wsl/setup-engine.sh`, `windows/` (`DeployerSetup.exe` sources + `build.ps1`) |
| `docs/` | Architecture, API contract, schema conventions, host devices, backups, remote access |

## Development setup

See *Development* in [README.md](README.md). In short:

```bash
cp deploy/.env.example deploy/.env
docker compose -f deploy/docker-compose.yml up --build
```

## Checks (run before opening a PR - CI runs the same)

- API: `cd api && pytest`
- Dashboard: `cd dashboard && npm run lint && npm run typecheck && npm run test -- --run && npm run build`
- Compose: `docker compose -f deploy/docker-compose.yml --env-file deploy/.env.example config`
  (also with `-f deploy/docker-compose.dev.yml`)
- Installer (Windows PowerShell):
  ```powershell
  Get-ChildItem installer -Recurse -Filter *.ps1 | ForEach-Object {
    $e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$null, [ref]$e); $e }
  Invoke-ScriptAnalyzer -Path installer -Recurse -Severity Error
  powershell -ExecutionPolicy Bypass -File installer\windows\build.ps1
  dist\DeployerSetup.selftest.exe /selftest dist\selftest
  ```
- `bash -n` on every `*.sh` (`installer/wsl/`, `deploy/mongodb/`, `deploy/tunnel/`, `api/docker-entrypoint.sh`)

## PowerShell conventions

- Target **Windows PowerShell 5.1** (no `??`, `?.`, ternaries or `&&`).
- Keep `.ps1` files **ASCII-only**: 5.1 reads BOM-less files in the ANSI code page.
- Don't redirect native stderr with `2>&1`; use `Invoke-DeployerNative` from `lib/common.ps1`.
- Every user-facing failure should say what to do next.

## Commits and pull requests

- Small, focused PRs with a clear description of *why*.
- Add or update tests for behaviour changes.
- Database schema changes need an Alembic migration and must keep export/import working.
- By contributing you agree your work is released under the MIT license.
