import pytest
from fastapi import HTTPException
import httpx

from app.core.errors import (
    DatabaseUnavailableError,
    ErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    IncuBrixError,
)
from app.main import app


def test_error_envelope_model_serialization():
    """Verify exact schema of ErrorEnvelope JSON representation."""
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=ErrorCode.DATABASE_UNAVAILABLE,
            message="Database readiness check failed",
            retryable=True,
            details={"database": "disconnected"},
        )
    )
    serialized = envelope.model_dump()
    assert "error" in serialized
    assert serialized["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert serialized["error"]["message"] == "Database readiness check failed"
    assert serialized["error"]["retryable"] is True
    assert serialized["error"]["details"] == {"database": "disconnected"}


def test_custom_incubrix_error_envelope_conversion():
    """IncuBrixError subclasses cleanly convert to standard ErrorEnvelope."""
    err = DatabaseUnavailableError()
    env = err.to_envelope()
    assert env.error.code == ErrorCode.DATABASE_UNAVAILABLE
    assert env.error.retryable is True


@pytest.mark.asyncio
async def test_404_produces_standard_error_envelope(async_client: httpx.AsyncClient):
    """Accessing non-existent route produces standard error envelope."""
    response = await async_client.get("/non_existent_route_12345")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert isinstance(data["error"]["message"], str)
    assert data["error"]["retryable"] is False
    assert isinstance(data["error"]["details"], dict)
