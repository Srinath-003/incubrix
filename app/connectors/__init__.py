"""
Connector subsystem: abstract contract, registry, and platform connector implementations.
"""

from app.connectors.base import BaseConnector
from app.connectors.registry import ConnectorRegistry, connector_registry

__all__ = ["BaseConnector", "ConnectorRegistry", "connector_registry"]
