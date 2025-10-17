"""HeyGen FastAPI routes for asset upload and video generation."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from config.config import settings
from controllers.generate_video import upload_audio_assets
from models.heygen import (
	HeyGenStructuredOutput,
	HeyGenVideoRequest,
	HeyGenVideoResponse,
	HeyGenVideoResult,
)
from utils.agents import heygen_agent

router = APIRouter()

HEYGEN_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
HEYGEN_STATUS_URL = "https://api.heygen.com/v1/video_status.get"
DEFAULT_TALKING_PHOTO_ID = (settings.HEYGEN_DEFAULT_TALKING_PHOTO_ID or "Monica_inSleeveless_20220819").strip()
STATUS_POLL_INTERVAL_SECONDS = 5
STATUS_MAX_ATTEMPTS = 24


def _build_asset_lookup(assets: list[dict[str, Any]]) -> dict[str, str]:
	"""Create a flexible lookup of scene identifiers to HeyGen asset ids."""

	asset_lookup: dict[str, str] = {}

	for asset in assets:
		file_name = asset.get("file_name", "")
		asset_id = asset.get("asset_id")
		if not file_name or not asset_id:
			continue

		path = Path(file_name)
		stem = path.stem.lower()
		base_stem = stem.split("__", 1)[0]

		candidates = {
			stem,
			stem.replace("-", "_"),
			stem.replace("_", "-"),
			base_stem,
			base_stem.replace("-", "_"),
			base_stem.replace("_", "-"),
		}

		scene_match = re.match(r"scene[\s_\-]?([0-9]+)", stem)
		if scene_match:
			number = scene_match.group(1)
			candidates.update(
				{
					f"scene_{number}",
					f"scene-{number}",
					f"scene {number}",
				}
			)

		for key in candidates:
			if key:
				asset_lookup[key] = asset_id

		scene_id = asset.get("scene_id")
		if isinstance(scene_id, str) and scene_id.strip():
			scene_slug = scene_id.strip().lower()
			asset_lookup[scene_slug] = asset_id
			asset_lookup[scene_slug.replace("-", "_")] = asset_id
			asset_lookup[scene_slug.replace("_", "-")] = asset_id

	return asset_lookup


def _prepare_agent_input(script: str, assets: list[dict[str, Any]]) -> str:
	"""Render the agent-friendly prompt that pairs scripts with asset metadata."""

	asset_map: dict[str, str] = {}
	for asset in assets:
		asset_id = asset.get("asset_id")
		if not asset_id:
			continue

		file_name = asset.get("file_name")
		if isinstance(file_name, str) and file_name:
			asset_map[file_name] = asset_id
			stem = Path(file_name).stem
			asset_map.setdefault(stem, asset_id)
			if "__" in stem:
				base_stem = stem.split("__", 1)[0]
				asset_map.setdefault(base_stem, asset_id)
				asset_map.setdefault(base_stem.replace("-", "_"), asset_id)
				asset_map.setdefault(base_stem.replace("_", "-"), asset_id)

		scene_id = asset.get("scene_id")
		if isinstance(scene_id, str) and scene_id:
			slug = scene_id.strip()
			if slug:
				asset_map.setdefault(slug, asset_id)
				asset_map.setdefault(slug.replace("-", "_"), asset_id)
				asset_map.setdefault(slug.replace("_", "-"), asset_id)

	pretty_assets = json.dumps(asset_map, indent=2, ensure_ascii=False)

	return (
		"SCRIPT:\n"
		f"{script.strip()}\n\n"
		"AUDIO_ASSET_MAP:\n"
		f"{pretty_assets}\n"
	)


def _submit_video_job(job_payload: dict[str, Any]) -> dict[str, Any]:
	"""Submit a HeyGen video job and normalise the success envelope."""

	headers = {
		"X-Api-Key": settings.HEYGEN_API_KEY,
		"Content-Type": "application/json",
	}

	response = requests.post(
		HEYGEN_GENERATE_URL,
		json=job_payload,
		headers=headers,
		timeout=120,
	)

	if response.status_code != 200:
		raise HTTPException(status_code=response.status_code, detail=response.text)

	data = response.json()
	if data.get("code") == 100:
		return data

	video_id = (data.get("data") or {}).get("video_id")
	if data.get("error") in (None, "", {}) and video_id:
		data.setdefault("code", 100)
		data.setdefault("message", "Success")
		return data

	raise HTTPException(status_code=500, detail=data.get("message") or data.get("error") or data)


def _resolve_asset_id(scene_id: str, explicit_id: str | None, asset_lookup: dict[str, str]) -> str | None:
	"""Pick the best asset id for a given scene using explicit overrides when present."""

	if explicit_id:
		return explicit_id

	slug = scene_id.lower().strip()
	candidates = {
		slug,
		slug.replace("-", "_"),
		slug.replace("_", "-"),
	}

	match = re.match(r"scene[\s_\-]?([0-9]+)", slug)
	if match:
		number = match.group(1)
		candidates.update(
			{
				f"scene_{number}",
				f"scene-{number}",
				f"scene {number}",
			}
		)

	for candidate in candidates:
		if candidate in asset_lookup:
			return asset_lookup[candidate]

	return None


def _normalize_talking_photo_id(candidate: str | None) -> str:
	"""Return a trimmed talking photo id, defaulting to configured fallback."""

	if candidate:
		sanitized = candidate.strip()
		if sanitized:
			return sanitized
	return DEFAULT_TALKING_PHOTO_ID


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
	asset_lookup = _build_asset_lookup(assets)

	agent_input = _prepare_agent_input(request.script, assets)

	try:
		agent_response = await heygen_agent.run(agent_input)
		scene_plan = HeyGenStructuredOutput.model_validate_json(agent_response.output)
	except ValidationError as exc:
		raise HTTPException(status_code=422, detail=f"Invalid HeyGen agent output: {exc}") from exc
	except json.JSONDecodeError as exc:
		raise HTTPException(status_code=422, detail="HeyGen agent returned invalid JSON.") from exc
	except Exception as exc:  # pragma: no cover - defensive
		raise HTTPException(status_code=500, detail=f"HeyGen agent failed: {exc}") from exc

	scene_results: list[HeyGenVideoResult] = []
	missing_assets: list[str] = []
	errors: list[str] = []

	for scene in scene_plan.scenes:
		scene.audio_asset_id = _resolve_asset_id(scene.scene_id, scene.audio_asset_id, asset_lookup)
		scene.talking_photo_id = _normalize_talking_photo_id(scene.talking_photo_id)

		if not scene.audio_asset_id:
			missing_assets.append(scene.scene_id)
			continue

		video_payload = {
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
				}
			]
		}

		try:
			submission_response = _submit_video_job(video_payload)
		except HTTPException as exc:
			errors.append(f"{scene.scene_id}: {exc.detail}")
			scene_results.append(
				HeyGenVideoResult(
					scene_id=scene.scene_id,
					status="failed",
					video_id=None,
					video_url=None,
					thumbnail_url=None,
					message=str(exc.detail),
					request_payload=video_payload,
					status_detail=None,
				)
			)
			continue

		video_id = submission_response.get("data", {}).get("video_id")
		result_status = "submitted"
		message = submission_response.get("message", "Success")
		video_url: str | None = None
		thumbnail_url: str | None = None
		status_response: dict[str, Any] | None = None

		if video_id:
			try:
				status_response = _fetch_video_status(video_id)
			except HTTPException as status_exc:
				errors.append(f"{scene.scene_id}: {status_exc.detail}")
				message = f"Video status lookup failed: {status_exc.detail}"
			else:
				data_section = status_response.get("data") or {}
				status_value = (data_section.get("status") or "").lower()
				if status_value == "completed":
					result_status = "completed"
					video_url = data_section.get("video_url")
					thumbnail_url = data_section.get("thumbnail_url")
					message = data_section.get("message") or "Video rendering completed."
				elif status_value == "failed":
					result_status = "failed"
					fail_message = data_section.get("error") or status_response.get("message") or "Video rendering failed."
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

		scene_results.append(
			HeyGenVideoResult(
				scene_id=scene.scene_id,
				status=result_status,
				video_id=video_id,
				video_url=video_url,
				thumbnail_url=thumbnail_url,
				message=message,
				request_payload=video_payload,
				status_detail=status_response,
			)
		)

	status: str
	if scene_results and not missing_assets and not errors:
		status = "success"
	elif scene_results:
		status = "partial"
	else:
		status = "failed"

	return HeyGenVideoResponse(
		status=status,
		results=scene_results,
		missing_assets=missing_assets,
		errors=errors,
	)


def _fetch_video_status(video_id: str, *, max_attempts: int = STATUS_MAX_ATTEMPTS, interval_seconds: int = STATUS_POLL_INTERVAL_SECONDS) -> dict[str, Any]:
	"""Poll HeyGen for the latest video status and return the response payload."""

	if not settings.HEYGEN_API_KEY:
		raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

	headers = {
		"X-Api-Key": settings.HEYGEN_API_KEY,
		"accept": "application/json",
	}
	params = {"video_id": video_id}
	last_payload: dict[str, Any] | None = None

	for attempt in range(max_attempts):
		response = requests.get(
			HEYGEN_STATUS_URL,
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


