from __future__ import annotations

import asyncio
import json
import logging
import textwrap
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

import requests
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from config.config import settings
from models.freepik_model import (
    FreepikAgentPromptOutput,
    FreepikImageToVideoGenerationRequest,
    FreepikImageToVideoResponse,
    FreepikPromptBundle,
)
from utils.agents import freepik_agent

FREEPIK_IMAGE_TO_VIDEO_URL = "https://api.freepik.com/v1/ai/image-to-video/kling-v2-1-std"
FREEPIK_STATUS_URL = "https://api.freepik.com/v1/ai/image-to-video/kling-v2-1"
REQUEST_TIMEOUT_SECONDS = 120
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_POLL_TIMEOUT_SECONDS = 300.0

logger = logging.getLogger(__name__)


def fallback_prompt_bundle(
    request: FreepikImageToVideoGenerationRequest,
) -> FreepikPromptBundle:
    """Derive a conservative prompt bundle when the agent output is unusable."""

    collapsed = " ".join(request.script.split())
    shortened = textwrap.shorten(collapsed, width=600, placeholder="...")
    base_prompt = (
        f"{shortened}\n"
        "Cinematic lighting, smooth camera motion, natural facial animation, high fidelity details."
    )
    negative_prompt = (
        "blurry, noisy, distorted faces, watermark, text overlays, logo, glitches, "
        "double exposure, artifacts"
    )
    cfg_scale = request.cfg_scale if request.cfg_scale is not None else 0.5

    return FreepikPromptBundle(
        prompt=base_prompt,
        negative_prompt=negative_prompt,
        cfg_scale=cfg_scale,
        duration=request.duration,
    )


async def generate_prompt_bundle(
    request: FreepikImageToVideoGenerationRequest,
) -> FreepikPromptBundle:
    """Use the Freepik agent to craft prompts with a resilient fallback."""

    try:
        agent_response = await freepik_agent.run(
            json.dumps(
                {
                    "script": request.script,
                    "duration": request.duration,
                    "cfg_scale": request.cfg_scale,
                }
            )
        )
    except Exception as exc:  # pragma: no cover - network/LLM failures
        logger.warning("Freepik agent invocation failed: %s", exc)
        return fallback_prompt_bundle(request)

    try:
        payload = json.loads(agent_response.output)
        agent_output = FreepikAgentPromptOutput.model_validate(payload)
        return agent_output.to_bundle(
            fallback_cfg_scale=request.cfg_scale if request.cfg_scale is not None else 0.5,
            fallback_duration=request.duration,
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Invalid Freepik agent output: %s", exc)
        return fallback_prompt_bundle(request)


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
        except ValueError as exc:
            raise HTTPException(status_code=response.status_code, detail=response.text) from exc
        raise HTTPException(status_code=response.status_code, detail=error_payload)

    try:
        response_json = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Freepik API returned invalid JSON.") from exc

    try:
        return FreepikImageToVideoResponse.model_validate(response_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502, detail=f"Unexpected Freepik response format: {exc}"
        ) from exc


def _fetch_task_status(task_id: UUID) -> FreepikImageToVideoResponse:
    try:
        response = requests.get(
            f"{FREEPIK_STATUS_URL}/{task_id}",
            headers=_build_headers(include_content_type=False),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:  # pragma: no cover - network failures
        raise HTTPException(
            status_code=502, detail=f"Freepik status request failed: {exc}"
        ) from exc

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
                detail=(
                    "Timed out waiting for Kling task "
                    f"{task_id} to finish (last status: {latest.data.status})."
                ),
            )

        await asyncio.sleep(max(poll_interval, 0.5))
        latest = _fetch_task_status(task_id)


def _stream_generated_asset(task_id: UUID, asset_url: str) -> StreamingResponse:
    try:
        upstream = requests.get(asset_url, stream=True, timeout=REQUEST_TIMEOUT_SECONDS)
        upstream.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network failures
        raise HTTPException(
            status_code=502, detail=f"Failed to download generated video: {exc}"
        ) from exc

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
