"""Main API router for v1 endpoints."""

import logging

from fastapi import APIRouter, Depends

from services.auth import require_current_user

from .routers import (
    auth_route,
    creatomate_route,
    elevenlabs_route,
    freepik_route,
    heygen_route,
    longform_route,
)

logger = logging.getLogger(__name__)

api_router = APIRouter()

protected_dependencies = [Depends(require_current_user)]

api_router.include_router(auth_route.router, prefix="/auth", tags=["auth"])

api_router.include_router(
    elevenlabs_route.router,
    prefix="/elevenlabs",
    tags=["elevenlabs"],
    dependencies=protected_dependencies,
)

api_router.include_router(
    heygen_route.router,
    prefix="/heygen",
    tags=["heygen"],
    dependencies=protected_dependencies,
)

api_router.include_router(
    freepik_route.router,
    prefix="/freepik",
    tags=["freepik"],
    dependencies=protected_dependencies,
)

api_router.include_router(
    creatomate_route.router,
    prefix="/creatomate",
    tags=["creatomate"],
    dependencies=protected_dependencies,
)

api_router.include_router(
    longform_route.router,
    tags=["longform"],
    dependencies=protected_dependencies,
)


@api_router.get("/health", tags=["health"], dependencies=[Depends(require_current_user)])
async def health_check() -> dict[str, str]:
    """Simple health probe so the frontend can verify backend availability."""

    logger.info("Health check request received")
    return {"status": "ok"}
