"""
Connector subsystem: abstract contract, registry, and platform connector implementations.
"""

from app.connectors.base import BaseConnector
from app.connectors.discourse.connector import DiscourseConnector
from app.connectors.registry import ConnectorRegistry, connector_registry


def register_default_connectors() -> None:
    """Register standard platform connectors into the central registry."""
    if not connector_registry.contains("discourse"):
        connector_registry.register(DiscourseConnector())


__all__ = [
    "BaseConnector",
    "ConnectorRegistry",
    "connector_registry",
    "DiscourseConnector",
    "register_default_connectors",
]
