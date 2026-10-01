import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

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
