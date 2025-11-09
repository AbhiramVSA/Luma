"""HeyGen FastAPI routes for asset upload and video generation."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

import controllers.heygen as heygen_controller
from config.config import settings
from controllers.generate_video import upload_audio_assets
from models.heygen import (
    HeyGenAvatarAgentOutput,
    HeyGenAvatarVideoRequest,
    HeyGenAvatarVideoResponse,
    HeyGenVideoRequest,
    HeyGenVideoResponse,
)
from utils.agents import heygen_avatar_agent

router = APIRouter()

logger = logging.getLogger(__name__)


@router.post("/upload-audio-assets", response_model=dict)
async def trigger_audio_asset_upload(force: bool = False) -> dict[str, Any]:
    """Expose audio upload helper via API."""

    logger.info("POST /heygen/upload-audio-assets invoked (force=%s)", force)
    try:
        result = await upload_audio_assets(force=force)
    except HTTPException as http_error:
        logger.warning(
            "HeyGen audio asset upload failed (status=%s detail=%s)",
            http_error.status_code,
            http_error.detail,
        )
        raise
    except Exception:
        logger.exception("Unexpected error while uploading HeyGen audio assets")
        raise

    logger.info(
        "POST /heygen/upload-audio-assets completed (assets=%d)",
        len(result.get("assets", [])),
    )
    return result


@router.post("/generate-video", response_model=HeyGenVideoResponse)
async def generate_heygen_videos(request: HeyGenVideoRequest) -> HeyGenVideoResponse:
    if not settings.HEYGEN_API_KEY:
        logger.error("HeyGen API key missing for generate-video request")
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    logger.info(
        "POST /heygen/generate-video invoked (script_length=%d force_upload=%s)",
        len(request.script or ""),
        request.force_upload,
    )
    try:
        response = await heygen_controller.generate_video_batch(
            request.script,
            force_upload=request.force_upload,
        )
    except HTTPException as http_error:
        logger.warning(
            "HeyGen video generation failed (status=%s detail=%s)",
            http_error.status_code,
            http_error.detail,
        )
        raise
    except Exception:
        logger.exception("Unexpected error during HeyGen video generation")
        raise

    logger.info(
        "POST /heygen/generate-video completed (status=%s results=%d)",
        response.status,
        len(response.results),
    )
    return response


@router.post("/avatar-iv/generate", response_model=HeyGenAvatarVideoResponse)
async def generate_avatar_iv_video(
    request: HeyGenAvatarVideoRequest,
) -> HeyGenAvatarVideoResponse:
    if not settings.HEYGEN_API_KEY:
        logger.error("HeyGen API key missing for avatar-IV request")
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    logger.info(
        "POST /heygen/avatar-iv/generate invoked (force_upload_audio=%s image_key=%s)",
        request.force_upload_audio,
        request.image_asset_id,
    )
    assets_result = await upload_audio_assets(force=request.force_upload_audio)
    assets = assets_result.get("assets", [])
    if not assets:
        logger.warning("Avatar IV generation failed: no audio assets available")
        raise HTTPException(
            status_code=404,
            detail="No HeyGen audio assets found. Generate narration audio first.",
        )

    asset_lookup = heygen_controller._build_asset_lookup(assets)
    resolved_audio_asset_id, resolved_audio_alias = heygen_controller.resolve_avatar_audio_asset(
        request.script,
        assets,
        asset_lookup,
    )

    if not resolved_audio_asset_id:
        raise HTTPException(
            status_code=404,
            detail="Unable to resolve a HeyGen audio asset id from generated audio.",
        )

    envelope = heygen_controller.build_avatar_agent_envelope(
        request,
        audio_asset_id=resolved_audio_asset_id,
        audio_alias=resolved_audio_alias,
    )

    try:
        agent_output_raw = await heygen_avatar_agent.run(envelope)
        prompts = HeyGenAvatarAgentOutput.model_validate_json(agent_output_raw.output)
    except (ValidationError, json.JSONDecodeError) as validation_error:
        logger.warning("HeyGen avatar agent output invalid: %s", validation_error)
        prompts = heygen_controller.fallback_avatar_prompts(request)
    except Exception as agent_error:  # pragma: no cover - defensive
        logger.warning("HeyGen avatar agent failed: %s", agent_error)
        prompts = heygen_controller.fallback_avatar_prompts(request)

    if request.orientation_hint and prompts.video_orientation != request.orientation_hint:
        prompts.video_orientation = request.orientation_hint
    if request.fit_hint and prompts.fit != request.fit_hint:
        prompts.fit = request.fit_hint
    if request.enhance_motion_override is not None:
        prompts.enhance_custom_motion_prompt = request.enhance_motion_override

    payload: dict[str, Any] = {
        "image_key": request.image_asset_id,
        "video_title": prompts.video_title,
        "video_orientation": prompts.video_orientation,
        "fit": prompts.fit,
        "custom_motion_prompt": prompts.custom_motion_prompt,
        "enhance_custom_motion_prompt": prompts.enhance_custom_motion_prompt,
        "audio_asset_id": resolved_audio_asset_id,
    }

    payload["script"] = prompts.script
    payload["voice_id"] = prompts.voice_id

    try:
        job = heygen_controller._submit_avatar_iv_job(payload)
    except HTTPException as http_error:
        logger.warning(
            "HeyGen avatar IV submission failed (status=%s detail=%s)",
            http_error.status_code,
            http_error.detail,
        )
        return HeyGenAvatarVideoResponse(
            status="failed",
            job={},
            prompts=prompts,
            audio_asset_id=resolved_audio_asset_id,
            audio_reference=resolved_audio_alias,
            request_payload=payload,
            errors=[str(http_error.detail)],
        )

    logger.info(
        "POST /heygen/avatar-iv/generate completed (job_id=%s audio_asset_id=%s)",
        (job.get("data") or {}).get("video_id"),
        resolved_audio_asset_id,
    )
    return HeyGenAvatarVideoResponse(
        status="success",
        job=job,
        prompts=prompts,
        audio_asset_id=resolved_audio_asset_id,
        audio_reference=resolved_audio_alias,
        request_payload=payload,
        errors=[],
    )
