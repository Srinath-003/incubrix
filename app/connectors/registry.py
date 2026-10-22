import logging
from typing import Dict, List, Optional

from app.connectors.base import BaseConnector
from app.core.errors import ConnectorDisabledError, ConnectorNotFoundError, DuplicateConnectorError

logger = logging.getLogger(__name__)


class ConnectorRegistry:
    """Registry managing available destination connectors.
    
    Guarantees unique connector keys, validates manifest constraints on registration,
    and returns informative errors when querying unknown or disabled connectors.
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, BaseConnector] = {}
        self._disabled: set[str] = set()

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
        if not manifest.enabled:
            self._disabled.add(key)
        logger.info("Successfully registered connector: %s (v%s, tier: %s)", key, manifest.version, manifest.tier.value)

    def disable(self, connector_key: str) -> None:
        """Disable a registered connector."""
        if connector_key not in self._connectors:
            raise ConnectorNotFoundError(connector_key=connector_key)
        self._disabled.add(connector_key)
        logger.info("Connector '%s' has been disabled", connector_key)

    def enable(self, connector_key: str) -> None:
        """Enable a previously disabled connector."""
        if connector_key not in self._connectors:
            raise ConnectorNotFoundError(connector_key=connector_key)
        self._disabled.discard(connector_key)
        logger.info("Connector '%s' has been enabled", connector_key)

    def is_disabled(self, connector_key: str) -> bool:
        """Check whether a connector is disabled."""
        if connector_key not in self._connectors:
            return False
        return (
            connector_key in self._disabled
            or not self._connectors[connector_key].manifest.enabled
        )

    def get(self, connector_key: str, check_enabled: bool = True) -> BaseConnector:
        """Retrieve registered connector by its unique key.
        
        Raises ConnectorNotFoundError if connector is not registered.
        Raises ConnectorDisabledError if connector is disabled and check_enabled is True.
        """
        if connector_key not in self._connectors:
            raise ConnectorNotFoundError(connector_key=connector_key)
        if check_enabled and self.is_disabled(connector_key):
            raise ConnectorDisabledError(connector_key=connector_key)
        return self._connectors[connector_key]

    def list_all(self, include_disabled: bool = True) -> List[BaseConnector]:
        """Return list of registered connectors sorted by connector key."""
        if include_disabled:
            return [self._connectors[k] for k in sorted(self._connectors.keys())]
        return [
            self._connectors[k]
            for k in sorted(self._connectors.keys())
            if not self.is_disabled(k)
        ]

    def contains(self, connector_key: str) -> bool:
        """Check whether a connector key is registered."""
        return connector_key in self._connectors

    def unregister(self, connector_key: str) -> Optional[BaseConnector]:
        """Unregister a connector by key, returning it if present."""
        self._disabled.discard(connector_key)
        return self._connectors.pop(connector_key, None)

    def clear(self) -> None:
        """Clear all registered connectors (useful for clean test isolation)."""
        self._connectors.clear()
        self._disabled.clear()


# Application global singleton registry
connector_registry = ConnectorRegistry()
