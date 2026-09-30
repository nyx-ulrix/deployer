import logging
from functools import lru_cache

from fastapi import APIRouter, Response
from sqlalchemy import text

from app import __version__
from app.config import get_settings
from app.db import get_engine
from app.redis_client import get_redis

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@lru_cache
def _mongo_client():
    from pymongo import MongoClient

    return MongoClient(get_settings().mongo_root_uri, serverSelectionTimeoutMS=2000, connectTimeoutMS=2000)


def _check_mariadb() -> bool:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001
        log.debug("MariaDB health check failed", exc_info=True)
        return False


def _check_mongodb() -> bool | None:
    """None when MongoDB is switched off (no AVX CPU): not running is expected, not a failure."""
    if not get_settings().managed_mongodb_enabled:
        return None
    try:
        _mongo_client().admin.command("ping")
        return True
    except Exception:  # noqa: BLE001
        log.debug("MongoDB health check failed", exc_info=True)
        return False


def _check_redis() -> bool:
    try:
        return bool(get_redis().ping())
    except Exception:  # noqa: BLE001
        log.debug("Redis health check failed", exc_info=True)
        return False


@router.get("/health")
def health(response: Response) -> dict:
    # MariaDB and Redis are required; MongoDB only backs MongoDB projects, so it does not degrade the API.
    services = {"mariadb": _check_mariadb(), "mongodb": _check_mongodb(), "redis": _check_redis()}
    ok = services["mariadb"] and services["redis"]
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "degraded", "version": __version__, "services": services}
