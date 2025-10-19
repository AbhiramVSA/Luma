"""HeyGen FastAPI routes for asset upload and video generation."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from config.config import settings
from controllers.generate_video import upload_audio_assets
import controllers.heygen as heygen_controller
from models.heygen import (
	HeyGenStructuredOutput,
	HeyGenVideoRequest,
	HeyGenVideoResponse,
	HeyGenVideoResult,
)
from utils.agents import heygen_agent

router = APIRouter()


@router.post("/upload-audio-assets", response_model=dict)
async def upload_audio_assets_endpoint(force: bool = False) -> dict[str, Any]:
	"""Expose audio upload helper via API."""

	return await upload_audio_assets(force=force)


@router.post("/generate-video", response_model=HeyGenVideoResponse)
async def generate_video(request: HeyGenVideoRequest) -> HeyGenVideoResponse:
	if not settings.HEYGEN_API_KEY:
		raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

	assets_result = await upload_audio_assets(force=request.force_upload)
	assets = assets_result.get("assets", [])
	asset_lookup = heygen_controller._build_asset_lookup(assets)

	agent_input = heygen_controller._prepare_agent_input(request.script, assets)

	try:
		agent_output_raw = await heygen_agent.run(agent_input)
		structured = HeyGenStructuredOutput.model_validate_json(agent_output_raw.output)
	except ValidationError as exc:
		raise HTTPException(status_code=422, detail=f"Invalid HeyGen agent output: {exc}") from exc
	except json.JSONDecodeError as exc:
		raise HTTPException(status_code=422, detail="HeyGen agent returned invalid JSON.") from exc
	except Exception as exc:  # pragma: no cover - defensive
		raise HTTPException(status_code=500, detail=f"HeyGen agent failed: {exc}") from exc

	results: list[HeyGenVideoResult] = []
	missing_assets: list[str] = []
	errors: list[str] = []

	for scene in structured.scenes:
		scene.audio_asset_id = heygen_controller._resolve_asset_id(
			scene.scene_id,
			scene.audio_asset_id,
			asset_lookup,
		)
		scene.talking_photo_id = heygen_controller._normalize_talking_photo_id(scene.talking_photo_id)

		if not scene.audio_asset_id:
			missing_assets.append(scene.scene_id)
			continue

		payload = {
			"dimension": {
				"width": 720,
				"height": 1280,
			},
			"video_inputs": [
				{
					"character": {
						"type": "talking_photo",
						"talking_photo_id": scene.talking_photo_id,
					},
					"voice": {
						"type": "audio",
						"audio_asset_id": scene.audio_asset_id,
					},
				},
			],
		}

		try:
			response_json = heygen_controller._submit_video_job(payload)
		except HTTPException as exc:
			errors.append(f"{scene.scene_id}: {exc.detail}")
			results.append(
				HeyGenVideoResult(
					scene_id=scene.scene_id,
					status="failed",
					video_id=None,
					video_url=None,
					thumbnail_url=None,
					message=str(exc.detail),
					request_payload=payload,
					status_detail=None,
				),
			)
			continue

		video_id = response_json.get("data", {}).get("video_id")
		result_status = "submitted"
		message = response_json.get("message", "Success")
		video_url: str | None = None
		thumbnail_url: str | None = None
		status_payload: dict[str, Any] | None = None

		if video_id:
			try:
				status_payload = _fetch_video_status(video_id)
			except HTTPException as status_exc:
				errors.append(f"{scene.scene_id}: {status_exc.detail}")
				message = f"Video status lookup failed: {status_exc.detail}"
			else:
				data_section = status_payload.get("data") or {}
				status_value = (data_section.get("status") or "").lower()
				if status_value == "completed":
					result_status = "completed"
					video_url = data_section.get("video_url")
					thumbnail_url = data_section.get("thumbnail_url")
					message = data_section.get("message") or "Video rendering completed."
				elif status_value == "failed":
					result_status = "failed"
					fail_message = data_section.get("error") or status_payload.get("message") or "Video rendering failed."
					message = str(fail_message)
					errors.append(f"{scene.scene_id}: {message}")
				elif status_value:
					result_status = "processing"
					message = f"Video status: {status_value}. The video will be ready shortly."
				else:
					message = "Video status lookup returned no status."
		else:
			message = "HeyGen did not return a video_id."
			errors.append(f"{scene.scene_id}: {message}")

		results.append(
			HeyGenVideoResult(
				scene_id=scene.scene_id,
				status=result_status,
				video_id=video_id,
				video_url=video_url,
				thumbnail_url=thumbnail_url,
				message=message,
				request_payload=payload,
				status_detail=status_payload,
			),
		)

	if results and not missing_assets and not errors:
		status = "success"
	elif results:
		status = "partial"
	else:
		status = "failed"

	return HeyGenVideoResponse(
		status=status,
		results=results,
		missing_assets=missing_assets,
		errors=errors,
	)


def _fetch_video_status(
    video_id: str,
    *,
    max_attempts: Optional[int] = None,
    interval_seconds: Optional[int] = None,
) -> dict[str, Any]:
	"""Poll HeyGen for the latest video status and return the response payload."""

	if not settings.HEYGEN_API_KEY:
		raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

	max_attempts = max_attempts or heygen_controller.STATUS_MAX_ATTEMPTS
	interval_seconds = interval_seconds or heygen_controller.STATUS_POLL_INTERVAL_SECONDS

	headers = {
		"X-Api-Key": settings.HEYGEN_API_KEY,
		"accept": "application/json",
	}
	params = {"video_id": video_id}
	last_payload: dict[str, Any] | None = None

	for attempt in range(max_attempts):
		response = requests.get(
			heygen_controller.HEYGEN_STATUS_URL,
			params=params,
			headers=headers,
			timeout=120,
		)

		if response.status_code == 404:
			raise HTTPException(status_code=404, detail=f"HeyGen video {video_id} was not found.")
		if response.status_code != 200:
			raise HTTPException(status_code=response.status_code, detail=response.text)

		payload = response.json()
		last_payload = payload
		status_value = ((payload.get("data") or {}).get("status") or "").lower()
		if status_value in {"completed", "failed"}:
			return payload

		if attempt < max_attempts - 1:
			time.sleep(interval_seconds)

	return last_payload or {}


