"""The Google REST calls behind the Firebase hosting targets and databases (docs/CLOUD.md): Firebase Hosting
v1beta1, Cloud Run Admin v2, Artifact Registry v1 and Cloud Firestore v1, with a service-account key.

No Google SDK: the OAuth token is a JWT-bearer grant signed with the key's RSA private key (PyJWT +
cryptography, already dependencies) and every call is plain httpx. Rules:

- the token endpoint is always `TOKEN_URL`; the key file's own `token_uri` is ignored (a pasted key
  must not be able to send a signed assertion anywhere else);
- every URL is built from constants plus validated ids; the only URLs taken from a response are
  long-running operation names (checked against `_OPERATION`) and Hosting's upload URL (must start
  with `UPLOAD_PREFIX`), so the bearer token only ever goes to Google;
- the private key and access tokens are never logged or put in `CloudError` messages.

`GcpClient` is replaced by a fake in tests (`set_factory`); the token exchange itself is tested with
`set_transport` (httpx.MockTransport).
"""

from __future__ import annotations

import hashlib
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
UPLOAD_PREFIX = "https://upload-firebasehosting.googleapis.com/"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
CHANNEL_TTL = "604800s"  # preview channels expire after 7 days

PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
REGION_RE = re.compile(r"^[a-z]+-[a-z]+\d{1,2}$")
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_OPERATION = re.compile(r"^projects/[\w.-]+/locations/[\w-]+/operations/[\w.-]+$")
_VERSION = re.compile(r"^(projects/[\w-]+/)?sites/[a-z0-9-]+/versions/[\w-]+$")
# A Firestore path under projects/<project>/ (segments already percent-encoded by services/firestore.py):
# the database list, a database, or something under its documents / collection groups, plus a `:method`.
_FIRESTORE_PATH = re.compile(r"^databases(/[\w()%.~-]+(/(documents|collectionGroups)(/[\w%.~-]+)*)?)?(:[A-Za-z]+)?$")

_factory: Callable[[dict], Any] | None = None
_tokens: dict[str, tuple[str, float]] = {}  # sha256(client email + key) -> (access token, expiry)
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


class GcpClient:
    def __init__(self, config: dict):
        sa = config["service_account"]
        self.project = str(config["project_id"])
        self.region = str(config.get("region") or "us-central1")
        if not PROJECT_RE.match(self.project) or not REGION_RE.match(self.region):
            raise CloudError("Invalid Firebase project id or region")
        self._email, self._key, self._key_id = sa["client_email"], sa["private_key"], sa.get("private_key_id")
        # Tokens live an hour: shared by every client of the same key (a database request is a new client).
        self._cache_key = hashlib.sha256(f"{self._email} {self._key}".encode()).hexdigest()
        self._http = httpx.Client(timeout=TIMEOUT, transport=_transport, follow_redirects=False)

    def __repr__(self) -> str:
        return f"GcpClient(project={self.project!r}, <key hidden>)"

    # --- plumbing --------------------------------------------------------------------------------

    def access_token(self) -> str:
        cached = _tokens.get(self._cache_key)
        if cached and time.time() < cached[1] - 60:
            return cached[0]
        now = int(time.time())
        claims = {"iss": self._email, "scope": SCOPES, "aud": TOKEN_URL, "iat": now, "exp": now + 3600}
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
        _tokens[self._cache_key] = (str(token), time.time() + float(body.get("expires_in") or 3600))
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
        if isinstance(body, list) and body:  # streamed methods (Firestore runQuery) send errors as an array
            body = body[0]
        err = body.get("error") if isinstance(body, dict) else None
        code = ""
        if isinstance(err, dict):
            message, code = str(err.get("message") or err.get("status") or ""), str(err.get("status") or "")
        else:
            message = str(body.get("error_description") or err or "") if isinstance(body, dict) else ""
        raise CloudError(f"Google API error {resp.status_code}: {message[:500]}", code=code, status=resp.status_code)

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
        url = f"{FIRESTORE}/projects/{self.project}/{path}"
        if body is None:
            return self._send(method, url, params=params)
        return self._json(method, url, body, params=params)

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
    def _service_body(image: str, port: int, env: dict[str, str]) -> dict:
        return {
            "ingress": "INGRESS_TRAFFIC_ALL",
            "template": {
                "scaling": {"maxInstanceCount": 3},
                "containers": [
                    {
                        "image": image,
                        "ports": [{"containerPort": port}],
                        "env": [{"name": k, "value": v} for k, v in sorted(env.items())],
                        "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
                    }
                ],
            },
        }

    def create_service(self, name: str, image: str, port: int, env: dict[str, str]) -> str:
        """Returns the long-running operation's name."""
        body = self._service_body(image, port, env)
        return str(self._json("POST", self._services(), body, params={"serviceId": _name(name)}).get("name") or "")

    def update_service(self, name: str, image: str, port: int, env: dict[str, str]) -> str:
        body = self._service_body(image, port, env)
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
