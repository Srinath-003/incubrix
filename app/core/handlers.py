import logging
from pydantic import ValidationError as PydanticValidationError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import ErrorCode, ErrorDetail, ErrorEnvelope, IncuBrixError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register application-wide exception handlers enforcing the assessment error envelope."""

    @app.exception_handler(IncuBrixError)
    async def handle_incubrix_error(request: Request, exc: IncuBrixError) -> JSONResponse:
        logger.warning("IncuBrix domain error [%s]: %s (details: %s)", exc.code, exc.message, exc.details)
        envelope = exc.to_envelope()
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        clean_errors = []
        for err in exc.errors():
            clean_errors.append(
                {
                    "loc": [str(loc) for loc in err.get("loc", [])],
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message="Request body or query parameter validation failed",
                retryable=False,
                details={"errors": clean_errors},
            )
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(),
        )

    @app.exception_handler(PydanticValidationError)
    async def handle_pydantic_validation_error(request: Request, exc: PydanticValidationError) -> JSONResponse:
        clean_errors = []
        for err in exc.errors():
            clean_errors.append(
                {
                    "loc": [str(loc) for loc in err.get("loc", [])],
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=ErrorCode.VALIDATION_ERROR,
                message="Payload validation failed",
                retryable=False,
                details={"errors": clean_errors},
            )
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {
            404: ErrorCode.NOT_FOUND,
            405: ErrorCode.METHOD_NOT_SUPPORTED,
            422: ErrorCode.VALIDATION_ERROR,
            503: ErrorCode.DATABASE_UNAVAILABLE,
        }
        code = code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=code,
                message=str(exc.detail) if exc.detail else "HTTP error occurred",
                retryable=(exc.status_code == 503),
                details={"status_code": exc.status_code},
            )
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(),
        )

    @app.exception_handler(Exception)
    async def handle_generic_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code=ErrorCode.INTERNAL_ERROR,
                message="An unexpected internal server error occurred",
                retryable=False,
                details={"error_type": type(exc).__name__},
            )
        )
        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(),
        )
