import ipaddress
import re
import socket
import time
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import __version__
from app.config import seal_process
from app.errors import install_error_handlers
from app.routers import (
    api_keys,
    apps,
    auth,
    backups,
    cloud,
    cohosting,
    data,
    data_sources,
    device_local,
    devices,
    health,
    instance,
    integrations,
    jobs,
    mcp,
    members,
    monitoring,
    projects,
    query,
    remote_access,
    saved_queries,
    schema,
    setup,
    transfer,
)
from app.services.metrics import RequestMetricsMiddleware

# Routes that accept project API keys (docs/DATA_API.md "Calling from a browser"). Only these get CORS.
KEY_ROUTES = re.compile(
    r"^/v1/projects/[^/]+/(schema(/export|/links)?"
    r"|data-sources/[^/]+/(query|tables/[^/]+/rows|collections/[^/]+/documents(/[^/]+)?))$"
)


class KeyRoutesCORS:
    """CORS for browsers calling the data API with a bearer key. Any origin but no credentials:
    cookies are never sent or readable cross-origin, and a key works from curl anyway."""

    def __init__(self, app):
        self.app = app
        self.cors = CORSMiddleware(
            app,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and KEY_ROUTES.match(scope["path"]):
            await self.cors(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class CaddyProxyHeaders:
    """X-Forwarded-For / -Proto count only on connections from the `caddy` container (A-019): the API
    also listens on networks where untrusted code runs (the query console's shells), and Docker gives
    Caddy a new address when it is recreated, so the name is looked up (again at most every
    RESOLVE_EVERY_S while other peers connect) rather than trusting a fixed subnet."""

    RESOLVE_EVERY_S = 30.0

    def __init__(self, app, host: str = "caddy"):
        self.app, self.host = app, host
        self.trusting = ProxyHeadersMiddleware(app, trusted_hosts="*")  # Caddy sends exactly one XFF entry
        self.ips: frozenset[str] = frozenset()
        self.resolved_at = float("-inf")

    async def __call__(self, scope, receive, send):
        peer = (scope.get("client") or ("",))[0]
        if scope["type"] in ("http", "websocket") and _is_ip(peer):
            if peer not in self.ips and time.monotonic() - self.resolved_at >= self.RESOLVE_EVERY_S:
                self.resolved_at = time.monotonic()
                self.ips = await anyio.to_thread.run_sync(self.lookup)
            if peer in self.ips:
                return await self.trusting(scope, receive, send)
        await self.app(scope, receive, send)

    def lookup(self) -> frozenset[str]:
        try:
            return frozenset(info[4][0] for info in socket.getaddrinfo(self.host, None))
        except OSError:  # not on a compose network (tests, a bare uvicorn): trust nobody
            return frozenset()


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


@asynccontextmanager
async def lifespan(_app: FastAPI):
    seal_process()  # SECURITY.md "Query console": no child process inherits the secrets
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Deployer API",
        version=__version__,
        docs_url="/v1/docs",
        openapi_url="/v1/openapi.json",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(RequestMetricsMiddleware)  # docs/MONITORING.md
    app.add_middleware(KeyRoutesCORS)
    app.add_middleware(CaddyProxyHeaders)  # outermost: everything after it sees the real client
    for module in (
        health,
        setup,
        auth,
        instance,
        projects,
        members,
        api_keys,
        data_sources,
        schema,
        data,
        query,
        saved_queries,
        transfer,
        devices,
        device_local,
        backups,
        jobs,
        remote_access,
        apps,
        cloud,
        cohosting,
        integrations,
        mcp,
        monitoring,
    ):
        app.include_router(module.router, prefix="/v1")
    return app


app = create_app()
