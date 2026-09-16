from fastapi import FastAPI

from app import __version__
from app.errors import install_error_handlers
from app.routers import (
    api_keys,
    auth,
    data,
    data_sources,
    health,
    instance,
    members,
    projects,
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
        transfer,
    ):
        app.include_router(module.router, prefix="/v1")
    return app


app = create_app()
