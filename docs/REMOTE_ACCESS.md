# Remote Access & Custom Domains (Cloudflare)

By default Deployer is only reachable on the PC itself (`http://localhost:8080`) or the LAN. To use it
from anywhere with **your own domain** (e.g. `https://deployer.example.com`) the instance owner links
**their own Cloudflare account** in *Settings → Domains & remote access*. Deployer then creates a
Cloudflare Tunnel and DNS records for you. No router port forwarding, no certificates to manage, and
nothing from the Deployer authors is involved.

## Options

| Option | Needs | Result |
|---|---|---|
| **Cloudflare Tunnel + your domain** (recommended) | A free Cloudflare account with your domain added as a zone, and an API token you create | Stable `https://<hostname>` for the dashboard, API, OAuth callbacks and host devices |
| **Quick tunnel** (testing) | Nothing | Random `https://<words>.trycloudflare.com` URL that changes whenever the tunnel restarts. Not suitable for Google/GitHub sign-in or host devices. |
| Off (default) | – | localhost / LAN only |

## API token (created by the user)

Create at <https://dash.cloudflare.com/profile/api-tokens> → *Create Custom Token* with:

| Scope | Permission | Name reported in `missing_permissions` |
|---|---|---|
| Account → **Cloudflare Tunnel** | Edit | `Account / Cloudflare Tunnel / Edit` |
| Account → **Account Settings** | Read | `Account / Account Settings / Read` |
| Zone → **DNS** | Edit | `Zone / DNS / Edit` |
| Zone → **Zone** | Read | `Zone / Zone / Read` |

Account resources: the account that owns the domain. Zone resources: the specific zone(s) (or all
zones). The token is stored encrypted with `MASTER_KEY`; it can be replaced or removed at any time.
Deployer never asks for the Cloudflare password. (Cloudflare's API reference also accepts the newer
"Cloudflare One Connector: cloudflared Write" permission in place of "Cloudflare Tunnel Edit".)

**Pre-filled template link.** Cloudflare supports
[token template URLs](https://developers.cloudflare.com/fundamentals/api/how-to/account-owned-token-template/)
(`?permissionGroupKeys=<url-encoded JSON>&accountId=*&zoneId=all&name=...`). Documented keys exist for
`account_settings`, `zone` and `dns`, but **not for Cloudflare Tunnel**, so the dashboard link pre-fills
three permissions and tells the user to add *Account → Cloudflare Tunnel → Edit* by hand:

```text
https://dash.cloudflare.com/profile/api-tokens?permissionGroupKeys=%5B%7B%22key%22%3A%22account_settings%22%2C%22type%22%3A%22read%22%7D%2C%7B%22key%22%3A%22zone%22%2C%22type%22%3A%22read%22%7D%2C%7B%22key%22%3A%22dns%22%2C%22type%22%3A%22edit%22%7D%5D&accountId=%2A&zoneId=all&name=Deployer
```

## How linking works

1. `verify`: `GET /client/v4/user/tokens/verify` (invalid/expired → `cloudflare_auth_failed`), then
   harmless reads only: `GET /accounts` (empty/403 → Account Settings), `GET /zones?account.id=` per
   account (403, or no zones at all → Zone), `GET /accounts/{id}/cfd_tunnel?is_deleted=false`
   (403 → Cloudflare Tunnel) and `GET /zones/{id}/dns_records?per_page=1` for one zone per account
   (403 → DNS). Edit access can't be tested without writing, so a token with only *Read* on Tunnel/DNS
   passes `verify` and fails later with `cloudflare_permission_missing`. `ok` is true when nothing is
   missing.
2. `link`: find or create a remotely-managed tunnel named `deployer-<first 8 chars of instance_id>`
   (`instance_id` is a random setting generated once; the stored tunnel id is tried first, then
   `GET .../cfd_tunnel?name=`, else `POST /accounts/{account_id}/cfd_tunnel` with
   `config_src: "cloudflare"`), fetch its connector token
   (`GET /accounts/{account_id}/cfd_tunnel/{tunnel_id}/token`), put the ingress configuration and hand
   the token to the **tunnel sidecar** (below). Sets `remote_access_mode` to `cloudflare`. Relinking the
   same account reuses the tunnel; linking a different account while hostnames exist →
   `409 already_linked`.
3. `add hostname`: the hostname is normalised (lower-case, trailing dot removed, IDNA → punycode) and
   must equal the zone name or end with `.<zone>`; the zone must belong to the linked account. Existing
   records with that name are listed first: if any exist → `409 dns_record_exists` (details: `records`)
   unless `overwrite: true` (a CNAME already pointing at this tunnel is simply reused). Then
   `PUT /accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations` with ingress rules for every
   active dashboard hostname → `http://caddy:8081` (plus the final `http_status:404` rule), then create
   a proxied `CNAME <hostname> → <tunnel_id>.cfargotunnel.com` (with `overwrite`, a single existing
   CNAME is updated in place; other records are deleted first). If the DNS step fails, the ingress
   change is rolled back. The domain is stored as `active`. Removing a hostname deletes its DNS record
   and rewrites the ingress rules.

   Why port **8081**: Caddy's `:8081` listener is not published on the host and is only used by the
   tunnel. It trusts `X-Forwarded-Proto: https` from cloudflared (so the API sees https) and takes the
   visitor IP from `Cf-Connecting-Ip` (used for login rate limiting); the LAN-facing `:8080` listener
   trusts no forwarded headers.
4. When the connector reports healthy, the owner can click **Use as public URL**: `public_url` changes
   to `https://<hostname>`, and the dashboard lists the new Google/GitHub callback URLs to paste into
   their OAuth apps (both old and new URLs can be registered during the switch). Requires an `active`
   domain and mode `cloudflare` (`409 domain_not_active` / `tunnel_not_active`); `{quick:true}`
   requires a running quick tunnel with a known URL (`409 quick_tunnel_not_ready`); `{local:true}`
   sets `http://localhost:<port>`.
5. `unlink`: optionally delete Deployer's DNS records (only the records it created) and the tunnel
   (the connector is stopped and stale connections cleaned up first), then clear all `cloudflare_*`
   settings and dashboard domains and stop the connector. If a Cloudflare call fails nothing is
   unlinked (retry, or unlink with both flags false). If `public_url` pointed at a removed hostname it
   reverts to `http://localhost:<port>`; the same happens when that hostname is deleted, and when quick
   mode is turned off while `public_url` is a `trycloudflare.com` URL. `<port>` is `DEPLOYER_HTTP_PORT`
   (passed to the API by compose), else the port of a `localhost` request, else 8080.

`POST /quick {enabled:true}` switches the connector to a quick tunnel (a linked tunnel stays configured
but its connector stops); `{enabled:false}` returns to `cloudflare` if linked, else `off`.

`GET /v1/instance/remote-access` reads the tunnel's live `status` (`GET .../cfd_tunnel/{id}`) and counts
its connections (`GET .../cfd_tunnel/{id}/connections`, sum of `conns`); `token_valid` is `false` when
Cloudflare rejects the stored token and `null` when Cloudflare can't be reached. It also lists the
linked account's `zones` (`GET /zones?account.id=`, cached in Redis for 5 minutes and refreshed by
`link`) so the dashboard can offer them after a reload without asking for the token again; while
Cloudflare can't be reached and nothing is cached, `zones` is `[]`. It also rewrites `desired.json` if
it is missing or out of date (and so does API startup).

## Tunnel sidecar

Compose service `tunnel` (image `deployer-tunnel`, built from `deploy/tunnel/`): Alpine + `jq` + a
pinned `cloudflared` (currently 2026.9.1, linux-amd64) whose SHA256 is verified during the build; the
version and checksum are `ARG`s in the Dockerfile, taken from the "SHA256 Checksums" section of the
GitHub release notes. It runs as uid 10001 with a read-only root filesystem, `cap_drop: ALL`, a tmpfs
`/tmp`, no published ports and only the `public` network, and shares the `tunnel_state` volume with the
API (both images own `/tunnel` as uid 10001, so either can initialise a fresh volume):

| File (written by) | Content |
|---|---|
| `/tunnel/desired.json` (API) | `{"mode":"off"}` \| `{"mode":"cloudflare","token":"..."}` \| `{"mode":"quick"}` (mode 0600) |
| `/tunnel/status.json` (sidecar) | `{"mode", "running", "pid", "started_at", "quick_url", "last_error", "updated_at"}` |

The supervisor (`deploy/tunnel/supervisor.sh`, POSIX sh) polls `desired.json` every 3 s and (re)starts
`cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20241 run` (token in `TUNNEL_TOKEN`) or
`cloudflared tunnel --no-autoupdate --metrics 127.0.0.1:20241 --url http://caddy:8081`. A change of
mode or token stops the old process (SIGTERM, SIGKILL after 10 s). If cloudflared exits it is restarted
after 1, 2, 4 … 60 s (reset after 60 s of stable running); `last_error` holds the exit code and the last
`ERR` log line. The quick-tunnel URL is parsed from cloudflared's output, which is also forwarded to
`docker logs`. The token is passed via the `TUNNEL_TOKEN` environment variable of the child process,
never on the command line, and is never logged. An unreadable or invalid `desired.json` keeps the
current state and sets `last_error`. `status.json` is replaced atomically on every change and at least
every 15 s; the API treats a status older than 45 s as "sidecar not running". The API has no Docker
socket access.

## Data model

- `instance_settings` keys: `cloudflare_api_token` (secret), `cloudflare_account_id`,
  `cloudflare_account_name`, `cloudflare_tunnel_id`, `cloudflare_tunnel_name`,
  `cloudflare_tunnel_token` (secret), `remote_access_mode` (`off`/`cloudflare`/`quick`), `instance_id`.
- API process settings: `TUNNEL_STATE_DIR` (default `/tunnel`), `DEPLOYER_HTTP_PORT`.
- `domains`: `id, hostname (unique), provider ("cloudflare"), zone_id, zone_name, dns_record_id,
  target_type ("dashboard" now; "project" reserved for push-to-deploy), project_id (nullable), status
  ("pending"/"active"/"error"), status_message, created_at, updated_at`.

## API (instance owner only)

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/v1/instance/remote-access` | – | `RemoteAccess` |
| POST | `/v1/instance/remote-access/cloudflare/verify` | `{api_token}` | `{ok, accounts:[{id,name}], zones:[{id,name,account_id,status}], missing_permissions:string[]}` |
| POST | `/v1/instance/remote-access/cloudflare/link` | `{api_token, account_id}` | `RemoteAccess` |
| POST | `/v1/instance/remote-access/cloudflare/hostnames` | `{zone_id, hostname, overwrite?}` | `Domain` |
| DELETE | `/v1/instance/remote-access/cloudflare/hostnames/{domain_id}` | – | `{ok:true}` |
| POST | `/v1/instance/remote-access/cloudflare/unlink` | `{delete_dns:boolean, delete_tunnel:boolean}` | `RemoteAccess` |
| POST | `/v1/instance/remote-access/quick` | `{enabled:boolean}` | `RemoteAccess` |
| POST | `/v1/instance/remote-access/public-url` | `{domain_id}` \| `{quick:true}` \| `{local:true}` | `{settings: InstanceSettings, oauth_callbacks:{google:string, github:string}, previous_public_url}` |

```ts
type Domain = {
  id: string; hostname: string; zone_id: string; zone_name: string;
  target_type: "dashboard" | "project"; project_id: string | null;
  status: "pending" | "active" | "error"; status_message: string | null; url: string;
};
type RemoteAccess = {
  mode: "off" | "cloudflare" | "quick";
  public_url: string;
  connector: { running: boolean; started_at: string | null; last_error: string | null };
  cloudflare: {
    linked: boolean; token_valid: boolean | null;
    account: { id: string; name: string } | null;
    tunnel: { id: string; name: string; status: string | null; connections: number } | null;
    domains: Domain[];
    zones: { id: string; name: string; account_id: string; status: string }[];  // of the linked account
  };
  quick: { url: string | null };
};
```

Errors:

| Code | HTTP | When |
|---|---|---|
| `cloudflare_auth_failed` | 400 | Cloudflare rejected the token (401, or 400 with an auth error code). Deliberately not 401, so the dashboard doesn't mistake it for its own session expiring. |
| `cloudflare_permission_missing` | 400 | Cloudflare answered 403; `details.missing_permissions` lists the permission name(s) |
| `cloudflare_api_error` | 502 | Cloudflare unreachable or any other failure; message from Cloudflare |
| `account_not_found` | 404 | `link` with an account the token can't read |
| `zone_not_found` | 404 | Unknown zone, or a zone outside the linked account |
| `hostname_not_in_zone` | 422 | Hostname is neither the zone apex nor a subdomain of it |
| `validation_error` | 422 | Invalid hostname (`details.field`), or not exactly one of `domain_id`/`quick`/`local` |
| `dns_record_exists` | 409 | `details.records: [{id, type, content}]`; retry with `overwrite: true` |
| `domain_exists` | 409 | Hostname already configured |
| `not_linked` | 409 | No Cloudflare account linked |
| `already_linked` | 409 | Linking a different account while hostnames exist |
| `domain_not_active`, `tunnel_not_active`, `quick_tunnel_not_ready` | 409 | `public-url` preconditions |

No endpoint ever returns the API token or the connector token.

## Troubleshooting

- **`connector.last_error` says the sidecar hasn't reported / isn't running**: the `tunnel` container
  isn't running. Check `docker compose ps tunnel` and `docker compose logs tunnel`, then
  `docker compose up -d tunnel`.
- **"Could not write /tunnel/desired.json"**: the API can't write the shared volume (for example a
  volume first created by an image without `/tunnel`, so it is owned by root). Fix it with
  `docker compose run --rm --no-deps --user 0 --cap-add CHOWN --entrypoint sh tunnel -c "chown -R 10001:10001 /tunnel"`,
  then reload the settings page.
- **"cloudflared exited with code 1" mentioning an invalid token or unauthorized**: the tunnel was
  deleted or its token rotated in the Cloudflare dashboard. Link again (same account) to fetch a fresh
  token.
- **Tunnel status `inactive`/`down` with 0 connections**: the PC can't reach Cloudflare outbound
  (port 7844 UDP/TCP). Firewalls often block QUIC; cloudflared falls back to HTTP/2 by itself.
- **Browser shows Cloudflare error 1033**: DNS points at the tunnel but no connector is running (see
  above). **Error 502/504**: cloudflared can't reach `caddy:8081`; make sure the `caddy` container is
  running with the current `deploy/Caddyfile`.
- **`missing_permissions` right after creating the token**: edit the token in Cloudflare and check that
  its account and zone resources include the account and zone you picked.
- **`dns_record_exists`**: an existing record (e.g. an old A record) would be replaced. Make sure it
  isn't in use, then retry with *Overwrite*.
- **Signed out or login loop after switching the public URL**: cookies become `Secure` when `public_url`
  is https, so use the dashboard at the new `https://` address. To go back, open
  `http://localhost:<port>` and choose *Use local URL* (`{local:true}`).
- **Google/GitHub sign-in fails after the switch**: add the new callback URLs shown by the dashboard to
  your OAuth apps. Quick tunnel URLs change on every restart, so don't use them for OAuth.
- **Quick tunnel never shows a URL**: `trycloudflare.com` is rate limited; the reason is in
  `docker compose logs tunnel`.
