from __future__ import annotations

from fastapi import APIRouter, Body

from controllers.elevenlabs import (
    clear_audio_storage,
    describe_audio_directory,
    synthesize_audio_assets,
)

router = APIRouter()


@router.post("/generate-audio")
async def generate_audio(script: str = Body(..., embed=True)) -> dict[str, object]:
    """Generate per-scene audio clips through the ElevenLabs dialogue API."""

    _, payload = await synthesize_audio_assets(script)
    return payload


@router.get("/audio-files")
async def list_audio_files() -> dict[str, object]:
    """Enumerate locally cached audio files available for reuse or download."""

    return describe_audio_directory()


@router.delete("/audio-files")
async def clear_audio_files() -> dict[str, object]:
    """Remove generated audio assets and supporting metadata from disk."""

    return clear_audio_storage()
