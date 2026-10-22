from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ErrorCode:
    """Standardized UPPER_SNAKE_CASE error codes for IncuBrix assessment."""

    CONNECTOR_NOT_FOUND = "CONNECTOR_NOT_FOUND"
    DUPLICATE_CONNECTOR = "DUPLICATE_CONNECTOR"
    METHOD_NOT_SUPPORTED = "METHOD_NOT_SUPPORTED"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    NOT_FOUND = "NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    PUBLISH_FAILED = "PUBLISH_FAILED"


class ErrorDetail(BaseModel):
    """Inner error payload in the standard error envelope."""

    code: str = Field(..., description="UPPER_SNAKE_CASE error code")
    message: str = Field(..., description="Human-readable description of error")
    retryable: bool = Field(default=False, description="Whether the operation may be retried")
    details: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary additional context")


class ErrorEnvelope(BaseModel):
    """Authoritative error envelope required by the assessment:
    {"error":{"code":"UPPER_SNAKE_CASE","message":"...","retryable":false,"details":{}}}
    """

    error: ErrorDetail


class IncuBrixError(Exception):
    """Base exception for application errors mapped to the standard error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 500,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}

    def to_envelope(self) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                retryable=self.retryable,
                details=self.details,
            )
        )


class ConnectorNotFoundError(IncuBrixError):
    def __init__(self, connector_key: str) -> None:
        super().__init__(
            code=ErrorCode.CONNECTOR_NOT_FOUND,
            message=f"Connector '{connector_key}' not found",
            status_code=404,
            retryable=False,
            details={"connector_key": connector_key},
        )


class DuplicateConnectorError(IncuBrixError):
    def __init__(self, connector_key: str) -> None:
        super().__init__(
            code=ErrorCode.DUPLICATE_CONNECTOR,
            message=f"Connector with key '{connector_key}' is already registered",
            status_code=409,
            retryable=False,
            details={"connector_key": connector_key},
        )


class MethodNotSupportedError(IncuBrixError):
    def __init__(self, connector_key: str, method: str) -> None:
        super().__init__(
            code=ErrorCode.METHOD_NOT_SUPPORTED,
            message=f"Method '{method}' is not supported by connector '{connector_key}'",
            status_code=405,
            retryable=False,
            details={"connector_key": connector_key, "method": method},
        )


class DatabaseUnavailableError(IncuBrixError):
    def __init__(self, message: str = "Database readiness check failed", details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            code=ErrorCode.DATABASE_UNAVAILABLE,
            message=message,
            status_code=503,
            retryable=True,
            details=details or {"database": "disconnected"},
        )


class ManifestValidationError(IncuBrixError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            code=ErrorCode.MANIFEST_INVALID,
            message=message,
            status_code=422,
            retryable=False,
            details=details or {},
        )


class InvalidArgumentError(IncuBrixError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            message=message,
            status_code=400,
            retryable=False,
            details=details or {},
        )
