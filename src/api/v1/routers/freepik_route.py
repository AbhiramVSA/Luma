from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from config.config import settings
from controllers.freepik import (
    DEFAULT_POLL_INTERVAL_SECONDS, 
    DEFAULT_POLL_TIMEOUT_SECONDS, 
    FREEPIK_IMAGE_TO_VIDEO_URL, 
    REQUEST_TIMEOUT_SECONDS,
    _build_headers, 
    _fetch_task_status, 
    _parse_freepik_response, 
    _poll_task_status, 
    _stream_generated_asset)

from models.freepik_model import (
	FreepikImageToVideoRequest,
	FreepikImageToVideoResponse,
)

router = APIRouter()


@router.post("/image-to-video/kling-v2-1-std", response_model=FreepikImageToVideoResponse)
async def create_kling_video(
	request: FreepikImageToVideoRequest,
) -> FreepikImageToVideoResponse:
	payload = request.model_dump(exclude_none=True)

	try:
		response = requests.post(
			FREEPIK_IMAGE_TO_VIDEO_URL,
			json=payload,
			headers=_build_headers(),
			timeout=REQUEST_TIMEOUT_SECONDS,
		)
	except requests.RequestException as exc:  # pragma: no cover - network failures
		raise HTTPException(status_code=502, detail=f"Freepik API request failed: {exc}") from exc

	return _parse_freepik_response(response)


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
		raise HTTPException(status_code=409, detail="Task is not completed yet; cannot download video.")

	generated_assets = status_response.data.generated
	if not generated_assets:
		raise HTTPException(status_code=404, detail="No generated video URLs were returned for this task.")

	if asset_index < 0 or asset_index >= len(generated_assets):
		raise HTTPException(status_code=400, detail="asset_index is out of range for the generated results.")

	return _stream_generated_asset(task_id, str(generated_assets[asset_index]))
