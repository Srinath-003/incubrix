from typing import Any, Dict, Optional
from fastapi import APIRouter, Body, Header, Request

from app.connectors.registry import connector_registry
from app.core.errors import (
    AmbiguousTimeoutError,
    IdempotencyConflictError,
    MethodNotSupportedError,
    PolicyViolationError,
)
from app.idempotency.repository import compute_request_hash, idempotency_repository
from app.models.connector import (
    AssistPackRequest,
    DeleteRequest,
    MetricsRequest,
    PublishRequest,
    RefreshAuthRequest,
    StatusRequest,
    ValidateRequest,
)
from app.policies.rules import PolicyEngine

router = APIRouter(prefix="/connector/v1", tags=["Connector RPC"])


@router.post("/{connector_key}/{method}", summary="Invoke connector contract method")
async def invoke_connector_method(
    connector_key: str,
    method: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
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
      
    Features:
      - Reconciles Idempotency-Key HTTP header with request body.
      - Enforces pre-publish policy validation hook.
      - Provides durable and in-memory publish idempotency.
      - Dispatches safe simulation mode or real platform adapter.
    """
    # 1. Retrieve connector; raises ConnectorNotFoundError (404) or ConnectorDisabledError (403)
    connector = connector_registry.get(connector_key, check_enabled=True)

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
        # Reconcile Idempotency-Key header with payload
        body_key = payload.get("idempotency_key")
        if idempotency_key_header and body_key:
            if idempotency_key_header != body_key:
                raise IdempotencyConflictError(
                    "Conflicting idempotency keys: Idempotency-Key header does not match body idempotency_key",
                    details={"header_key": idempotency_key_header, "body_key": body_key},
                )
        elif idempotency_key_header and not body_key:
            payload["idempotency_key"] = idempotency_key_header

        req_pub = PublishRequest.model_validate(payload)

        # 2. Enforce pre-publish policy hook
        policy_result = PolicyEngine.evaluate(req_pub.rendition, req_pub.destination)
        if not policy_result.ok:
            raise PolicyViolationError(
                "Pre-publish policy check failed",
                details={"violations": policy_result.violations},
            )

        # 3. Check and acquire idempotency reservation
        request_hash = compute_request_hash(req_pub.rendition, req_pub.destination)
        action, cached_response = await idempotency_repository.acquire_or_get(
            connector_key=connector_key,
            idempotency_key=req_pub.idempotency_key,
            request_hash=request_hash,
        )

        if action == "completed" and cached_response:
            return cached_response

        # 4. Execute connector publish
        try:
            resp = await connector.publish(
                rendition=req_pub.rendition,
                destination=req_pub.destination,
                connection=req_pub.connection,
                idempotency_key=req_pub.idempotency_key,
            )
            resp_dict = resp.model_dump()
            await idempotency_repository.mark_completed(
                connector_key=connector_key,
                idempotency_key=req_pub.idempotency_key,
                response=resp_dict,
            )
            return resp_dict
        except AmbiguousTimeoutError as exc:
            await idempotency_repository.mark_uncertain(
                connector_key=connector_key,
                idempotency_key=req_pub.idempotency_key,
                error_details={"code": exc.code, "message": exc.message},
            )
            raise
        except Exception as exc:
            await idempotency_repository.mark_failed(
                connector_key=connector_key,
                idempotency_key=req_pub.idempotency_key,
                error_details={"error_type": type(exc).__name__, "message": str(exc)},
            )
            raise

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
