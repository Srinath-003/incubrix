from datetime import datetime, timezone
import hashlib
from typing import Dict, Optional
from pydantic import BaseModel, Field


class SimulatedPost(BaseModel):
    """Represents an isolated simulated platform post."""

    platform_post_id: str
    live_url: str
    status: str = "published"
    platform: str
    destination_url: str
    title: str = ""
    caption: str = ""
    idempotency_key: str
    created_at: str
    is_deleted: bool = False


class SimulationStore:
    """Dedicated in-memory store for isolated simulation mode state."""

    def __init__(self) -> None:
        self._posts: Dict[str, SimulatedPost] = {}

    def record_post(
        self,
        platform: str,
        title: str,
        caption: str,
        destination_url: str,
        idempotency_key: str,
    ) -> SimulatedPost:
        """Create and store a deterministic simulated post."""
        key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:10]
        post_id = f"sim_{platform}_{key_hash}"
        clean_url = destination_url.rstrip("/") if destination_url else f"https://mock.{platform}.local"
        live_url = f"{clean_url}/t/simulated-{platform}-post/{post_id}"

        now_iso = datetime.now(timezone.utc).isoformat()
        sim_post = SimulatedPost(
            platform_post_id=post_id,
            live_url=live_url,
            status="published",
            platform=platform,
            destination_url=clean_url,
            title=title,
            caption=caption,
            idempotency_key=idempotency_key,
            created_at=now_iso,
            is_deleted=False,
        )
        self._posts[post_id] = sim_post
        return sim_post

    def get_post(self, platform_post_id: str) -> Optional[SimulatedPost]:
        """Retrieve simulated post by its platform post ID."""
        return self._posts.get(platform_post_id)

    def delete_post(self, platform_post_id: str) -> bool:
        """Mark simulated post as deleted. Returns True if found."""
        if platform_post_id in self._posts:
            self._posts[platform_post_id].is_deleted = True
            self._posts[platform_post_id].status = "deleted"
            return True
        return False

    def clear(self) -> None:
        """Clear all simulation state for test isolation."""
        self._posts.clear()


# Global simulation store singleton
simulation_store = SimulationStore()
