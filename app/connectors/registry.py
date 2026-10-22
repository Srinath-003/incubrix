import logging
from typing import Dict, List, Optional

from app.connectors.base import BaseConnector
from app.core.errors import ConnectorNotFoundError, DuplicateConnectorError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Registry managing available destination connectors.
    
    Guarantees unique connector keys, validates manifest constraints on registration,
    and returns informative errors when querying unknown connectors.
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        """Register a destination connector.
        
        Validates manifest tier requirements and ensures no duplicate connector keys exist.
        """
        manifest = connector.manifest
        key = manifest.connector_key

        if key in self._connectors:
            logger.warning("Duplicate connector registration attempted: %s", key)
            raise DuplicateConnectorError(connector_key=key)

        manifest.validate_tier_requirements()
        self._connectors[key] = connector
        logger.info("Successfully registered connector: %s (v%s, tier: %s)", key, manifest.version, manifest.tier.value)

    def get(self, connector_key: str) -> BaseConnector:
        """Retrieve registered connector by its unique key.
        
        Raises ConnectorNotFoundError if connector is not registered.
        """
        if connector_key not in self._connectors:
            raise ConnectorNotFoundError(connector_key=connector_key)
        return self._connectors[connector_key]

    def list_all(self) -> List[BaseConnector]:
        """Return list of all registered connectors sorted by connector key."""
        return [self._connectors[k] for k in sorted(self._connectors.keys())]

    def contains(self, connector_key: str) -> bool:
        """Check whether a connector key is registered."""
        return connector_key in self._connectors

    def unregister(self, connector_key: str) -> Optional[BaseConnector]:
        """Unregister a connector by key, returning it if present."""
        return self._connectors.pop(connector_key, None)

    def clear(self) -> None:
        """Clear all registered connectors (useful for clean test isolation)."""
        self._connectors.clear()


# Application global singleton registry
connector_registry = ConnectorRegistry()
