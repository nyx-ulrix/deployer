from fastapi import FastAPI

from app import __version__
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


def create_app() -> FastAPI:
    app = FastAPI(title="Deployer API", version=__version__, docs_url="/v1/docs", openapi_url="/v1/openapi.json")
    install_error_handlers(app)
    app.add_middleware(RequestMetricsMiddleware)  # docs/MONITORING.md
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
