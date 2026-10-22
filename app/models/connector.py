from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.models.common import Connection, Destination, Rendition


# ---------------------------------------------------------------------------
# 1. validate(rendition, destination, connection) -> {ok, violations[]}
# ---------------------------------------------------------------------------
class ValidateRequest(BaseModel):
    rendition: Rendition | Dict[str, Any] = Field(..., description="Media rendition to validate")
    destination: Destination | Dict[str, Any] = Field(..., description="Target destination settings")
    connection: Connection | Dict[str, Any] = Field(..., description="Platform authentication connection")


class ValidateResponse(BaseModel):
    ok: bool = Field(..., description="Whether validation succeeded")
    violations: List[str] = Field(default_factory=list, description="List of rule/spec violations if not ok")


# ---------------------------------------------------------------------------
# 2. publish(rendition, destination, connection, idempotency_key) -> {platform_post_id, live_url, status}
# ---------------------------------------------------------------------------
class PublishRequest(BaseModel):
    rendition: Rendition | Dict[str, Any] = Field(..., description="Media rendition to publish")
    destination: Destination | Dict[str, Any] = Field(..., description="Target destination settings")
    connection: Connection | Dict[str, Any] = Field(..., description="Platform authentication connection")
    idempotency_key: str = Field(..., description="Unique idempotency key for this publish operation")


class PublishResponse(BaseModel):
    platform_post_id: str = Field(..., description="Unique post ID assigned by the destination platform")
    live_url: Optional[str] = Field(default=None, description="Public URL to published post")
    status: str = Field(..., description="Status of the post (e.g. published, processing, scheduled)")


# ---------------------------------------------------------------------------
# 3. get_status(platform_post_id, connection) -> {status, live_url}
# ---------------------------------------------------------------------------
class StatusRequest(BaseModel):
    platform_post_id: str = Field(..., description="Unique platform post ID to inspect")
    connection: Connection | Dict[str, Any] = Field(..., description="Platform authentication connection")


class StatusResponse(BaseModel):
    status: str = Field(..., description="Current status of the post (e.g. published, failed, deleted)")
    live_url: Optional[str] = Field(default=None, description="Public URL to published post")


# ---------------------------------------------------------------------------
# 4. delete(platform_post_id, connection) -> {deleted}
# ---------------------------------------------------------------------------
class DeleteRequest(BaseModel):
    platform_post_id: str = Field(..., description="Platform post ID to delete")
    connection: Connection | Dict[str, Any] = Field(..., description="Platform authentication connection")


class DeleteResponse(BaseModel):
    deleted: bool = Field(..., description="Whether post deletion succeeded on the platform")


# ---------------------------------------------------------------------------
# 5. Optional fetch_metrics(platform_post_id, connection, since) -> {metrics, fetched_at}
# ---------------------------------------------------------------------------
class MetricsRequest(BaseModel):
    platform_post_id: str = Field(..., description="Platform post ID for metric collection")
    connection: Connection | Dict[str, Any] = Field(..., description="Platform authentication connection")
    since: Optional[str] = Field(default=None, description="ISO timestamp cutoff for metrics")


class MetricsResponse(BaseModel):
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Platform engagement metrics")
    fetched_at: str = Field(..., description="ISO timestamp when metrics were collected")


# ---------------------------------------------------------------------------
# 6. Optional refresh_auth(connection) -> {refreshed, credentials, expires_at}
# ---------------------------------------------------------------------------
class RefreshAuthRequest(BaseModel):
    connection: Connection | Dict[str, Any] = Field(..., description="Connection containing refresh credentials")


class RefreshAuthResponse(BaseModel):
    refreshed: bool = Field(..., description="Whether token refresh succeeded")
    credentials: Dict[str, Any] = Field(default_factory=dict, description="Updated credential tokens")
    expires_at: Optional[str] = Field(default=None, description="New token expiration ISO timestamp")


# ---------------------------------------------------------------------------
# 7. build_assist_pack(rendition, destination) -> {instructions, assets, metadata}
# ---------------------------------------------------------------------------
class AssistPackRequest(BaseModel):
    rendition: Rendition | Dict[str, Any] = Field(..., description="Media rendition for assisted package")
    destination: Destination | Dict[str, Any] = Field(..., description="Destination platform configuration")


class AssistPackResponse(BaseModel):
    instructions: str = Field(..., description="Human-readable publishing instructions for assisted tier")
    assets: List[Dict[str, Any]] = Field(default_factory=list, description="Prepared media asset references")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Copy, hashtags, and destination settings")
