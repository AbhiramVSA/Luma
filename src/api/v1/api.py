"""Main API router for v1 endpoints."""

from fastapi import APIRouter

from .routers import elevenlabs_gen

api_router = APIRouter()
api_router.include_router(
    elevenlabs_gen.router, prefix="/elevenlabs", tags=["elevenlabs"]
)
