from typing import Any, Dict
from fastapi import APIRouter

from app.core.database import db_manager

router = APIRouter(tags=["Health & Readiness"])


@router.get("/health", summary="Liveness check")
async def get_health() -> Dict[str, Any]:
    """Liveness probe.
    
    Returns 200 as long as the application process is running.
    Does NOT fail if MongoDB is unreachable, ensuring container orchestrators
    do not misinterpret database issues as process crashes.
    """
    return {"status": "healthy"}


@router.get("/ready", summary="Readiness check")
async def get_readiness() -> Dict[str, Any]:
    """Readiness probe.
    
    Verifies live connectivity to MongoDB.
    Returns 200 if MongoDB is reachable, or 503 if unreachable.
    """
    await db_manager.check_ready()
    return {"status": "ready", "database": "connected"}
