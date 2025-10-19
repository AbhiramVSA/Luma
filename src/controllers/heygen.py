"""HeyGen FastAPI routes for asset upload and video generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException

from config.config import settings
from controllers.generate_video import upload_audio_assets
from utils.agents import heygen_agent

router = APIRouter()

HEYGEN_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
HEYGEN_STATUS_URL = "https://api.heygen.com/v1/video_status.get"
DEFAULT_TALKING_PHOTO_ID = (settings.HEYGEN_DEFAULT_TALKING_PHOTO_ID or "70febb5b01d6411682bceebd3bc7f5cb").strip()
STATUS_POLL_INTERVAL_SECONDS = 5
STATUS_MAX_ATTEMPTS = 24


def _build_asset_lookup(assets: list[dict[str, Any]]) -> dict[str, str]:
	lookup: dict[str, str] = {}

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
				lookup[key] = asset_id

		scene_id = asset.get("scene_id")
		if isinstance(scene_id, str) and scene_id.strip():
			scene_slug = scene_id.strip().lower()
			lookup[scene_slug] = asset_id
			lookup[scene_slug.replace("-", "_")] = asset_id
			lookup[scene_slug.replace("_", "-")] = asset_id

	return lookup


def _prepare_agent_input(script: str, assets: list[dict[str, Any]]) -> str:
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


def _submit_video_job(payload: dict[str, Any]) -> dict[str, Any]:
	headers = {
		"X-Api-Key": settings.HEYGEN_API_KEY,
		"Content-Type": "application/json",
	}

	response = requests.post(
		HEYGEN_GENERATE_URL,
		json=payload,
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

	return data


def _resolve_asset_id(scene_id: str, explicit_id: str | None, asset_lookup: dict[str, str]) -> str | None:
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
	if candidate:
		sanitized = candidate.strip()
		if sanitized:
			return sanitized
	return DEFAULT_TALKING_PHOTO_ID


@router.post("/upload-audio-assets", response_model=dict)
async def upload_audio_assets_endpoint(force: bool = False) -> dict[str, Any]:
	"""Expose audio upload helper via API."""

	return await upload_audio_assets(force=force)