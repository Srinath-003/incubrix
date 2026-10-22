import re
from typing import Any, Dict, List, Set
from pydantic import BaseModel, Field, field_validator

from app.core.errors import ManifestValidationError
from app.models.common import ConnectorTier

# Authoritative connector contract method names per Appendix A
VALID_CONTRACT_METHODS: Set[str] = {
    "validate",
    "publish",
    "get_status",
    "delete",
    "fetch_metrics",
    "refresh_auth",
    "build_assist_pack",
}

AUTOMATED_REQUIRED_METHODS: Set[str] = {
    "validate",
    "publish",
    "get_status",
    "delete",
}

ASSISTED_REQUIRED_METHODS: Set[str] = {
    "validate",
    "build_assist_pack",
}


class ConnectorCapabilities(BaseModel):
    """Platform-specific capabilities and limits."""

    media_types: List[str] = Field(default_factory=lambda: ["video"])
    max_file_size_bytes: int = Field(default=500 * 1024 * 1024)
    max_duration_sec: int = Field(default=300)
    supported_aspect_ratios: List[str] = Field(default_factory=lambda: ["16:9", "9:16", "1:1"])
    supports_scheduling: bool = Field(default=False)
    supports_metrics: bool = Field(default=False)
    supports_delete: bool = Field(default=True)
    custom_limits: Dict[str, Any] = Field(default_factory=dict)


class ConnectorManifest(BaseModel):
    """Metadata manifest describing connector capabilities and contract adherence."""

    connector_key: str = Field(..., description="Unique slug identifier for the connector")
    name: str = Field(..., description="Human-readable name of the connector")
    version: str = Field(..., description="Semantic version of the connector")
    description: str = Field(..., description="Detailed description of platform integration")
    tier: ConnectorTier = Field(default=ConnectorTier.AUTOMATED, description="Execution tier (automated or assisted)")
    platform: str = Field(..., description="Target platform identifier")
    auth_type: str = Field(default="oauth2", description="Authentication mechanism")
    supported_methods: List[str] = Field(..., description="List of implemented connector contract methods")
    capabilities: ConnectorCapabilities = Field(default_factory=ConnectorCapabilities)
    manifest_version: str = Field(default="1.0", description="Schema version of this manifest")

    @field_validator("connector_key")
    @classmethod
    def validate_connector_key(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError(
                f"connector_key '{v}' must be alphanumeric lowercase with underscores or hyphens"
            )
        return v

    @field_validator("supported_methods")
    @classmethod
    def validate_supported_methods(cls, methods: List[str]) -> List[str]:
        if not methods:
            raise ValueError("supported_methods list cannot be empty")
        for method in methods:
            if method not in VALID_CONTRACT_METHODS:
                raise ValueError(
                    f"Unknown contract method '{method}'. Valid methods are: {sorted(VALID_CONTRACT_METHODS)}"
                )
        return methods

    def validate_tier_requirements(self) -> None:
        """Validate that the manifest declares all methods required for its tier."""
        declared = set(self.supported_methods)
        if self.tier == ConnectorTier.AUTOMATED:
            missing = AUTOMATED_REQUIRED_METHODS - declared
            if missing:
                raise ManifestValidationError(
                    f"Automated connector '{self.connector_key}' is missing required methods: {sorted(missing)}",
                    details={"connector_key": self.connector_key, "missing_methods": sorted(missing)},
                )
        elif self.tier == ConnectorTier.ASSISTED:
            missing = ASSISTED_REQUIRED_METHODS - declared
            if missing:
                raise ManifestValidationError(
                    f"Assisted connector '{self.connector_key}' is missing required methods: {sorted(missing)}",
                    details={"connector_key": self.connector_key, "missing_methods": sorted(missing)},
                )
