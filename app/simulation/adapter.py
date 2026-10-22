import logging
from typing import Any, Dict

from app.models.common import Connection, Destination, Rendition
from app.models.connector import DeleteResponse, PublishResponse, StatusResponse, ValidateResponse
from app.simulation.store import simulation_store

logger = logging.getLogger("incubrix.simulation")


class SimulationAdapter:
    """Isolated test adapter executing simulated connector operations with ZERO external HTTP requests.
    
    All state is kept strictly in-memory and isolated from production connector logic.
    """

    @classmethod
    def validate(
        cls,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
    ) -> ValidateResponse:
        """Perform simulation validation without requiring real credentials."""
        logger.info("[SIMULATION MODE] Executing simulated validation")
        violations = []
        rend_dict = rendition.model_dump() if isinstance(rendition, Rendition) else rendition
        if not rend_dict.get("title") and not rend_dict.get("caption") and not rend_dict.get("url"):
            violations.append("Simulated rendition must contain at least title, caption, or URL")
        return ValidateResponse(ok=len(violations) == 0, violations=violations)

    @classmethod
    def publish(
        cls,
        rendition: Rendition | Dict[str, Any],
        destination: Destination | Dict[str, Any],
        connection: Connection | Dict[str, Any],
        idempotency_key: str,
        platform: str = "mock",
    ) -> PublishResponse:
        """Create deterministic mock post in simulation store without network calls."""
        rend_dict = rendition.model_dump() if isinstance(rendition, Rendition) else rendition
        dest_dict = destination.model_dump() if isinstance(destination, Destination) else destination

        title = rend_dict.get("title") or "Simulated Topic"
        caption = rend_dict.get("caption") or ""
        dest_url = dest_dict.get("settings", {}).get("instance_url") or dest_dict.get("settings", {}).get("base_url") or "https://mock.platform.local"

        logger.info(
            "[SIMULATION MODE] Publishing simulated topic to platform '%s' (destination: %s)",
            platform,
            dest_url,
        )

        sim_post = simulation_store.record_post(
            platform=platform,
            title=title,
            caption=caption,
            destination_url=dest_url,
            idempotency_key=idempotency_key,
        )

        return PublishResponse(
            platform_post_id=sim_post.platform_post_id,
            live_url=sim_post.live_url,
            status=sim_post.status,
        )

    @classmethod
    def get_status(
        cls,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> StatusResponse:
        """Retrieve status of simulated post."""
        logger.info("[SIMULATION MODE] Inspecting post status for '%s'", platform_post_id)
        post = simulation_store.get_post(platform_post_id)
        if post:
            return StatusResponse(
                status=post.status,
                live_url=post.live_url if not post.is_deleted else None,
            )
        # Deterministic fallback for mock IDs
        return StatusResponse(
            status="published",
            live_url=f"https://simulated.destination/posts/{platform_post_id}",
        )

    @classmethod
    def delete(
        cls,
        platform_post_id: str,
        connection: Connection | Dict[str, Any],
    ) -> DeleteResponse:
        """Simulate deletion of post."""
        logger.info("[SIMULATION MODE] Deleting post '%s'", platform_post_id)
        simulation_store.delete_post(platform_post_id)
        return DeleteResponse(deleted=True)
