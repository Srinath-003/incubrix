from typing import Any, Dict
from fastapi import APIRouter, Body, Request
from pydantic import ValidationError

from app.connectors.registry import connector_registry
from app.core.errors import MethodNotSupportedError
from app.models.connector import (
    AssistPackRequest,
    DeleteRequest,
    MetricsRequest,
    PublishRequest,
    RefreshAuthRequest,
    StatusRequest,
    ValidateRequest,
)

router = APIRouter(prefix="/connector/v1", tags=["Connector RPC"])


@router.post("/{connector_key}/{method}", summary="Invoke connector contract method")
async def invoke_connector_method(
    connector_key: str,
    method: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
) -> Dict[str, Any]:
    """Execute authoritative Appendix A connector contract method.
    
    Routes invocations for:
      - validate(rendition, destination, connection)
      - publish(rendition, destination, connection, idempotency_key)
      - get_status(platform_post_id, connection)
      - delete(platform_post_id, connection)
      - fetch_metrics(platform_post_id, connection, since)
      - refresh_auth(connection)
      - build_assist_pack(rendition, destination)
      
    Connectors are stateless and do NOT write directly to IncuBrix's database.
    """
    connector = connector_registry.get(connector_key)

    if method not in connector.manifest.supported_methods:
        raise MethodNotSupportedError(connector_key=connector_key, method=method)

    if method == "validate":
        req_val = ValidateRequest.model_validate(payload)
        resp = await connector.validate(
            rendition=req_val.rendition,
            destination=req_val.destination,
            connection=req_val.connection,
        )
        return resp.model_dump()

    elif method == "publish":
        req_pub = PublishRequest.model_validate(payload)
        resp = await connector.publish(
            rendition=req_pub.rendition,
            destination=req_pub.destination,
            connection=req_pub.connection,
            idempotency_key=req_pub.idempotency_key,
        )
        return resp.model_dump()

    elif method == "get_status":
        req_stat = StatusRequest.model_validate(payload)
        resp = await connector.get_status(
            platform_post_id=req_stat.platform_post_id,
            connection=req_stat.connection,
        )
        return resp.model_dump()

    elif method == "delete":
        req_del = DeleteRequest.model_validate(payload)
        resp = await connector.delete(
            platform_post_id=req_del.platform_post_id,
            connection=req_del.connection,
        )
        return resp.model_dump()

    elif method == "fetch_metrics":
        req_met = MetricsRequest.model_validate(payload)
        resp = await connector.fetch_metrics(
            platform_post_id=req_met.platform_post_id,
            connection=req_met.connection,
            since=req_met.since,
        )
        return resp.model_dump()

    elif method == "refresh_auth":
        req_ref = RefreshAuthRequest.model_validate(payload)
        resp = await connector.refresh_auth(
            connection=req_ref.connection,
        )
        return resp.model_dump()

    elif method == "build_assist_pack":
        req_ast = AssistPackRequest.model_validate(payload)
        resp = await connector.build_assist_pack(
            rendition=req_ast.rendition,
            destination=req_ast.destination,
        )
        return resp.model_dump()

    else:
        raise MethodNotSupportedError(connector_key=connector_key, method=method)
