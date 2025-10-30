"""FastAPI routes orchestrating Creatomate renders."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from controllers.creatomate import orchestrate_creatomate_render, save_scene_image
from models.creatomate import CreatomateRenderRequest, CreatomateRenderResponse

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/render", response_model=CreatomateRenderResponse)
async def render_creatomate_video(
    request: CreatomateRenderRequest,
) -> CreatomateRenderResponse:
    """Execute the full pipeline: audio -> HeyGen videos -> Creatomate render."""

    try:
        return await orchestrate_creatomate_render(request)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Creatomate orchestration failed: %%s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/upload-image")
async def upload_creatomate_image(
    scene_id: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
) -> dict[str, str]:
    """Accept a scene image upload and persist it for Creatomate rendering."""
    return await save_scene_image(scene_id, file)
