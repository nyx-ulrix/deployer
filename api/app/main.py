from fastapi import FastAPI

from app import __version__
from app.errors import install_error_handlers
from app.routers import (
    api_keys,
    auth,
    backups,
    data,
    data_sources,
    device_local,
    devices,
    health,
    instance,
    jobs,
    members,
    projects,
    query,
    remote_access,
    schema,
    setup,
    transfer,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Deployer API", version=__version__, docs_url="/v1/docs", openapi_url="/v1/openapi.json")
    install_error_handlers(app)
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
        transfer,
        devices,
        device_local,
        backups,
        jobs,
        remote_access,
    ):
        app.include_router(module.router, prefix="/v1")
    return app


app = create_app()
