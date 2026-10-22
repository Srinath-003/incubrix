import pytest
from typing import Any, AsyncGenerator, Dict, Optional
import httpx

from app.connectors.base import BaseConnector
from app.connectors.registry import connector_registry
from app.core.database import db_manager
from app.main import app
from app.models.common import Connection, ConnectorTier, Destination, Rendition
from app.models.connector import (
    AssistPackResponse,
    DeleteResponse,
    MetricsResponse,
    PublishResponse,
    RefreshAuthResponse,
    StatusResponse,
    ValidateResponse,
)
from app.models.manifest import ConnectorCapabilities, ConnectorManifest


class SampleAutomatedConnector(BaseConnector):
    """Test connector implementing automated tier contract."""

    def __init__(self, key: str = "sample_platform") -> None:
        self._key = key

    @property
    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            connector_key=self._key,
            name="Sample Platform Connector",
            version="1.0.0",
            description="Mock connector for verifying automated connector contract",
            tier=ConnectorTier.AUTOMATED,
            platform="sample_platform",
            auth_type="oauth2",
            supported_methods=[
                "validate",
                "publish",
                "get_status",
                "delete",
                "fetch_metrics",
                "refresh_auth",
            ],
            capabilities=ConnectorCapabilities(
                media_types=["video", "image"],
                max_file_size_bytes=100 * 1024 * 1024,
                max_duration_sec=120,
                supports_metrics=True,
                supports_delete=True,
            ),
        )

    async def validate(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
    ) -> ValidateResponse:
        violations = []
        rend_dict = rendition.model_dump() if isinstance(rendition, Rendition) else rendition
        if not rend_dict.get("url"):
            violations.append("Rendition URL is required")
        return ValidateResponse(ok=len(violations) == 0, violations=violations)

    async def publish(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
        idempotency_key: str,
    ) -> PublishResponse:
        return PublishResponse(
            platform_post_id=f"sample_{idempotency_key[:8]}",
            live_url=f"https://sample.platform/post/{idempotency_key[:8]}",
            status="published",
        )

    async def get_status(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> StatusResponse:
        return StatusResponse(
            status="published",
            live_url=f"https://sample.platform/post/{platform_post_id}",
        )

    async def delete(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> DeleteResponse:
        return DeleteResponse(deleted=True)

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
        since: Optional[str] = None,
    ) -> MetricsResponse:
        return MetricsResponse(
            metrics={"views": 42, "likes": 7},
            fetched_at="2026-10-22T12:00:00Z",
        )

    async def refresh_auth(
        self,
        connection: Connection | Dict[str, Any],
    ) -> RefreshAuthResponse:
        return RefreshAuthResponse(
            refreshed=True,
            credentials={"access_token": "new_mock_token"},
            expires_at="2026-12-31T23:59:59Z",
        )


class SampleAssistedConnector(BaseConnector):
    """Test connector implementing assisted tier contract."""

    @property
    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            connector_key="sample_assisted",
            name="Sample Assisted Connector",
            version="1.0.0",
            description="Mock connector for verifying assisted tier contract",
            tier=ConnectorTier.ASSISTED,
            platform="sample_assisted",
            auth_type="session",
            supported_methods=["validate", "build_assist_pack"],
        )

    async def validate(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
    ) -> ValidateResponse:
        return ValidateResponse(ok=True, violations=[])

    async def publish(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
        idempotency_key: str,
    ) -> PublishResponse:
        raise NotImplementedError("Assisted tier does not support automated publish")

    async def get_status(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> StatusResponse:
        raise NotImplementedError("Assisted tier does not support automated status query")

    async def delete(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> DeleteResponse:
        raise NotImplementedError("Assisted tier does not support automated delete")

    async def build_assist_pack(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
    ) -> AssistPackResponse:
        return AssistPackResponse(
            instructions="Upload file manually via platform dashboard",
            assets=[{"name": "main_video", "url": "https://example.com/asset.mp4"}],
            metadata={"title": "Test Title", "tags": ["tag1", "tag2"]},
        )


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure connector registry is clean before and after each test."""
    connector_registry.clear()
    yield
    connector_registry.clear()


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client bound to the FastAPI application."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
