from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from uuid import UUID

import requests
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from config.config import settings
from models.freepik_model import (
	FreepikImageToVideoResponse,
)


FREEPIK_IMAGE_TO_VIDEO_URL = "https://api.freepik.com/v1/ai/image-to-video/kling-v2-1-std"
FREEPIK_STATUS_URL = "https://api.freepik.com/v1/ai/image-to-video/kling-v2-1"
REQUEST_TIMEOUT_SECONDS = 120
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_POLL_TIMEOUT_SECONDS = 300.0


def _require_api_key() -> str:
	if not settings.FREEPIK_API_KEY:
		raise HTTPException(status_code=400, detail="FREEPIK_API_KEY is not configured.")
	return settings.FREEPIK_API_KEY


def _build_headers(include_content_type: bool = True) -> dict[str, str]:
	headers = {"x-freepik-api-key": _require_api_key()}
	if include_content_type:
		headers["Content-Type"] = "application/json"
	return headers


def _parse_freepik_response(response: requests.Response) -> FreepikImageToVideoResponse:
	if response.status_code >= 400:
		try:
			error_payload = response.json()
		except ValueError:
			raise HTTPException(status_code=response.status_code, detail=response.text)
		raise HTTPException(status_code=response.status_code, detail=error_payload)

	try:
		response_json = response.json()
	except ValueError as exc:
		raise HTTPException(status_code=502, detail="Freepik API returned invalid JSON.") from exc

	try:
		return FreepikImageToVideoResponse.model_validate(response_json)
	except ValidationError as exc:
		raise HTTPException(status_code=502, detail=f"Unexpected Freepik response format: {exc}") from exc


def _fetch_task_status(task_id: UUID) -> FreepikImageToVideoResponse:
	try:
		response = requests.get(
			f"{FREEPIK_STATUS_URL}/{task_id}",
			headers=_build_headers(include_content_type=False),
			timeout=REQUEST_TIMEOUT_SECONDS,
		)
	except requests.RequestException as exc:  # pragma: no cover - network failures
		raise HTTPException(status_code=502, detail=f"Freepik status request failed: {exc}") from exc

	return _parse_freepik_response(response)


async def _poll_task_status(
	task_id: UUID,
	poll_interval: float,
	timeout: float,
) -> FreepikImageToVideoResponse:
	latest = _fetch_task_status(task_id)
	deadline = time.monotonic() + timeout

	while True:
		status = latest.data.status.upper()
		if status in {"COMPLETED", "FAILED"}:
			return latest

		if time.monotonic() >= deadline:
			raise HTTPException(
				status_code=504,
				detail=f"Timed out waiting for Kling task {task_id} to finish (last status: {latest.data.status}).",
			)

		await asyncio.sleep(max(poll_interval, 0.5))
		latest = _fetch_task_status(task_id)


def _stream_generated_asset(task_id: UUID, asset_url: str) -> StreamingResponse:
	try:
		upstream = requests.get(asset_url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS)
		upstream.raise_for_status()
	except requests.RequestException as exc:  # pragma: no cover - network failures
		raise HTTPException(status_code=502, detail=f"Failed to download generated video: {exc}") from exc

	filename = Path(urlparse(asset_url).path).name or f"{task_id}.mp4"
	media_type = upstream.headers.get("Content-Type", "video/mp4")

	def iter_stream() -> Iterator[bytes]:
		try:
			for chunk in upstream.iter_content(chunk_size=8192):
				if chunk:
					yield chunk
		finally:
			upstream.close()

	return StreamingResponse(
		iter_stream(),
		media_type=media_type,
		headers={
			"Content-Disposition": f'attachment; filename="{filename}"',
		},
	)