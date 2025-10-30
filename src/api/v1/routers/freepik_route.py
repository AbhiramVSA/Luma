from __future__ import annotations

from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException

from controllers.freepik import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_POLL_TIMEOUT_SECONDS,
    FREEPIK_IMAGE_TO_VIDEO_URL,
    REQUEST_TIMEOUT_SECONDS,
    _build_headers,
    _fetch_task_status,
    _parse_freepik_response,
    _poll_task_status,
    _stream_generated_asset,
    generate_prompt_bundle,
)
from models.freepik_model import (
    FreepikImageToVideoGenerationRequest,
    FreepikImageToVideoRequest,
    FreepikImageToVideoResponse,
    FreepikPromptBundle,
    FreepikVideoTaskResponse,
)

router = APIRouter()


@router.post("/image-to-video/kling-v2-1-std", response_model=FreepikVideoTaskResponse)
async def create_kling_video(
    request: FreepikImageToVideoGenerationRequest,
) -> FreepikVideoTaskResponse:
    prompt_bundle = await generate_prompt_bundle(request)

    video_request = FreepikImageToVideoRequest(
        duration=prompt_bundle.duration,
        webhook_url=request.webhook_url,
        image=request.image,
        prompt=prompt_bundle.prompt,
        negative_prompt=prompt_bundle.negative_prompt,
        cfg_scale=request.cfg_scale if request.cfg_scale is not None else prompt_bundle.cfg_scale,
        static_mask=request.static_mask,
        dynamic_masks=request.dynamic_masks,
    )

    payload = video_request.model_dump(exclude_none=True)
    if not payload.get("prompt"):
        raise HTTPException(
            status_code=500,
            detail="Unable to derive a valid prompt for Kling request.",
        )

    try:
        response = requests.post(
            FREEPIK_IMAGE_TO_VIDEO_URL,
            json=payload,
            headers=_build_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:  # pragma: no cover - network failures
        raise HTTPException(status_code=502, detail=f"Freepik API request failed: {exc}") from exc

    parsed = _parse_freepik_response(response)

    applied_cfg_scale = payload.get("cfg_scale", prompt_bundle.cfg_scale)
    applied_duration = payload.get("duration", prompt_bundle.duration)

    return FreepikVideoTaskResponse(
        data=parsed.data,
        prompts=FreepikPromptBundle(
            prompt=str(payload.get("prompt", prompt_bundle.prompt)),
            negative_prompt=payload.get("negative_prompt"),
            cfg_scale=applied_cfg_scale,
            duration=applied_duration,
        ),
    )


@router.get("/image-to-video/kling-v2-1/{task_id}", response_model=FreepikImageToVideoResponse)
async def get_kling_video_status(
    task_id: UUID,
    wait_for_completion: bool = False,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    timeout: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    download: bool = False,
    asset_index: int = 0,
):
    if poll_interval <= 0:
        poll_interval = DEFAULT_POLL_INTERVAL_SECONDS
    if timeout <= 0:
        timeout = DEFAULT_POLL_TIMEOUT_SECONDS

    status_response = (
        await _poll_task_status(task_id, poll_interval, timeout)
        if wait_for_completion or download
        else _fetch_task_status(task_id)
    )

    if not download:
        return status_response

    if status_response.data.status.upper() != "COMPLETED":
        raise HTTPException(
            status_code=409, detail="Task is not completed yet; cannot download video."
        )

    generated_assets = status_response.data.generated
    if not generated_assets:
        raise HTTPException(
            status_code=404, detail="No generated video URLs were returned for this task."
        )

    if asset_index < 0 or asset_index >= len(generated_assets):
        raise HTTPException(
            status_code=400, detail="asset_index is out of range for the generated results."
        )

    return _stream_generated_asset(task_id, str(generated_assets[asset_index]))
