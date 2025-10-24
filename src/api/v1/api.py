"""Main API router for v1 endpoints."""

from fastapi import APIRouter

from .routers import elevenlabs_route, freepik_route, heygen_route

api_router = APIRouter()

api_router.include_router(elevenlabs_route.router, prefix="/elevenlabs", tags=["elevenlabs"])

api_router.include_router(heygen_route.router, prefix="/heygen", tags=["heygen"])

api_router.include_router(freepik_route.router, prefix="/freepik", tags=["freepik"])


@api_router.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Simple health probe so the frontend can verify backend availability."""

    return {"status": "ok"}
