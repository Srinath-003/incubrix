import logging
from typing import Any, Dict, Optional
import httpx

from app.config import get_settings
from app.connectors.base import BaseConnector
from app.core.errors import (
    AmbiguousTimeoutError,
    AuthenticationError,
    ContentRejectedError,
    ErrorCode,
    IncuBrixError,
    PlatformUnavailableError,
    RateLimitedError,
    SecurityViolationError,
)
from app.core.security import validate_destination_url
from app.models.common import Connection, ConnectorTier, Destination, Rendition
from app.models.connector import DeleteResponse, PublishResponse, StatusResponse, ValidateResponse
from app.models.manifest import ConnectorCapabilities, ConnectorManifest
from app.simulation.adapter import SimulationAdapter

logger = logging.getLogger("incubrix.connectors.discourse")


class DiscourseConnector(BaseConnector):
    """Production destination connector adapter for Discourse community forums.
    
    Adheres strictly to the Appendix A connector contract.
    Operates safely in simulation mode by default with ZERO external network calls.
    In real mode, interacts with the documented Discourse API (POST /posts.json).
    """

    @property
    def manifest(self) -> ConnectorManifest:
        return ConnectorManifest(
            connector_key="discourse",
            name="Discourse Forum Connector",
            version="1.0.0",
            description="Publishes and manages discussion topics on Discourse community forums via REST API",
            tier=ConnectorTier.AUTOMATED,
            platform="discourse",
            auth_type="api_key",
            supported_methods=["validate", "publish", "get_status", "delete"],
            capabilities=ConnectorCapabilities(
                media_types=["video", "image", "text", "link"],
                max_file_size_bytes=50 * 1024 * 1024,
                max_duration_sec=300,
                supported_aspect_ratios=["16:9", "9:16", "1:1"],
                supports_scheduling=False,
                supports_metrics=False,
                supports_delete=True,
                custom_limits={
                    "min_title_length": 5,
                    "max_title_length": 255,
                    "min_body_length": 10,
                },
            ),
            supported_surfaces=["topic", "post"],
            rate_limits={"posts_per_minute": 20, "burst": 5},
            auth_requirements={
                "api_key": "Discourse API Key (global or user key)",
                "api_username": "Discourse API Username (or system)",
            },
            instance_parameters={
                "instance_url": "Base URL of Discourse forum (e.g. https://discourse.example.com)",
                "category": "Discourse Category ID (integer) or category slug",
            },
            error_mapping={
                "401": "AUTHENTICATION_ERROR",
                "403": "AUTHENTICATION_ERROR",
                "404": "NOT_FOUND",
                "422": "CONTENT_REJECTED",
                "429": "RATE_LIMITED",
                "502": "PLATFORM_UNAVAILABLE",
                "503": "PLATFORM_UNAVAILABLE",
                "504": "PLATFORM_UNAVAILABLE",
            },
            enabled=True,
        )

    def _extract_instance_url(self, destination: Destination | Dict[str, Any]) -> str:
        dest_dict = destination.model_dump() if isinstance(destination, Destination) else destination
        settings = dest_dict.get("settings", {})
        return settings.get("instance_url") or settings.get("base_url") or ""

    def _extract_category(self, destination: Destination | Dict[str, Any]) -> Optional[Any]:
        dest_dict = destination.model_dump() if isinstance(destination, Destination) else destination
        settings = dest_dict.get("settings", {})
        return settings.get("category") or settings.get("category_id")

    def _extract_credentials(self, connection: Connection | Dict[str, Any]) -> Tuple_Credentials:
        conn_dict = connection.model_dump() if isinstance(connection, Connection) else connection
        creds = conn_dict.get("credentials", {})
        api_key = creds.get("api_key") or creds.get("Api-Key")
        api_username = creds.get("api_username") or creds.get("Api-Username") or "system"
        return api_key, api_username

    async def validate(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
    ) -> ValidateResponse:
        """Validate rendition fields, destination URL, and connection credentials for Discourse."""
        violations = []
        rend_dict = rendition.model_dump() if isinstance(rendition, Rendition) else rendition
        dest_dict = destination.model_dump() if isinstance(destination, Destination) else destination
        conn_dict = connection.model_dump() if isinstance(connection, Connection) else connection

        # 1. Rendition validation
        title = (rend_dict.get("title") or "").strip()
        caption = (rend_dict.get("caption") or "").strip()

        if not title:
            violations.append("Discourse topic requires a non-empty title")
        elif len(title) < 5:
            violations.append("Discourse title is too short (minimum 5 characters)")
        elif len(title) > 255:
            violations.append("Discourse title is too long (maximum 255 characters)")

        if not caption:
            violations.append("Discourse topic requires post body copy (caption)")
        elif len(caption) < 10:
            violations.append("Discourse post body is too short (minimum 10 characters)")

        # 2. Destination validation
        instance_url = self._extract_instance_url(destination)
        if not instance_url:
            violations.append("Discourse destination settings must specify 'instance_url'")
        else:
            try:
                settings = get_settings()
                validate_destination_url(instance_url, allow_local=settings.allow_local_destinations)
            except SecurityViolationError as err:
                violations.append(str(err.message))

        category = self._extract_category(destination)
        if category is None:
            violations.append("Discourse destination settings must specify 'category' or 'category_id'")

        # 3. Connection validation
        api_key, _ = self._extract_credentials(connection)
        if not api_key:
            violations.append("Discourse connection credentials must include 'api_key'")

        return ValidateResponse(ok=len(violations) == 0, violations=violations)

    async def publish(
        self,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
        idempotency_key: str,
    ) -> PublishResponse:
        """Publish topic to Discourse forum or execute simulated publish if simulation mode is active."""
        settings = get_settings()

        # Safe simulation mode intercept
        if settings.simulation_mode:
            logger.info("Discourse publish intercepted by active SIMULATION MODE")
            return SimulationAdapter.publish(
                rendition=rendition,
                destination=destination,
                connection=connection,
                idempotency_key=idempotency_key,
                platform="discourse",
            )

        # Real platform publishing execution
        val_res = await self.validate(rendition, destination, connection)
        if not val_res.ok:
            raise ContentRejectedError(
                "Discourse pre-publish validation failed",
                details={"violations": val_res.violations},
            )

        instance_url = self._extract_instance_url(destination)
        instance_url = validate_destination_url(instance_url, allow_local=settings.allow_local_destinations)
        api_key, api_username = self._extract_credentials(connection)

        rend_dict = rendition.model_dump() if isinstance(rendition, Rendition) else rendition
        category = self._extract_category(destination)

        payload: Dict[str, Any] = {
            "title": rend_dict.get("title"),
            "raw": rend_dict.get("caption"),
        }
        if category is not None:
            payload["category"] = category
        if rend_dict.get("tags"):
            payload["tags"] = rend_dict.get("tags")

        headers = {
            "Api-Key": str(api_key),
            "Api-Username": str(api_username),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        target_endpoint = f"{instance_url.rstrip('/')}/posts.json"
        logger.info("Dispatching Discourse topic creation request to %s (user: %s)", target_endpoint, api_username)

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
                response = await client.post(target_endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("Discourse publish request timed out: %s", exc)
            raise AmbiguousTimeoutError(
                "Discourse request timed out before confirmation; post creation is uncertain.",
                details={"destination": instance_url},
            )
        except httpx.RequestError as exc:
            logger.warning("Discourse network error during publish: %s", exc)
            raise PlatformUnavailableError(
                f"Discourse network error: {type(exc).__name__}",
                details={"destination": instance_url},
            )

        # Map response status
        if response.status_code in (200, 201):
            data = response.json()
            post_id = str(data.get("id"))
            topic_id = data.get("topic_id") or post_id
            topic_slug = data.get("topic_slug", "topic")
            live_url = f"{instance_url.rstrip('/')}/t/{topic_slug}/{topic_id}"
            return PublishResponse(
                platform_post_id=post_id,
                live_url=live_url,
                status="published",
            )
        elif response.status_code in (401, 403):
            raise AuthenticationError(
                "Discourse authentication failed. Invalid API key or username.",
                details={"status_code": response.status_code},
            )
        elif response.status_code == 429:
            raise RateLimitedError(
                "Discourse rate limit exceeded. Please retry later.",
                details={"status_code": 429},
            )
        elif response.status_code == 422:
            try:
                err_body = response.json()
                errors = err_body.get("errors", ["Content was rejected by Discourse"])
            except Exception:
                errors = [response.text]
            raise ContentRejectedError(
                f"Discourse rejected content: {', '.join(str(e) for e in errors)}",
                details={"errors": errors, "status_code": 422},
            )
        elif response.status_code in (502, 503, 504):
            raise PlatformUnavailableError(
                "Discourse service is currently unavailable.",
                details={"status_code": response.status_code},
            )
        else:
            raise IncuBrixError(
                code=ErrorCode.PUBLISH_FAILED,
                message=f"Discourse returned unexpected status code {response.status_code}",
                status_code=500,
                retryable=False,
                details={"status_code": response.status_code},
            )

    async def get_status(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> StatusResponse:
        """Inspect status of Discourse post."""
        settings = get_settings()

        if settings.simulation_mode or platform_post_id.startswith("sim_"):
            return SimulationAdapter.get_status(platform_post_id, connection)

        # In real mode, connection settings or default test URL
        dest_url = settings.discourse_test_url
        if not dest_url:
            # Fallback to simulation adapter if no live test URL is configured
            return SimulationAdapter.get_status(platform_post_id, connection)

        instance_url = validate_destination_url(dest_url, allow_local=settings.allow_local_destinations)
        api_key, api_username = self._extract_credentials(connection)

        headers = {
            "Api-Key": str(api_key or ""),
            "Api-Username": str(api_username or "system"),
            "Accept": "application/json",
        }

        target_endpoint = f"{instance_url.rstrip('/')}/posts/{platform_post_id}.json"

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
                response = await client.get(target_endpoint, headers=headers)
        except httpx.TimeoutException:
            raise AmbiguousTimeoutError("Discourse status query timed out.")
        except httpx.RequestError as exc:
            raise PlatformUnavailableError(f"Discourse connection failed: {exc}")

        if response.status_code == 200:
            data = response.json()
            is_deleted = bool(data.get("deleted_at"))
            status = "deleted" if is_deleted else "published"
            topic_id = data.get("topic_id")
            topic_slug = data.get("topic_slug", "topic")
            live_url = f"{instance_url.rstrip('/')}/t/{topic_slug}/{topic_id}" if not is_deleted else None
            return StatusResponse(status=status, live_url=live_url)
        elif response.status_code == 404:
            raise IncuBrixError(
                code=ErrorCode.NOT_FOUND,
                message=f"Post '{platform_post_id}' not found on Discourse forum",
                status_code=404,
                details={"platform_post_id": platform_post_id},
            )
        elif response.status_code in (401, 403):
            raise AuthenticationError(
                "Discourse authentication failed while checking post status",
                details={"status_code": response.status_code},
            )
        else:
            raise PlatformUnavailableError(
                f"Discourse returned error status {response.status_code}",
                details={"status_code": response.status_code},
            )

    async def delete(
        self,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> DeleteResponse:
        """Safely delete post on Discourse instance."""
        settings = get_settings()

        if settings.simulation_mode or platform_post_id.startswith("sim_"):
            return SimulationAdapter.delete(platform_post_id, connection)

        # Deletion guard: must be configured test instance
        test_url = settings.discourse_test_url
        if not test_url and not settings.allow_local_destinations:
            raise SecurityViolationError(
                "Deletion rejected: deletion requires simulation mode or an explicitly configured owned test instance."
            )

        instance_url = validate_destination_url(test_url or "http://localhost", allow_local=settings.allow_local_destinations)
        api_key, api_username = self._extract_credentials(connection)

        headers = {
            "Api-Key": str(api_key or ""),
            "Api-Username": str(api_username or "system"),
            "Accept": "application/json",
        }

        target_endpoint = f"{instance_url.rstrip('/')}/posts/{platform_post_id}.json"

        try:
            async with httpx.AsyncClient(timeout=10.0, verify=True) as client:
                response = await client.delete(target_endpoint, headers=headers)
        except httpx.RequestError as exc:
            raise PlatformUnavailableError(f"Discourse delete request failed: {exc}")

        if response.status_code in (200, 204):
            return DeleteResponse(deleted=True)
        elif response.status_code == 404:
            raise IncuBrixError(
                code=ErrorCode.NOT_FOUND,
                message=f"Post '{platform_post_id}' not found for deletion",
                status_code=404,
            )
        elif response.status_code in (401, 403):
            raise AuthenticationError("Discourse authentication failed during deletion")
        else:
            raise PlatformUnavailableError(f"Discourse delete returned status {response.status_code}")


Tuple_Credentials = tuple[Optional[str], str]
