from typing import Any, Dict, List
from fastapi import APIRouter

from app.connectors.registry import connector_registry

router = APIRouter(prefix="/api/v1/connectors", tags=["Connectors"])


@router.get("", summary="List registered connectors")
async def list_connectors() -> Dict[str, List[Dict[str, Any]]]:
    """Return all registered destination connectors and their manifests."""
    connectors = connector_registry.list_all()
    return {
        "connectors": [c.manifest.model_dump() for c in connectors]
    }


@router.get("/{key}/manifest", summary="Get connector manifest")
async def get_connector_manifest(key: str) -> Dict[str, Any]:
    """Retrieve the capability and contract manifest for a specific connector.
    
    Raises 404 with CONNECTOR_NOT_FOUND if connector is not registered.
    """
    connector = connector_registry.get(key)
    return connector.manifest.model_dump()
