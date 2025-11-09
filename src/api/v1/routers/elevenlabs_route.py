from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException

from controllers.elevenlabs import (
    clear_audio_storage,
    describe_audio_directory,
    synthesize_audio_assets,
    synthesize_longform_audio,
)
from models.elevenlabs_model import LongFormAudioRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate-audio")
async def generate_scene_audio(script: str = Body(..., embed=True)) -> dict[str, object]:
    """Generate per-scene audio clips through the ElevenLabs dialogue API."""

    logger.info("POST /elevenlabs/generate-audio invoked (script_length=%d)", len(script or ""))
    try:
        _, payload = await synthesize_audio_assets(script)
    except HTTPException as http_error:
        logger.warning(
            "ElevenLabs scene audio generation failed (status=%s detail=%s)",
            http_error.status_code,
            http_error.detail,
        )
        raise
    except Exception:
        logger.exception("Unexpected error while generating scene audio")
        raise

    logger.info(
        "POST /elevenlabs/generate-audio completed (outputs=%d)",
        len(payload.get("outputs", [])),
    )
    return payload


@router.get("/audio-files")
async def list_audio_files() -> dict[str, object]:
    """Enumerate locally cached audio files available for reuse or download."""

    logger.info("GET /elevenlabs/audio-files invoked")
    payload = describe_audio_directory()
    logger.info("GET /elevenlabs/audio-files completed (file_count=%d)", payload.get("count", 0))
    return payload


@router.post("/generate-audio/longform")
async def generate_longform_audio(request: LongFormAudioRequest) -> dict[str, object]:
    """Generate long-form narration audio and return stitched output metadata."""

    logger.info(
        "POST /elevenlabs/generate-audio/longform invoked (scenes=%d voice_override=%s)",
        len(request.scenes or []),
        bool(request.voice_id),
    )
    try:
        response = await synthesize_longform_audio(request)
    except HTTPException as http_error:
        logger.warning(
            "Long-form synthesis failed (status=%s detail=%s)",
            http_error.status_code,
            http_error.detail,
        )
        raise
    except Exception:
        logger.exception("Unexpected error during long-form synthesis")
        raise

    logger.info(
        "POST /elevenlabs/generate-audio/longform completed (segments=%d)",
        len(response.get("segments", [])),
    )
    return response


@router.delete("/audio-files")
async def purge_audio_files() -> dict[str, object]:
    """Remove generated audio assets and supporting metadata from disk."""

    logger.info("DELETE /elevenlabs/audio-files invoked")
    try:
        payload = clear_audio_storage()
    except HTTPException as http_error:
        logger.warning(
            "Failed to delete ElevenLabs audio files (status=%s detail=%s)",
            http_error.status_code,
            http_error.detail,
        )
        raise
    except Exception:
        logger.exception("Unexpected error while clearing audio storage")
        raise

    logger.info(
        "DELETE /elevenlabs/audio-files completed (deleted=%d)",
        payload.get("deleted", 0),
    )
    return payload
