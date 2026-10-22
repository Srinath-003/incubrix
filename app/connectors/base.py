from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.core.errors import MethodNotSupportedError
from app.models.common import Connection, Destination, Rendition
from app.models.connector import (
    AssistPackResponse,
    DeleteResponse,
    MetricsResponse,
    PublishResponse,
    RefreshAuthResponse,
    StatusResponse,
    ValidateResponse,
)
from app.models.manifest import ConnectorManifest


class BaseConnector(ABC):
    """Abstract base connector defining the authoritative Appendix A contract.
    
    Connectors are stateless platform adapters that execute platform API calls.
    They NEVER write directly to IncuBrix's internal database.
    """

    @property
    @abstractmethod
    def manifest(self) -> ConnectorManifest:
        """Connector metadata manifest declaring capabilities and supported methods."""
        pass

    @abstractmethod
    async def validate(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
    ) -> ValidateResponse:
        """Validate rendition against destination and connection constraints.
        
        Must return ValidateResponse with `ok` (bool) and `violations` (list of strings).
        """
        pass

    @abstractmethod
    async def publish(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
        idempotency_key: str,
    ) -> PublishResponse:
        """Publish rendition to platform with idempotency protection.
        
        Must return PublishResponse with `platform_post_id`, optional `live_url`, and `status`.
        """
        pass

    @abstractmethod
    async def get_status(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> StatusResponse:
        """Query status of a previously published post.
        
        Must return StatusResponse with `status` and optional `live_url`.
        """
        pass

    @abstractmethod
    async def delete(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> DeleteResponse:
        """Delete post from target platform.
        
        Must return DeleteResponse with `deleted` (bool).
        """
        pass

    async def fetch_metrics(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
        since: Optional[str] = None,
    ) -> MetricsResponse:
        """Optional: Fetch engagement metrics for a post.
        
        Raises MethodNotSupportedError by default unless implemented.
        """
        raise MethodNotSupportedError(
            connector_key=self.manifest.connector_key,
            method="fetch_metrics",
        )

    async def refresh_auth(
        self,
        connection: Connection | Dict[str, Any],
    ) -> RefreshAuthResponse:
        """Optional: Refresh platform credentials/tokens.
        
        Raises MethodNotSupportedError by default unless implemented.
        """
        raise MethodNotSupportedError(
            connector_key=self.manifest.connector_key,
            method="refresh_auth",
        )

    async def build_assist_pack(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
    ) -> AssistPackResponse:
        """Assisted Tier: Package media and instructions for manual posting.
        
        Raises MethodNotSupportedError by default unless implemented.
        """
        raise MethodNotSupportedError(
            connector_key=self.manifest.connector_key,
            method="build_assist_pack",
        )
