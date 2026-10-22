import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI

from app.api.router import api_router
from app.config import Settings, get_settings
from app.core.database import db_manager
from app.core.handlers import register_exception_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("incubrix")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for database connection lifecycle."""
    settings = get_settings()
    logger.info("Starting %s in [%s] environment", settings.app_name, settings.app_env)

    # Initialize database connection on startup
    try:
        await db_manager.connect()
        # Verify initial connectivity
        if await db_manager.ping():
            logger.info("MongoDB connectivity verified successfully")
        else:
            logger.warning("MongoDB ping failed on startup; readiness probe will report unavailable")
    except Exception as exc:
        logger.warning("MongoDB initial connection error: %s. Application process will still run.", exc)

    yield

    # Clean shutdown
    logger.info("Shutting down %s", settings.app_name)
    try:
        await db_manager.disconnect()
    except Exception as exc:
        logger.warning("Error during MongoDB disconnect: %s", exc)


def create_app(settings: Settings | None = None) -> FastAPI:
    """FastAPI application factory."""
    current_settings = settings or get_settings()

    application = FastAPI(
        title=current_settings.app_name,
        version="0.1.0",
        description="IncuBrix Distribution Engine: Long-Tail Destination Network",
        lifespan=lifespan,
    )

    # Register standardized error handlers enforcing the assessment error envelope
    register_exception_handlers(application)

    # Mount API routers
    application.include_router(api_router)

    return application


app = create_app()
