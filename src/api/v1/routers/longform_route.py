"""Long-form scene processing FastAPI endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from controllers.longform_scenes import (
    build_multipart_response,
    multipart_media_type,
    process_longform_script,
)
from models.longform import LongformScenesRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/longform_scenes", response_class=StreamingResponse)
async def generate_longform_scenes(
    request: LongformScenesRequest,
) -> StreamingResponse:
    logger.info("POST /longform_scenes invoked (script_length=%d)", len(request.script or ""))

    if not request.script or not request.script.strip():
        raise HTTPException(status_code=422, detail="Script must not be empty.")

    metadata, final_audio = await process_longform_script(request.script)

    return StreamingResponse(
        build_multipart_response(metadata, final_audio),
        media_type=multipart_media_type(),
    )
