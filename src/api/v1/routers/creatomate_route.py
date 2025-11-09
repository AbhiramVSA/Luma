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
async def render_video(
    request: CreatomateRenderRequest,
) -> CreatomateRenderResponse:
    """Execute the full pipeline: audio -> HeyGen videos -> Creatomate render."""

    logger.info(
        "POST /creatomate/render invoked (template=%s scenes=%d wait_for_render=%s)",
        request.template_id or "auto",
        len(request.scenes),
        request.wait_for_render,
    )
    try:
        response = await orchestrate_creatomate_render(request)
    except HTTPException as exc:
        logger.warning(
            "Creatomate orchestration failed (status=%s detail=%s)",
            exc.status_code,
            exc.detail,
        )
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Creatomate orchestration failed: %%s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "POST /creatomate/render completed (status=%s errors=%d)",
        response.status,
        len(response.errors),
    )
    return response


@router.post("/upload-image")
async def upload_scene_image(
    scene_id: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
) -> dict[str, str]:
    """Accept a scene image upload and persist it for Creatomate rendering."""
    logger.info(
        "POST /creatomate/upload-image invoked (scene_id=%s filename=%s)",
        scene_id,
        file.filename,
    )
    try:
        response = await save_scene_image(scene_id, file)
    except HTTPException as exc:
        logger.warning(
            "Creatomate image upload failed (status=%s detail=%s)",
            exc.status_code,
            exc.detail,
        )
        raise
    except Exception:
        logger.exception("Unexpected error during Creatomate image upload")
        raise

    logger.info("POST /creatomate/upload-image completed (scene_id=%s)", scene_id)
    return response
