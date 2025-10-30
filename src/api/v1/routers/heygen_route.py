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
async def upload_audio_assets_endpoint(force: bool = False) -> dict[str, Any]:
    """Expose audio upload helper via API."""

    return await upload_audio_assets(force=force)


@router.post("/generate-video", response_model=HeyGenVideoResponse)
async def generate_video(request: HeyGenVideoRequest) -> HeyGenVideoResponse:
    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    return await heygen_controller.generate_video_batch(
        request.script,
        force_upload=request.force_upload,
    )


@router.post("/avatar-iv/generate", response_model=HeyGenAvatarVideoResponse)
async def generate_avatar_iv_video(
    request: HeyGenAvatarVideoRequest,
) -> HeyGenAvatarVideoResponse:
    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    assets_result = await upload_audio_assets(force=request.force_upload_audio)
    assets = assets_result.get("assets", [])
    if not assets:
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
    except (ValidationError, json.JSONDecodeError) as exc:
        logger.warning("HeyGen avatar agent output invalid: %s", exc)
        prompts = heygen_controller.fallback_avatar_prompts(request)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("HeyGen avatar agent failed: %s", exc)
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

    # Some workflows still expect script + voice, include for completeness.
    payload["script"] = prompts.script
    payload["voice_id"] = prompts.voice_id

    try:
        job = heygen_controller._submit_avatar_iv_job(payload)
    except HTTPException as exc:
        return HeyGenAvatarVideoResponse(
            status="failed",
            job={},
            prompts=prompts,
            audio_asset_id=resolved_audio_asset_id,
            audio_reference=resolved_audio_alias,
            request_payload=payload,
            errors=[str(exc.detail)],
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
