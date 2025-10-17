"""Main API router for v1 endpoints."""

from fastapi import APIRouter

from .routers import elevenlabs_route, heygen_route

api_router = APIRouter()

api_router.include_router(
    elevenlabs_route.router, prefix="/elevenlabs", tags=["elevenlabs"]
)

api_router.include_router(
    heygen_route.router, prefix="/heygen", tags=["heygen"]
)
