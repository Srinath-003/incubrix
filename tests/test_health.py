import pytest
from unittest.mock import AsyncMock, patch
import httpx

from app.core.database import db_manager


@pytest.mark.asyncio
async def test_health_liveness_succeeds(async_client: httpx.AsyncClient):
    """GET /health must return 200 indicating application process is live."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "healthy"}


@pytest.mark.asyncio
async def test_health_liveness_unaffected_by_db_failure(async_client: httpx.AsyncClient):
    """Liveness probe must NOT fail even when MongoDB is down."""
    with patch.object(db_manager, "ping", AsyncMock(return_value=False)):
        response = await async_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_succeeds_when_db_connected(async_client: httpx.AsyncClient):
    """GET /ready returns 200 when database ping succeeds."""
    with patch.object(db_manager, "ping", AsyncMock(return_value=True)):
        response = await async_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ready", "database": "connected"}


@pytest.mark.asyncio
async def test_readiness_fails_when_db_unreachable(async_client: httpx.AsyncClient):
    """GET /ready returns 503 and standard error envelope when database is unreachable."""
    with patch.object(db_manager, "ping", AsyncMock(return_value=False)):
        response = await async_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert data["error"]["retryable"] is True
        assert data["error"]["details"]["database"] == "disconnected"
