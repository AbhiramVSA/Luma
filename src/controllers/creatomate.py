"""Creatomate orchestration helpers and API integrations."""

from __future__ import annotations

import json
import logging
import secrets
import textwrap
import time
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError

import controllers.heygen as heygen_controller
from config.config import settings
from controllers.elevenlabs import synthesize_audio_assets
from controllers.generate_video import upload_audio_assets
from models.creatomate import (
    CreatomateAgentOutput,
    CreatomateRenderRequest,
    CreatomateRenderResponse,
    SceneVideoAsset,
)
from models.heygen import HeyGenVideoResult
from utils.agents import creatomate_agent

logger = logging.getLogger(__name__)

CREATOMATE_BASE_URL = "https://api.creatomate.com/v1"
CREATOMATE_TEMPLATES_URL = f"{CREATOMATE_BASE_URL}/templates"
CREATOMATE_RENDERS_URL = f"{CREATOMATE_BASE_URL}/renders"
RENDER_POLL_INTERVAL_SECONDS = 5
RENDER_POLL_TIMEOUT_SECONDS = 480
IMAGES_DIR = Path("generated_assets") / "images"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


def _require_creatomate_key() -> str:
    if not settings.CREATOMATE_API_KEY:
        raise HTTPException(status_code=400, detail="CREATOMATE_API_KEY is not configured.")
    return settings.CREATOMATE_API_KEY


def _build_headers(include_json: bool = True) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {_require_creatomate_key()}"}
    if include_json:
        headers["Content-Type"] = "application/json"
    return headers


def _request_json(response: requests.Response) -> dict[str, Any]:
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Creatomate authentication failed.")
    if response.status_code >= 400:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    try:
        return response.json()
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=502, detail="Creatomate returned invalid JSON") from exc


def _fetch_template_payload(template_id: str) -> dict[str, Any]:
    try:
        response = requests.get(
            f"{CREATOMATE_TEMPLATES_URL}/{template_id}",
            headers=_build_headers(include_json=False),
            timeout=60,
        )
    except requests.RequestException as exc:  # pragma: no cover - network issues
        raise HTTPException(
            status_code=502,
            detail=f"Creatomate template lookup failed: {exc}",
        ) from exc

    return _request_json(response)


def _extract_placeholder_keys(payload: dict[str, Any]) -> list[str]:
    placeholders: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = key.lower()
                if lowered in {"placeholder", "placeholders", "key", "property"}:
                    if isinstance(value, str) and value.strip():
                        placeholders.add(value.strip())
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str) and item.strip():
                                placeholders.add(item.strip())
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(payload)

    ordered = sorted(placeholders)
    return ordered


def _submit_render_job(template_id: str, modifications: dict[str, str]) -> dict[str, Any]:
    payload = {
        "template_id": template_id,
        "modifications": modifications,
    }

    try:
        response = requests.post(
            CREATOMATE_RENDERS_URL,
            headers=_build_headers(include_json=True),
            json=payload,
            timeout=120,
        )
    except requests.RequestException as exc:  # pragma: no cover - network issues
        raise HTTPException(
            status_code=502,
            detail=f"Creatomate render request failed: {exc}",
        ) from exc

    result = _request_json(response)
    return result


def _poll_render_status(render_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + RENDER_POLL_TIMEOUT_SECONDS

    while True:
        try:
            response = requests.get(
                f"{CREATOMATE_RENDERS_URL}/{render_id}",
                headers=_build_headers(include_json=False),
                timeout=60,
            )
        except requests.RequestException as exc:  # pragma: no cover - network issues
            raise HTTPException(
                status_code=502,
                detail=f"Creatomate status poll failed: {exc}",
            ) from exc

        payload = _request_json(response)
        status = (payload.get("status") or "").lower()
        if status in {"success", "failed"}:
            return payload

        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=504,
                detail="Timed out waiting for Creatomate render to finish.",
            )

        time.sleep(RENDER_POLL_INTERVAL_SECONDS)


def _shorten_dialogue(lines: list[str], width: int = 200) -> str:
    joined = " ".join(segment.strip() for segment in lines if segment.strip())
    return textwrap.shorten(joined, width=width, placeholder="...") if joined else ""


def _prepare_agent_brief(
    template_hint: str,
    placeholders: list[str],
    scene_video_assets: list[SceneVideoAsset],
    scene_context: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = ["TEMPLATE_ID:", template_hint or "", "", "PLACEHOLDERS:"]

    if placeholders:
        lines.extend(f"- {key}" for key in placeholders)
    else:
        lines.append("- (none)")

    lines.extend(["", "SCENE_SUMMARY:"])

    for asset in sorted(scene_video_assets, key=lambda item: item.order):
        context = scene_context.get(asset.scene_id, {})
        lines.append(f"- scene_id: {asset.scene_id}")
        lines.append(f"  order: {asset.order}")
        lines.append(f"  video_url: {asset.video_url}")
        image_url = context.get("image_url")
        if image_url:
            lines.append(f"  image_url: {image_url}")
        excerpt = context.get("script_excerpt") or ""
        if excerpt:
            lines.append(f"  script_excerpt: {excerpt}")
        notes = context.get("notes")
        if notes:
            lines.append(f"  notes: {notes}")

    brief = "\n".join(lines) + "\n"
    return brief


async def save_scene_image(scene_id: str, file: UploadFile) -> dict[str, str]:
    """Validate and persist an uploaded scene image for Creatomate renders."""

    slug = scene_id.strip()
    if not slug:
        raise HTTPException(status_code=400, detail="scene_id is required")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported image format. Use JPG, JPEG, PNG, or WEBP.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 10 MB limit.")

    safe_slug = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "-" for ch in slug.lower())
    token = secrets.token_hex(8)
    filename = f"{safe_slug}_{token}{suffix}"

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    destination = IMAGES_DIR / filename
    destination.write_bytes(content)

    return {
        "url": f"/generated_assets/images/{filename}",
        "file_name": filename,
    }


async def orchestrate_creatomate_render(
    request: CreatomateRenderRequest,
) -> CreatomateRenderResponse:
    _require_creatomate_key()

    script_config, audio_payload = await synthesize_audio_assets(request.script)
    if isinstance(audio_payload, dict):
        raw_audio_outputs = audio_payload.get("outputs", [])
        if isinstance(raw_audio_outputs, list):
            audio_outputs = [item for item in raw_audio_outputs if isinstance(item, dict)]
        else:
            audio_outputs = []
    else:
        audio_outputs = []

    assets_payload = await upload_audio_assets(force=request.force_upload_audio)
    if isinstance(assets_payload, dict):
        asset_candidates = assets_payload.get("assets", [])
        if isinstance(asset_candidates, list):
            asset_list = [item for item in asset_candidates if isinstance(item, dict)]
        else:
            asset_list = []
    else:
        asset_list = []

    heygen_response = await heygen_controller.generate_video_batch(
        request.script,
        force_upload=False,
        assets=asset_list,
    )

    completed_results: list[HeyGenVideoResult] = [
        result
        for result in heygen_response.results
        if isinstance(result.video_url, str) and result.video_url.strip()
    ]

    if not completed_results:
        raise HTTPException(
            status_code=502,
            detail="No completed HeyGen videos available for Creatomate render.",
        )

    scene_order_map: dict[str, int] = {
        scene.scene_id: index + 1 for index, scene in enumerate(script_config.scenes)
    }

    scene_context: dict[str, dict[str, Any]] = {}
    for scene in script_config.scenes:
        excerpt = _shorten_dialogue([line.text for line in scene.dialogues])
        scene_context[scene.scene_id] = {
            "script_excerpt": excerpt,
        }

    for scene_meta in request.scenes:
        slug = scene_meta.scene_id
        if slug not in scene_context:
            scene_context[slug] = {}
        if scene_meta.image_url:
            scene_context[slug]["image_url"] = scene_meta.image_url
        if scene_meta.notes:
            scene_context[slug]["notes"] = scene_meta.notes

    scene_video_assets: list[SceneVideoAsset] = []
    for result in completed_results:
        order = scene_order_map.get(result.scene_id) or (len(scene_video_assets) + 1)
        scene_video_assets.append(
            SceneVideoAsset(
                scene_id=result.scene_id,
                order=order,
                video_url=result.video_url or "",
            )
        )

    template_hint = request.template_id or settings.CREATOMATE_DEFAULT_TEMPLATE_ID or ""

    placeholders: list[str] = []
    if template_hint:
        try:
            template_payload = _fetch_template_payload(template_hint)
            placeholders = _extract_placeholder_keys(template_payload)
        except HTTPException as exc:
            logger.warning("Failed to fetch Creatomate template metadata: %s", exc.detail)

    if not placeholders:
        placeholders = [
            f"Video-{asset.order}.source"
            for asset in sorted(scene_video_assets, key=lambda item: item.order)
        ]

    agent_brief = _prepare_agent_brief(
        template_hint,
        placeholders,
        scene_video_assets,
        scene_context,
    )

    try:
        agent_response = await creatomate_agent.run(agent_brief)
        agent_output = CreatomateAgentOutput.model_validate_json(agent_response.output)
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Creatomate agent output invalid: {exc}",
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Creatomate agent failed: {exc}") from exc

    render_template_id = agent_output.template_id or template_hint
    if not render_template_id:
        raise HTTPException(
            status_code=400,
            detail="Creatomate agent did not specify a template_id.",
        )

    render_payload = _submit_render_job(render_template_id, agent_output.modifications)
    if request.wait_for_render and isinstance(render_payload.get("id"), str):
        render_payload = _poll_render_status(render_payload["id"])

    placeholder_lookup = {
        value: key for key, value in agent_output.modifications.items() if isinstance(value, str)
    }

    for asset in scene_video_assets:
        asset.placeholder = placeholder_lookup.get(asset.video_url)

    render_status = (render_payload.get("status") or "").lower()
    overall_status = "success" if render_status == "success" else "failed"

    error_messages: list[str] = []
    if getattr(heygen_response, "errors", None):
        error_messages.extend(str(err) for err in heygen_response.errors if err)
    if getattr(heygen_response, "missing_assets", None):
        missing = ", ".join(heygen_response.missing_assets)
        if missing:
            error_messages.append(f"Missing HeyGen audio assets for scenes: {missing}")
    if overall_status != "success":
        error_messages.append("Creatomate render did not complete successfully.")

    return CreatomateRenderResponse(
        status=overall_status,
        template_id=render_template_id,
        modifications=agent_output.modifications,
        creatomate_job=render_payload,
        audio_outputs=audio_outputs,
        scene_videos=scene_video_assets,
        heygen_results=heygen_response.results,
        errors=error_messages,
    )
