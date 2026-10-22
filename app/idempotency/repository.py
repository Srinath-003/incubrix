import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple

from app.core.database import CollectionNames, db_manager
from app.core.errors import AmbiguousTimeoutError, IdempotencyConflictError
from app.models.common import Destination, Rendition

logger = logging.getLogger("incubrix.idempotency")


def compute_request_hash(
    rendition: Rendition | Dict[str, Any],
    destination: Destination | Dict[str, Any],
) -> str:
    """Compute a canonical SHA-256 hash of the publish request payload.
    
    CRITICAL: Connection credentials MUST NEVER be included in the idempotency hash or stored.
    """
    rend_dict = rendition.model_dump() if isinstance(rendition, Rendition) else dict(rendition)
    dest_dict = destination.model_dump() if isinstance(destination, Destination) else dict(destination)

    # Normalize payload without any credentials or transient identifiers
    normalized = {
        "rendition": {
            "asset_id": rend_dict.get("asset_id"),
            "url": rend_dict.get("url"),
            "media_type": rend_dict.get("media_type"),
            "title": rend_dict.get("title"),
            "caption": rend_dict.get("caption"),
            "tags": sorted(rend_dict.get("tags") or []),
            "extra": rend_dict.get("extra") or {},
        },
        "destination": {
            "platform": dest_dict.get("platform"),
            "account_id": dest_dict.get("account_id"),
            "settings": dest_dict.get("settings") or {},
        },
    }

    canonical_json = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class IdempotencyRepository:
    """Manages durable and in-memory idempotency state for safe publishing operations.
    
    Guarantees:
      - Duplicate identical requests return the cached original response.
      - Conflicting requests with differing payloads raise IdempotencyConflictError (409).
      - Concurrent in-progress executions are safely detected.
      - Never stores credentials or sensitive authorization tokens.
    """

    def __init__(self) -> None:
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._index_ensured: bool = False

    def _make_key(self, connector_key: str, idempotency_key: str) -> str:
        return f"{connector_key}:{idempotency_key}"

    async def _ensure_mongo_index(self) -> None:
        """Ensure unique compound index on connector_key + idempotency_key if MongoDB is connected."""
        if self._index_ensured:
            return
        if db_manager.db is not None:
            try:
                coll = db_manager.db[CollectionNames.IDEMPOTENCY]
                await coll.create_index(
                    [("connector_key", 1), ("idempotency_key", 1)],
                    unique=True,
                    name="uniq_connector_idempotency_key",
                )
                self._index_ensured = True
                logger.info("MongoDB idempotency unique index ensured successfully")
            except Exception as exc:
                logger.debug("Could not ensure MongoDB idempotency index (fallback in-memory active): %s", exc)

    async def acquire_or_get(
        self,
        connector_key: str,
        idempotency_key: str,
        request_hash: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Atomically inspect or acquire an idempotency reservation.
        
        Returns:
          ("acquired", None) -> Caller holds lock and may execute publish
          ("completed", cached_response) -> Reused original result
        Raises:
          IdempotencyConflictError -> Differing request or concurrent in-progress attempt
          AmbiguousTimeoutError -> Previous execution timed out ambiguously
        """
        async with self._lock:
            # 1. Check MongoDB persistence if available
            await self._ensure_mongo_index()
            now_iso = datetime.now(timezone.utc).isoformat()
            full_key = self._make_key(connector_key, idempotency_key)

            existing_record: Optional[Dict[str, Any]] = None

            if db_manager.db is not None:
                try:
                    coll = db_manager.db[CollectionNames.IDEMPOTENCY]
                    existing_record = await coll.find_one(
                        {"connector_key": connector_key, "idempotency_key": idempotency_key}
                    )
                except Exception as exc:
                    logger.debug("MongoDB read failed for idempotency, falling back to memory: %s", exc)

            if existing_record is None:
                existing_record = self._memory_store.get(full_key)

            if existing_record is not None:
                stored_hash = existing_record.get("request_hash")
                status = existing_record.get("status")

                if stored_hash != request_hash:
                    logger.warning(
                        "Idempotency conflict: key '%s' previously used with different payload",
                        idempotency_key,
                    )
                    raise IdempotencyConflictError(
                        f"Idempotency key '{idempotency_key}' was previously used with a different request payload.",
                        details={
                            "idempotency_key": idempotency_key,
                            "connector_key": connector_key,
                        },
                    )

                if status == "completed":
                    logger.info("Reusing completed response for idempotency key '%s'", idempotency_key)
                    return "completed", existing_record.get("response")

                if status == "in_progress":
                    logger.warning("Concurrent execution detected for idempotency key '%s'", idempotency_key)
                    raise IdempotencyConflictError(
                        f"A publish request with idempotency key '{idempotency_key}' is currently in progress.",
                        details={"idempotency_key": idempotency_key, "status": "in_progress"},
                    )

                if status == "uncertain":
                    raise AmbiguousTimeoutError(
                        f"Previous publish operation for key '{idempotency_key}' timed out ambiguously. Reconciliation required before retrying.",
                        details={"idempotency_key": idempotency_key},
                    )

            # Record reservation
            reservation = {
                "connector_key": connector_key,
                "idempotency_key": idempotency_key,
                "request_hash": request_hash,
                "status": "in_progress",
                "response": None,
                "error": None,
                "created_at": now_iso,
                "updated_at": now_iso,
            }

            self._memory_store[full_key] = reservation

            if db_manager.db is not None:
                try:
                    coll = db_manager.db[CollectionNames.IDEMPOTENCY]
                    await coll.update_one(
                        {"connector_key": connector_key, "idempotency_key": idempotency_key},
                        {"$set": reservation},
                        upsert=True,
                    )
                except Exception as exc:
                    logger.debug("MongoDB upsert failed for idempotency reservation: %s", exc)

            return "acquired", None

    async def mark_completed(
        self,
        connector_key: str,
        idempotency_key: str,
        response: Dict[str, Any],
    ) -> None:
        """Mark idempotency record as successfully completed and store response."""
        async with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            full_key = self._make_key(connector_key, idempotency_key)

            if full_key in self._memory_store:
                self._memory_store[full_key]["status"] = "completed"
                self._memory_store[full_key]["response"] = response
                self._memory_store[full_key]["updated_at"] = now_iso

            if db_manager.db is not None:
                try:
                    coll = db_manager.db[CollectionNames.IDEMPOTENCY]
                    await coll.update_one(
                        {"connector_key": connector_key, "idempotency_key": idempotency_key},
                        {"$set": {"status": "completed", "response": response, "updated_at": now_iso}},
                    )
                except Exception as exc:
                    logger.debug("MongoDB update failed for completed idempotency: %s", exc)

    async def mark_failed(
        self,
        connector_key: str,
        idempotency_key: str,
        error_details: Dict[str, Any],
    ) -> None:
        """Mark idempotency record as failed so client may retry."""
        async with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            full_key = self._make_key(connector_key, idempotency_key)

            if full_key in self._memory_store:
                self._memory_store[full_key]["status"] = "failed"
                self._memory_store[full_key]["error"] = error_details
                self._memory_store[full_key]["updated_at"] = now_iso

            if db_manager.db is not None:
                try:
                    coll = db_manager.db[CollectionNames.IDEMPOTENCY]
                    await coll.update_one(
                        {"connector_key": connector_key, "idempotency_key": idempotency_key},
                        {"$set": {"status": "failed", "error": error_details, "updated_at": now_iso}},
                    )
                except Exception as exc:
                    logger.debug("MongoDB update failed for failed idempotency: %s", exc)

    async def mark_uncertain(
        self,
        connector_key: str,
        idempotency_key: str,
        error_details: Dict[str, Any],
    ) -> None:
        """Mark record as uncertain following an ambiguous timeout to prevent unsafe blind retries."""
        async with self._lock:
            now_iso = datetime.now(timezone.utc).isoformat()
            full_key = self._make_key(connector_key, idempotency_key)

            if full_key in self._memory_store:
                self._memory_store[full_key]["status"] = "uncertain"
                self._memory_store[full_key]["error"] = error_details
                self._memory_store[full_key]["updated_at"] = now_iso

            if db_manager.db is not None:
                try:
                    coll = db_manager.db[CollectionNames.IDEMPOTENCY]
                    await coll.update_one(
                        {"connector_key": connector_key, "idempotency_key": idempotency_key},
                        {"$set": {"status": "uncertain", "error": error_details, "updated_at": now_iso}},
                    )
                except Exception as exc:
                    logger.debug("MongoDB update failed for uncertain idempotency: %s", exc)

    def clear(self) -> None:
        """Clear memory state for test isolation."""
        self._memory_store.clear()


# Global singleton repository
idempotency_repository = IdempotencyRepository()
