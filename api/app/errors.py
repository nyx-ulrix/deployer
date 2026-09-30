import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    """Raise from handlers/services; rendered as {"error": {code, message, details}}."""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


class CloudError(Exception):
    """An AWS / Google Cloud call failed (docs/CLOUD.md). `message` is the provider's own error text,
    never request data or credentials; `code` is the provider's error code when there is one."""

    def __init__(self, message: str, *, code: str = "", status: int = 0):
        super().__init__(message)
        self.message, self.code, self.status = message, code, status


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def forbidden(message: str = "You do not have permission to do that") -> ApiError:
    return ApiError(403, "forbidden", message)


def unauthorized(message: str = "Authentication required") -> ApiError:
    return ApiError(401, "unauthorized", message)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def validation_error(message: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(422, "validation_error", message, details)


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        # 429s carry `details.retry_after`; mirror it in the standard header for HTTP clients.
        retry_after = exc.details.get("retry_after") if exc.status_code == 429 else None
        headers = {"Retry-After": str(max(int(retry_after), 1))} if isinstance(retry_after, int) else None
        return JSONResponse(
            status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details), headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Name the first bad field and keep the validator's own text; never echo `input` (it can be a password).
        errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
        message = "Invalid request"
        if errors:
            loc = [str(part) for part in errors[0].get("loc", ())]
            # A missing body stays "body"; a JSON decode error's loc number is a character offset, not a field.
            field = (
                ""
                if errors[0].get("type") == "json_invalid"
                else ".".join(loc[1:] if loc[:1] == ["body"] and len(loc) > 1 else loc)
            )
            msg = str(errors[0].get("msg", "")).removeprefix("Value error, ")
            message = f"{field}: {msg}" if field else msg or message
        return JSONResponse(
            status_code=422, content=_body("validation_error", message, {"errors": jsonable_encoder(errors)})
        )

    # Starlette's class (FastAPI's subclasses it), so router 404/405s get the envelope too.
    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        codes = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(codes.get(exc.status_code, "http_error"), str(exc.detail)),
            headers=exc.headers,  # e.g. the 405's Allow
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_body("internal_error", "Something went wrong. Run 'deployer logs api' on the PC for details."),
        )
