import asyncio
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.core.errors import DatabaseUnavailableError

logger = logging.getLogger(__name__)


class CollectionNames:
    """Planned MongoDB collections for IncuBrix Distribution Network.
    
    Collections are defined here as architectural constants for future phases.
    Per Phase 1 guidelines, unused collections and indexes are not created prematurely.
    Credentials must never be stored in plain text in ordinary documents.
    """

    CONNECTORS = "connectors"
    DESTINATIONS = "destinations"
    CONNECTIONS = "connections"
    JOBS = "jobs"
    IDEMPOTENCY = "idempotency"
    CERTIFICATIONS = "certifications"
    POSTING_EVENTS = "posting_events"
    FILES = "files"


class DatabaseManager:
    """Manages AsyncIOMotorClient connection lifecycle and readiness checks."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    @property
    def client(self) -> Optional[AsyncIOMotorClient]:
        return self._client

    @property
    def db(self) -> Optional[AsyncIOMotorDatabase]:
        return self._db

    async def connect(self) -> None:
        """Initialize MongoDB client connection with configured timeout."""
        if self._client is not None:
            return

        timeout_ms = self._settings.mongodb_timeout_ms
        logger.info(
            "Connecting to MongoDB at %s (database: %s, timeout: %d ms)",
            self._settings.mongodb_uri,
            self._settings.mongodb_db_name,
            timeout_ms,
        )
        self._client = AsyncIOMotorClient(
            self._settings.mongodb_uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
        )
        self._db = self._client[self._settings.mongodb_db_name]

    async def disconnect(self) -> None:
        """Close MongoDB client connection."""
        if self._client is not None:
            logger.info("Closing MongoDB client connection")
            self._client.close()
            self._client = None
            self._db = None

    async def ping(self) -> bool:
        """Verify database connectivity.
        
        Returns True if database responds within timeout, False otherwise.
        Does not raise an exception so callers can handle health/readiness checks gracefully.
        """
        if self._client is None:
            return False

        try:
            # Perform lightweight ping command against the admin database
            timeout_sec = max(1.0, self._settings.mongodb_timeout_ms / 1000.0)
            await asyncio.wait_for(
                self._client.admin.command("ping"),
                timeout=timeout_sec,
            )
            return True
        except Exception as exc:
            logger.warning("MongoDB ping failed: %s", exc)
            return False

    async def check_ready(self) -> None:
        """Readiness check: raises DatabaseUnavailableError if ping fails."""
        is_healthy = await self.ping()
        if not is_healthy:
            raise DatabaseUnavailableError(
                message="MongoDB is unreachable or unresponsive",
                details={
                    "database": "disconnected",
                    "uri": self._settings.mongodb_uri,
                    "db_name": self._settings.mongodb_db_name,
                },
            )


# Global singleton database manager
db_manager = DatabaseManager()


async def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency for accessing the database."""
    if db_manager.db is None:
        raise DatabaseUnavailableError(message="Database client is not initialized")
    return db_manager.db
