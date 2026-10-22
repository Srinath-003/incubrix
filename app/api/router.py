from fastapi import APIRouter

from app.api.routes import connector_rpc, connectors, health

api_router = APIRouter()

# Mount health & readiness probes at root level (/health, /ready)
api_router.include_router(health.router)

# Mount connector query endpoints (/api/v1/connectors)
api_router.include_router(connectors.router)

# Mount connector RPC contract endpoints (/connector/v1)
api_router.include_router(connector_rpc.router)
