import pytest
from app.connectors.registry import connector_registry
from app.core.errors import (
    ConnectorNotFoundError,
    DuplicateConnectorError,
    ErrorCode,
    ManifestValidationError,
)
from app.models.common import ConnectorTier
from app.models.manifest import ConnectorManifest
from tests.conftest import SampleAssistedConnector, SampleAutomatedConnector


def test_register_and_retrieve_connector():
    """Connector registers successfully and can be retrieved by key."""
    connector = SampleAutomatedConnector(key="platform_alpha")
    connector_registry.register(connector)

    retrieved = connector_registry.get("platform_alpha")
    assert retrieved is connector
    assert retrieved.manifest.connector_key == "platform_alpha"


def test_duplicate_key_rejected():
    """Registering a connector with an existing key raises DuplicateConnectorError."""
    connector1 = SampleAutomatedConnector(key="shared_key")
    connector2 = SampleAutomatedConnector(key="shared_key")

    connector_registry.register(connector1)
    with pytest.raises(DuplicateConnectorError) as exc_info:
        connector_registry.register(connector2)

    assert exc_info.value.code == ErrorCode.DUPLICATE_CONNECTOR
    assert "shared_key" in exc_info.value.message


def test_unknown_connector_raises_not_found():
    """Querying an unregistered connector raises ConnectorNotFoundError."""
    with pytest.raises(ConnectorNotFoundError) as exc_info:
        connector_registry.get("non_existent_key")

    assert exc_info.value.code == ErrorCode.CONNECTOR_NOT_FOUND
    assert exc_info.value.status_code == 404


def test_list_all_connectors():
    """Registry returns all registered connectors in sorted order."""
    connector_b = SampleAutomatedConnector(key="platform_b")
    connector_a = SampleAutomatedConnector(key="platform_a")
    connector_registry.register(connector_b)
    connector_registry.register(connector_a)

    all_connectors = connector_registry.list_all()
    assert len(all_connectors) == 2
    assert [c.manifest.connector_key for c in all_connectors] == ["platform_a", "platform_b"]


def test_manifest_tier_validation_on_registration():
    """Registration fails if an automated connector fails to declare mandatory methods."""
    class IncompleteAutomatedConnector(SampleAutomatedConnector):
        @property
        def manifest(self) -> ConnectorManifest:
            return ConnectorManifest(
                connector_key="incomplete_automated",
                name="Incomplete Connector",
                version="1.0.0",
                description="Missing delete method",
                tier=ConnectorTier.AUTOMATED,
                platform="mock",
                supported_methods=["validate", "publish", "get_status"],  # Missing 'delete'
            )

    incomplete = IncompleteAutomatedConnector()
    with pytest.raises(ManifestValidationError) as exc_info:
        connector_registry.register(incomplete)

    assert exc_info.value.code == ErrorCode.MANIFEST_INVALID
    assert "delete" in str(exc_info.value.details.get("missing_methods"))
