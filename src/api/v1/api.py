"""Main API router for v1 endpoints."""

import logging

from fastapi import APIRouter

from .routers import (
    creatomate_route,
    elevenlabs_route,
    freepik_route,
    heygen_route,
    longform_route,
)

logger = logging.getLogger(__name__)

api_router = APIRouter()

api_router.include_router(elevenlabs_route.router, prefix="/elevenlabs", tags=["elevenlabs"])

api_router.include_router(heygen_route.router, prefix="/heygen", tags=["heygen"])

api_router.include_router(freepik_route.router, prefix="/freepik", tags=["freepik"])

api_router.include_router(creatomate_route.router, prefix="/creatomate", tags=["creatomate"])

api_router.include_router(longform_route.router, tags=["longform"])


@api_router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple health probe so the frontend can verify backend availability."""

    logger.info("Health check request received")
    return {"status": "ok"}
