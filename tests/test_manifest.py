import pytest
from pydantic import ValidationError

from app.core.errors import ManifestValidationError
from app.models.common import ConnectorTier
from app.models.manifest import ConnectorManifest


def test_valid_manifest_creation():
    """Valid manifest is constructed with all required fields."""
    manifest = ConnectorManifest(
        connector_key="bluesky_v1",
        name="Bluesky Destination Connector",
        version="1.0.0",
        description="Publishes video posts to Bluesky via AT Protocol",
        tier=ConnectorTier.AUTOMATED,
        platform="bluesky",
        auth_type="app_password",
        supported_methods=["validate", "publish", "get_status", "delete"],
    )
    assert manifest.connector_key == "bluesky_v1"
    assert manifest.name == "Bluesky Destination Connector"
    assert manifest.tier == ConnectorTier.AUTOMATED
    manifest.validate_tier_requirements()


def test_invalid_connector_key_format():
    """Connector keys with invalid characters or uppercase fail validation."""
    with pytest.raises(ValidationError) as exc_info:
        ConnectorManifest(
            connector_key="Invalid-Key With Spaces!",
            name="Invalid Key",
            version="1.0.0",
            description="Bad key",
            platform="bad",
            supported_methods=["validate"],
        )
    assert "connector_key" in str(exc_info.value)


def test_unknown_contract_method():
    """Manifest cannot declare non-standard or invented method names."""
    with pytest.raises(ValidationError) as exc_info:
        ConnectorManifest(
            connector_key="test_unknown_method",
            name="Unknown Method",
            version="1.0.0",
            description="Attempts to declare unknown method",
            platform="mock",
            supported_methods=["validate", "invented_method_foo"],
        )
    assert "Unknown contract method 'invented_method_foo'" in str(exc_info.value)


def test_empty_supported_methods_rejected():
    """Manifest cannot declare an empty list of supported methods."""
    with pytest.raises(ValidationError) as exc_info:
        ConnectorManifest(
            connector_key="test_empty_methods",
            name="Empty Methods",
            version="1.0.0",
            description="No methods",
            platform="mock",
            supported_methods=[],
        )
    assert "supported_methods list cannot be empty" in str(exc_info.value)


def test_assisted_tier_requirements():
    """Assisted tier manifests must declare build_assist_pack and validate."""
    incomplete_assisted = ConnectorManifest(
        connector_key="incomplete_assisted",
        name="Incomplete Assisted",
        version="1.0.0",
        description="Assisted missing build_assist_pack",
        tier=ConnectorTier.ASSISTED,
        platform="manual_platform",
        supported_methods=["validate"],
    )
    with pytest.raises(ManifestValidationError) as exc_info:
        incomplete_assisted.validate_tier_requirements()
    assert "build_assist_pack" in str(exc_info.value.details.get("missing_methods"))
