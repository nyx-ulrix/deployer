"""The Google REST calls behind the Firebase hosting targets and databases (docs/CLOUD.md): Firebase Hosting
v1beta1, Cloud Run Admin v2, Artifact Registry v1, Cloud Firestore v1 and the Firebase Realtime Database
(management v1beta + the database's own REST API), with a service-account key.

No Google SDK: the OAuth token is a JWT-bearer grant signed with the key's RSA private key (PyJWT +
cryptography, already dependencies) and every call is plain httpx. Rules:

- the token endpoint is always `TOKEN_URL`; the key file's own `token_uri` is ignored (a pasted key
  must not be able to send a signed assertion anywhere else);
- every URL is built from constants plus validated ids; the only URLs taken from a response are
  long-running operation names (checked against `_OPERATION`) and Hosting's upload URL (must start
  with `UPLOAD_PREFIX`), so the bearer token only ever goes to Google; a Realtime Database URL (from the
  management API, stored on the source) must match `_RTDB_URL` - a Firebase database host - before the
  database-scoped token is sent to it;
- the private key and access tokens are never logged or put in `CloudError` messages.

`GcpClient` is replaced by a fake in tests (`set_factory`); the token exchange itself is tested with
`set_transport` (httpx.MockTransport).
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.errors import CloudError

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = "https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/firebase"
FIREBASE = "https://firebase.googleapis.com/v1beta1"
HOSTING = "https://firebasehosting.googleapis.com/v1beta1"
RUN = "https://run.googleapis.com/v2"
REGISTRY = "https://artifactregistry.googleapis.com/v1"
FIRESTORE = "https://firestore.googleapis.com/v1"
STORAGE = "https://storage.googleapis.com/storage/v1"
RTDB_MANAGEMENT = "https://firebasedatabase.googleapis.com/v1beta"
IAM = "https://iam.googleapis.com/v1"
SECRETS = "https://secretmanager.googleapis.com/v1"
SECRET_ACCESSOR = "roles/secretmanager.secretAccessor"
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
# The Realtime Database's own REST API takes a token with these scopes (docs/CLOUD.md "C2-4").
RTDB_SCOPES = "https://www.googleapis.com/auth/firebase.database https://www.googleapis.com/auth/userinfo.email"
RTDB_MAX_BYTES = 32 * 1024 * 1024  # one Realtime Database read: bigger answers are refused, not buffered
UPLOAD_PREFIX = "https://upload-firebasehosting.googleapis.com/"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
CHANNEL_TTL = "604800s"  # preview channels expire after 7 days

PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
REGION_RE = re.compile(r"^[a-z]+-[a-z]+\d{1,2}$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_SA_EMAIL = re.compile(r"^[a-z0-9-]{6,30}@[a-z0-9-]+\.iam\.gserviceaccount\.com$")
_SECRET_ID = re.compile(r"^[A-Za-z0-9_-]{1,255}$")  # Secret Manager ids: deployer-<slug>-<id8>-<VARIABLE>
_OPERATION = re.compile(r"^projects/[\w.-]+/locations/[\w-]+/operations/[\w.-]+$")
_VERSION = re.compile(r"^(projects/[\w-]+/)?sites/[a-z0-9-]+/versions/[\w-]+$")
# A Firestore path under projects/<project>/ (segments already percent-encoded by services/firestore.py):
# the database list, a database, or something under its documents / collection groups / backup schedules /
# operations, plus a `:method` (`databases:restore`, `databases/<id>:exportDocuments`); or the project's backups.
_FIRESTORE_PATH = re.compile(
    r"^(databases(/[\w()%.~-]+(/(documents|collectionGroups|backupSchedules|operations)(/[\w%.~-]+)*)?)?"
    r"(:[A-Za-z]+)?|locations/[\w-]+/backups(/[\w-]+)?)$"
)
BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,61}[a-z0-9]$")
# A Realtime Database: https://<id>.firebaseio.com (us-central1) or https://<id>.<region>.firebasedatabase.app.
_RTDB_URL = re.compile(
    r"^https://[a-z0-9][a-z0-9-]{0,62}(\.firebaseio\.com|\.[a-z]+-[a-z]+\d{1,2}\.firebasedatabase\.app)$"
)
# A path in it (segments percent-encoded by services/rtdb.py; keys never contain "."): "" is the root.
_RTDB_PATH = re.compile(r"^(/[A-Za-z0-9_%~-]+)*$")

_factory: Callable[[dict], Any] | None = None
_tokens: dict[str, tuple[str, float]] = {}  # sha256(client email + key + scopes) -> (access token, expiry)
_transport: httpx.BaseTransport | None = None


def client(config: dict) -> GcpClient:
    return (_factory or GcpClient)(config)


def set_factory(factory: Callable[[dict], Any] | None) -> None:
    """Test hook: `client(config)` returns `factory(config)` (None restores the real client)."""
    global _factory
    _factory = factory


def set_transport(transport: httpx.BaseTransport | None) -> None:
    """Test hook: route the real client's HTTP through this transport."""
    global _transport
    _transport = transport


def _name(value: str) -> str:
    if not _NAME.match(value):
        raise CloudError(f"Invalid Google resource name {value[:70]!r}")
    return value


def _secret_id(value: str) -> str:
    if not _SECRET_ID.match(value):
        raise CloudError(f"Invalid Secret Manager secret id {value[:70]!r}")
    return value


def _api_error(status: int, body: Any) -> CloudError:
    if isinstance(body, list) and body:  # streamed methods (Firestore runQuery) send errors as an array
        body = body[0]
    err = body.get("error") if isinstance(body, dict) else None
    code = ""
    if isinstance(err, dict):
        message, code = str(err.get("message") or err.get("status") or ""), str(err.get("status") or "")
    else:  # also the Realtime Database's {"error": "Permission denied"}
        message = str(body.get("error_description") or err or "") if isinstance(body, dict) else ""
    return CloudError(f"Google API error {status}: {message[:500]}", code=code, status=status)


class GcpClient:
    def __init__(self, config: dict):
        sa = config["service_account"]
        self.project = str(config["project_id"])
        self.region = str(config.get("region") or "us-central1")
        if not PROJECT_RE.match(self.project) or not REGION_RE.match(self.region):
            raise CloudError("Invalid Firebase project id or region")
        self._email, self._key, self._key_id = sa["client_email"], sa["private_key"], sa.get("private_key_id")
        # Tokens live an hour: shared by every client of the same key (a database request is a new client).
        self._cache_key = f"{self._email} {self._key}"
        self._http = httpx.Client(timeout=TIMEOUT, transport=_transport, follow_redirects=False)

    def __repr__(self) -> str:
        return f"GcpClient(project={self.project!r}, <key hidden>)"

    # --- plumbing --------------------------------------------------------------------------------

    def access_token(self, scopes: str = SCOPES) -> str:
        cache_key = hashlib.sha256(f"{self._cache_key} {scopes}".encode()).hexdigest()
        cached = _tokens.get(cache_key)
        if cached and time.time() < cached[1] - 60:
            return cached[0]
        now = int(time.time())
        claims = {"iss": self._email, "scope": scopes, "aud": TOKEN_URL, "iat": now, "exp": now + 3600}
        try:
            assertion = jwt.encode(
                claims, self._key, algorithm="RS256", headers={"kid": self._key_id} if self._key_id else None
            )
        except (ValueError, TypeError, jwt.PyJWTError) as exc:
            raise CloudError("The service-account key's private_key is not a valid RSA key") from exc
        body = self._send(
            "POST",
            TOKEN_URL,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            auth=False,
        )
        token = body.get("access_token") if isinstance(body, dict) else None
        if not token:
            raise CloudError("Google returned no access token")
        _tokens[cache_key] = (str(token), time.time() + float(body.get("expires_in") or 3600))
        return str(token)

    def _send(self, method: str, url: str, *, auth: bool = True, ok: tuple[int, ...] = (200,), **kwargs) -> Any:
        headers = dict(kwargs.pop("headers", None) or {})
        if auth:
            headers["Authorization"] = f"Bearer {self.access_token()}"
        try:
            resp = self._http.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise CloudError(f"Google Cloud could not be reached ({type(exc).__name__})") from None
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {}
        if resp.status_code in ok:
            return body
        raise _api_error(resp.status_code, body)

    def _json(self, method: str, url: str, body: dict | None = None, **kwargs) -> Any:
        return self._send(method, url, json=body if body is not None else {}, **kwargs)

    # --- Firebase project ------------------------------------------------------------------------

    def project_info(self) -> dict:
        return self._send("GET", f"{FIREBASE}/projects/{self.project}")

    # --- Cloud Firestore (docs/CLOUD.md "C2-3") ---------------------------------------------------

    def firestore(self, method: str, path: str, body: Any = None, params: Any = None) -> Any:
        """One Firestore REST call under `projects/<project>/` (`databases/(default)/documents:runQuery`).
        services/firestore.py builds every path and body; this is the seam its tests fake."""
        if not _FIRESTORE_PATH.match(path) or "/../" in f"/{path}/" or "/./" in f"/{path}/":
            raise CloudError("Refusing an unexpected Firestore path")
        # Deployer never deletes a database, a backup or an export: only documents and backup schedules.
        if method == "DELETE" and not re.search(r"/(documents|backupSchedules)/", f"/{path}"):
            raise CloudError("Refusing to delete anything but documents and backup schedules")
        url = f"{FIRESTORE}/projects/{self.project}/{path}"
        if body is None:
            return self._send(method, url, params=params)
        return self._json(method, url, body, params=params)

    # --- Cloud Storage: the bucket Firestore exports go to (docs/CLOUD.md "Firestore backups") ------

    def bucket(self, name: str) -> dict:
        """A bucket the service account can see (`{name, location}`), else CloudError."""
        if not BUCKET_RE.match(name):
            raise CloudError(f"Invalid Cloud Storage bucket name {name[:70]!r}")
        return self._send("GET", f"{STORAGE}/b/{name}")

    def create_bucket(self, name: str, location: str) -> None:
        """A private bucket (uniform access, public access prevented) in the project. One that exists already is
        fine when the service account can see it; else the name belongs to someone else (names are global)."""
        if not BUCKET_RE.match(name):
            raise CloudError(f"Invalid Cloud Storage bucket name {name[:70]!r}")
        body = {
            "name": name,
            "location": location,
            "iamConfiguration": {"uniformBucketLevelAccess": {"enabled": True}, "publicAccessPrevention": "enforced"},
            "labels": {"managed-by": "deployer"},
        }
        try:
            self._json("POST", f"{STORAGE}/b", body, params={"project": self.project})
        except CloudError as exc:
            if exc.status != 409:
                raise
            try:
                self.bucket(name)
            except CloudError:
                raise CloudError(f"The bucket name {name} is taken by another Google project") from None

    # --- Firebase Realtime Database (docs/CLOUD.md "C2-4") ----------------------------------------

    def rtdb_instances(self) -> list[dict]:
        """The project's Realtime Database instances (`{name, databaseUrl, type, state}`), every location."""
        out, token = [], None
        for _ in range(20):
            params = {"pageSize": 100, **({"pageToken": token} if token else {})}
            page = self._send("GET", f"{RTDB_MANAGEMENT}/projects/{self.project}/locations/-/instances", params=params)
            out += page.get("instances") or []
            token = page.get("nextPageToken")
            if not token:
                break
        return out

    def create_rtdb_instance(self, location: str, database_id: str) -> dict:
        """Creates the project's default Realtime Database (`<project>-default-rtdb`) in `location`."""
        if not REGION_RE.match(location) or not _NAME.match(database_id):
            raise CloudError("Invalid Realtime Database location or id")
        url = f"{RTDB_MANAGEMENT}/projects/{self.project}/locations/{location}/instances"
        return self._json("POST", url, {"type": "DEFAULT_DATABASE"}, params={"databaseId": database_id})

    def rtdb(self, method: str, base_url: str, path: str = "", body: Any = None, params: Any = None) -> Any:
        """One call to a Realtime Database's REST API: `<base_url><path>.json`. services/rtdb.py builds every
        path and body; this is the seam its tests fake. Answers over RTDB_MAX_BYTES are refused (code
        TOO_LARGE) while reading, never buffered whole."""
        if not _RTDB_URL.match(base_url) or not _RTDB_PATH.match(path):
            raise CloudError("Refusing an unexpected Realtime Database URL")
        kwargs: dict[str, Any] = {
            "params": params,
            "headers": {"Authorization": f"Bearer {self.access_token(RTDB_SCOPES)}"},
        }
        if body is not None:
            kwargs["json"] = body
        try:
            with self._http.stream(method, f"{base_url}{path}.json", **kwargs) as resp:
                raw = bytearray()
                for chunk in resp.iter_bytes():
                    raw += chunk
                    if len(raw) > RTDB_MAX_BYTES:
                        raise CloudError(
                            f"More than {RTDB_MAX_BYTES // 1024 // 1024} MB of data at this path: read a smaller "
                            "path, or use shallow / limitToFirst",
                            code="TOO_LARGE",
                            status=413,
                        )
        except httpx.HTTPError as exc:
            raise CloudError(f"The Realtime Database could not be reached ({type(exc).__name__})") from None
        try:
            out = json.loads(bytes(raw)) if raw else None
        except ValueError:
            out = None
        if resp.status_code == 200:
            return out
        raise _api_error(resp.status_code, out)

    # --- Hosting ---------------------------------------------------------------------------------

    def create_site(self, site: str) -> None:
        url = f"{HOSTING}/projects/{self.project}/sites"
        try:
            self._json("POST", url, params={"siteId": _name(site)})
        except CloudError as exc:
            if exc.status != 409:
                raise
            try:  # 409: fine when it is already this project's site, else the id is taken globally
                self._send("GET", f"{url}/{site}")
            except CloudError:
                raise CloudError(f"The Firebase site id '{site}' is taken by another project") from None

    def delete_site(self, site: str) -> None:
        self._send("DELETE", f"{HOSTING}/projects/{self.project}/sites/{_name(site)}", ok=(200, 404))

    def create_version(self, site: str, config: dict) -> str:
        out = self._json("POST", f"{HOSTING}/sites/{_name(site)}/versions", {"config": config})
        name = str(out.get("name") or "")
        if not _VERSION.match(name):
            raise CloudError("Firebase Hosting returned an unexpected version name")
        return name

    def populate_files(self, version: str, files: dict[str, str]) -> tuple[str, list[str]]:
        """(upload URL, hashes Hosting doesn't have yet) for `{"/path": sha256 of the gzipped file}`."""
        out = self._json("POST", f"{HOSTING}/{version}:populateFiles", {"files": files})
        upload_url = str(out.get("uploadUrl") or "")
        required = [str(h) for h in out.get("uploadRequiredHashes") or []]
        if required and not upload_url.startswith(UPLOAD_PREFIX):
            raise CloudError("Firebase Hosting returned an unexpected upload URL")
        return upload_url, required

    def upload_file(self, upload_url: str, sha256: str, gzipped: bytes) -> None:
        if not upload_url.startswith(UPLOAD_PREFIX) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise CloudError("Refusing an unexpected Firebase Hosting upload URL")
        self._send(
            "POST", f"{upload_url}/{sha256}", content=gzipped, headers={"Content-Type": "application/octet-stream"}
        )

    def finalize_version(self, version: str) -> None:
        self._json("PATCH", f"{HOSTING}/{version}", {"status": "FINALIZED"}, params={"updateMask": "status"})

    def create_channel(self, site: str, channel: str) -> str:
        """A preview channel; returns its URL."""
        out = self._json(
            "POST",
            f"{HOSTING}/sites/{_name(site)}/channels",
            {"ttl": CHANNEL_TTL},
            params={"channelId": _name(channel)},
        )
        return str(out.get("url") or "")

    def release(self, site: str, version: str, channel: str | None = None) -> None:
        base = f"{HOSTING}/sites/{_name(site)}" + (f"/channels/{_name(channel)}" if channel else "")
        self._json("POST", f"{base}/releases", {}, params={"versionName": version})

    def add_domain(self, site: str, hostname: str) -> None:
        url = f"{HOSTING}/projects/{self.project}/sites/{_name(site)}/customDomains"
        self._json("POST", url, {}, params={"customDomainId": hostname}, ok=(200, 409))

    def domain(self, site: str, hostname: str) -> dict:
        """`{status, records: [{type, name, value}]}`; status `active` once Hosting serves it with HTTPS."""
        url = f"{HOSTING}/projects/{self.project}/sites/{_name(site)}/customDomains/{quote(hostname, safe='')}"
        out = self._send("GET", url)
        records = []
        for group in (out.get("requiredDnsUpdates") or {}).get("desired") or []:
            for r in group.get("records") or []:
                if r.get("requiredAction", "ADD") == "ADD":
                    name = str(r.get("domainName") or group.get("domainName") or hostname).rstrip(".")
                    records.append({"type": r.get("type"), "name": name, "value": str(r.get("rdata") or "")})
        active = out.get("hostState") == "HOST_ACTIVE" and out.get("ownershipState") == "OWNERSHIP_ACTIVE"
        cert = (out.get("cert") or {}).get("state")
        return {"status": "active" if active and cert in (None, "CERT_ACTIVE") else "pending", "records": records}

    def delete_domain(self, site: str, hostname: str) -> None:
        url = f"{HOSTING}/projects/{self.project}/sites/{_name(site)}/customDomains/{quote(hostname, safe='')}"
        self._send("DELETE", url, ok=(200, 404))

    # --- Artifact Registry -----------------------------------------------------------------------

    def ensure_repository(self, repo: str) -> str:
        """Creates the Docker repository once; returns its image path prefix."""
        url = f"{REGISTRY}/projects/{self.project}/locations/{self.region}/repositories"
        op = self._json("POST", url, {"format": "DOCKER"}, params={"repositoryId": _name(repo)}, ok=(200, 409))
        name = op.get("name") if isinstance(op, dict) else None
        if name and not op.get("done"):
            for _ in range(30):
                if self.operation(REGISTRY, name).get("done"):
                    break
                time.sleep(2)
        return f"{self.region}-docker.pkg.dev/{self.project}/{repo}"

    def delete_package(self, repo: str, package: str) -> None:
        url = f"{REGISTRY}/projects/{self.project}/locations/{self.region}/repositories/{_name(repo)}"
        self._send("DELETE", f"{url}/packages/{_name(package)}", ok=(200, 404))

    def docker_login(self) -> tuple[str, str, str]:
        """(registry host, username, password) for `docker login --password-stdin`."""
        return f"{self.region}-docker.pkg.dev", "oauth2accesstoken", self.access_token()

    # --- Cloud Run -------------------------------------------------------------------------------

    def _services(self) -> str:
        return f"{RUN}/projects/{self.project}/locations/{self.region}/services"

    @staticmethod
    def _service_body(image: str, port: int, env: dict[str, str], secrets: dict[str, str] | None) -> dict:
        # docs/CLOUD.md "G1": `secrets` = NAME -> Secret Manager secret id, read as the service's own account.
        refs = [
            {"name": k, "valueSource": {"secretKeyRef": {"secret": _secret_id(v), "version": "latest"}}}
            for k, v in sorted((secrets or {}).items())
        ]
        return {
            "ingress": "INGRESS_TRAFFIC_ALL",
            "template": {
                "scaling": {"maxInstanceCount": 3},
                "containers": [
                    {
                        "image": image,
                        "ports": [{"containerPort": port}],
                        "env": [{"name": k, "value": v} for k, v in sorted(env.items())] + refs,
                        "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
                    }
                ],
            },
        }

    def create_service(
        self, name: str, image: str, port: int, env: dict[str, str], secrets: dict[str, str] | None = None
    ) -> str:
        """Returns the long-running operation's name."""
        body = self._service_body(image, port, env, secrets)
        return str(self._json("POST", self._services(), body, params={"serviceId": _name(name)}).get("name") or "")

    def update_service(
        self, name: str, image: str, port: int, env: dict[str, str], secrets: dict[str, str] | None = None
    ) -> str:
        body = self._service_body(image, port, env, secrets)
        return str(self._json("PATCH", f"{self._services()}/{_name(name)}", body).get("name") or "")

    def operation(self, base: str, name: str) -> dict:
        """`{done, error}` of a long-running operation (`base` is RUN or REGISTRY)."""
        if not _OPERATION.match(name) or base not in (RUN, REGISTRY):
            raise CloudError("Google returned an unexpected operation name")
        out = self._send("GET", f"{base}/{name}")
        err = out.get("error") or None
        return {"done": bool(out.get("done")), "error": (err or {}).get("message") if err else None}

    def make_public(self, name: str) -> None:
        policy = {"policy": {"bindings": [{"role": "roles/run.invoker", "members": ["allUsers"]}]}}
        self._json("POST", f"{self._services()}/{_name(name)}:setIamPolicy", policy)

    def service_url(self, name: str) -> str:
        return str(self._send("GET", f"{self._services()}/{_name(name)}").get("uri") or "")

    def delete_service(self, name: str) -> None:
        self._send("DELETE", f"{self._services()}/{_name(name)}", ok=(200, 404))

    # --- Secret Manager (docs/CLOUD.md "G1"; services/cloud_secrets.py) ----------------------------------

    def _secret(self, name: str) -> str:
        return f"{SECRETS}/projects/{self.project}/secrets/{_secret_id(name)}"

    def put_secret(self, name: str, value: str) -> str:
        """The secret `name` holds `value`: created once (automatic replication), a new version only when the
        value changed (Google bills per active version). Returns the secret id the service references."""
        url = f"{SECRETS}/projects/{self.project}/secrets"
        body = {"replication": {"automatic": {}}, "labels": {"managed-by": "deployer"}}
        self._json("POST", url, body, params={"secretId": _secret_id(name)}, ok=(200, 409))
        try:
            current = self._send("GET", f"{self._secret(name)}/versions/latest:access")
            data = base64.b64decode(str((current.get("payload") or {}).get("data") or ""))
        except CloudError as exc:
            if exc.status not in (400, 404):  # no version yet, or the latest one is disabled / destroyed
                raise
            data = None
        if data != value.encode("utf-8"):
            payload = {"payload": {"data": base64.b64encode(value.encode("utf-8")).decode("ascii")}}
            self._json("POST", f"{self._secret(name)}:addVersion", payload)
        return name

    def allow_secret(self, name: str, member: str) -> None:
        """Only `member` (the Cloud Run service's account) may read this secret: the whole policy is ours."""
        policy = {"policy": {"bindings": [{"role": SECRET_ACCESSOR, "members": [member]}]}}
        self._json("POST", f"{self._secret(name)}:setIamPolicy", policy)

    def delete_secret(self, name: str) -> None:
        self._send("DELETE", self._secret(name), ok=(200, 404))

    # --- GitHub Actions builds: workload identity federation (docs/CLOUD.md "C3") ------------------

    def _pools(self) -> str:
        return f"{IAM}/projects/{self.project}/locations/global/workloadIdentityPools"

    def _revive(self, url: str) -> None:
        """Pools and providers stay soft-deleted for 30 days and keep their id: bring one back."""
        if self._send("GET", url).get("state") == "DELETED":
            self._json("POST", f"{url}:undelete", {})

    def ensure_wif_pool(self, pool: str) -> None:
        """The project's workload identity pool for GitHub Actions (created once, shared, kept)."""
        try:
            self._json(
                "POST",
                self._pools(),
                {"displayName": "Deployer GitHub Actions"},
                params={"workloadIdentityPoolId": _name(pool)},
            )
        except CloudError as exc:
            if exc.status != 409:
                raise
            self._revive(f"{self._pools()}/{pool}")

    def ensure_wif_provider(self, pool: str, provider: str, condition: str) -> None:
        """An OIDC provider for GitHub's tokens that accepts only `condition` (one repository and branch)."""
        url = f"{self._pools()}/{_name(pool)}/providers"
        body = {
            "displayName": f"Deployer {provider}"[:32],
            "attributeMapping": {
                "google.subject": "assertion.sub",
                "attribute.repository": "assertion.repository",
                "attribute.ref": "assertion.ref",
            },
            "attributeCondition": condition,
            "oidc": {"issuerUri": GITHUB_ISSUER},
        }
        try:
            self._json("POST", url, body, params={"workloadIdentityPoolProviderId": _name(provider)})
        except CloudError as exc:
            if exc.status != 409:
                raise
            self._revive(f"{url}/{provider}")
            mask = "displayName,attributeMapping,attributeCondition,oidc"
            self._json("PATCH", f"{url}/{provider}", body, params={"updateMask": mask})

    def delete_wif_provider(self, pool: str, provider: str) -> None:
        self._send("DELETE", f"{self._pools()}/{_name(pool)}/providers/{_name(provider)}", ok=(200, 404))

    def set_sa_member(self, email: str, role: str, member: str, present: bool) -> None:
        """Adds (or removes) `member` in `role` on the service account `email` itself."""
        if not _SA_EMAIL.match(email):
            raise CloudError("Invalid service account email")
        url = f"{IAM}/projects/{self.project}/serviceAccounts/{email}"
        policy = self._json("POST", f"{url}:getIamPolicy", {})
        bindings = [b for b in policy.get("bindings") or [] if b.get("role") != role]
        members = {m for b in policy.get("bindings") or [] if b.get("role") == role for m in b.get("members") or []}
        changed = (member in members) != present
        members = (members | {member}) if present else (members - {member})
        if not changed:
            return
        if members:
            bindings.append({"role": role, "members": sorted(members)})
        self._json("POST", f"{url}:setIamPolicy", {"policy": {**policy, "bindings": bindings}})
