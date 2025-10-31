"""HeyGen controller helpers for asset upload and video generation."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException
from pydantic import ValidationError

from config.config import settings
from controllers.generate_video import upload_audio_assets
from models.heygen import (
    HeyGenAvatarAgentOutput,
    HeyGenAvatarVideoRequest,
    HeyGenStructuredOutput,
    HeyGenVideoResponse,
    HeyGenVideoResult,
)
from utils.agents import heygen_agent

HEYGEN_GENERATE_URL = "https://api.heygen.com/v2/video/generate"
HEYGEN_STATUS_URL = "https://api.heygen.com/v1/video_status.get"
HEYGEN_AVATAR_IV_URL = "https://api.heygen.com/v2/video/av4/generate"
DEFAULT_TALKING_PHOTO_ID = (
    settings.HEYGEN_DEFAULT_TALKING_PHOTO_ID or "70febb5b01d6411682bceebd3bc7f5cb"
).strip()
STATUS_POLL_INTERVAL_SECONDS = 5
STATUS_MAX_ATTEMPTS = 24


def build_avatar_agent_envelope(
    request: HeyGenAvatarVideoRequest,
    *,
    audio_asset_id: str | None,
    audio_alias: str | None,
) -> str:
    voice_notes: list[str] = []
    if request.voice_preferences:
        voice_notes.append(request.voice_preferences.strip())
    if request.orientation_hint:
        voice_notes.append(f"Preferred orientation: {request.orientation_hint}")
    if request.fit_hint:
        voice_notes.append(f"Suggested frame fit: {request.fit_hint}")
    if request.enhance_motion_override is not None:
        voice_notes.append(
            f"Enhance motion override: {str(request.enhance_motion_override).lower()}"
        )

    voice_section = "\n".join(voice_notes) if voice_notes else "(none provided)"
    references_section = request.script.strip() or "(none provided)"
    audio_section_lines: list[str] = []
    if audio_alias:
        audio_section_lines.append(f"Matched key: {audio_alias}")
    if audio_asset_id:
        audio_section_lines.append(f"Resolved asset id: {audio_asset_id}")
    audio_section = "\n".join(audio_section_lines) if audio_section_lines else "(none)"

    brief = textwrap.dedent(request.video_brief or request.script).strip()

    return (
        "VIDEO_BRIEF:\n"
        f"{brief}\n\n"
        "SCRIPT_REFERENCES:\n"
        f"{references_section}\n\n"
        "VOICE_PREFERENCES:\n"
        f"{voice_section}\n\n"
        "AUDIO_CONTEXT:\n"
        f"{audio_section}\n"
    )


def fallback_avatar_prompts(
    request: HeyGenAvatarVideoRequest,
) -> HeyGenAvatarAgentOutput:
    script_source = request.video_brief or request.script
    collapsed = " ".join(script_source.split())
    snippet = textwrap.shorten(collapsed, width=420, placeholder="...")
    if len(snippet) < 20:
        snippet = (snippet + " ...").strip()
        if len(snippet) < 20:
            snippet = snippet.ljust(20, ".")
    voice_id = "ryan_smith"
    if request.voice_preferences and request.voice_preferences.strip():
        tokens = request.voice_preferences.strip().split()
        for token in tokens:
            if any(ch.isdigit() for ch in token) or "_" in token:
                voice_id = token
                break
        else:
            voice_id = tokens[0]

    if request.video_brief:
        video_title_source = request.video_brief.strip()
    else:
        video_title_source = request.script.strip()

    return HeyGenAvatarAgentOutput(
        video_title=textwrap.shorten(video_title_source, width=70, placeholder="..."),
        script=snippet,
        voice_id=voice_id,
        video_orientation=request.orientation_hint or "portrait",
        fit=request.fit_hint or "cover",
        custom_motion_prompt=(
            "Warm eye contact, natural head nods, relaxed shoulder posture, gentle hand gestures "
            "to emphasise key lines, soft smile at the close."
        ),
        enhance_custom_motion_prompt=(
            request.enhance_motion_override if request.enhance_motion_override is not None else True
        ),
    )


def resolve_avatar_audio_asset(
    script: str,
    assets: list[dict[str, Any]],
    asset_lookup: dict[str, str],
) -> tuple[str | None, str | None]:
    script_lower = script.lower()
    normalized_lookup = {key.lower(): value for key, value in asset_lookup.items()}

    for key, asset_id in normalized_lookup.items():
        if key and key in script_lower:
            return asset_id, key

    for number in re.findall(r"scene[\s_-]?(\d+)", script_lower):
        for variant in (f"scene_{number}", f"scene-{number}", f"scene {number}", f"scene{number}"):
            asset_id = normalized_lookup.get(variant)
            if asset_id:
                return asset_id, variant

    for asset in assets:
        asset_id = asset.get("asset_id")
        if not asset_id:
            continue
        scene_id = asset.get("scene_id")
        if isinstance(scene_id, str) and scene_id.strip():
            lowered = scene_id.strip().lower()
            if lowered in normalized_lookup:
                return normalized_lookup[lowered], scene_id
            if lowered in script_lower:
                return asset_id, scene_id
        file_name = asset.get("file_name")
        if isinstance(file_name, str):
            stem = file_name.rsplit(".", 1)[0].lower()
            if stem in normalized_lookup:
                return normalized_lookup[stem], stem
            if stem in script_lower:
                return asset_id, stem

    if assets:
        first = assets[0]
        return first.get("asset_id"), first.get("scene_id")

    return None, None


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

    return f"SCRIPT:\n{script.strip()}\n\nAUDIO_ASSET_MAP:\n{pretty_assets}\n"


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


def _submit_avatar_iv_job(payload: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "X-Api-Key": settings.HEYGEN_API_KEY,
        "Content-Type": "application/json",
        "accept": "application/json",
    }

    response = requests.post(
        HEYGEN_AVATAR_IV_URL,
        json=payload,
        headers=headers,
        timeout=120,
    )

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    try:
        data = response.json()
    except ValueError as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=502,
            detail="HeyGen Avatar IV returned invalid JSON",
        ) from exc

    error_message = data.get("message") or data.get("msg")
    code = data.get("code")
    if code not in (0, 100, None) and (data.get("error") or error_message):
        raise HTTPException(status_code=502, detail=error_message or data.get("error"))

    return data


def _resolve_asset_id(
    scene_id: str, explicit_id: str | None, asset_lookup: dict[str, str]
) -> str | None:
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


def _fetch_video_status(
    video_id: str,
    *,
    max_attempts: int | None = None,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    """Poll HeyGen for the latest video status and return the JSON payload."""

    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    max_attempts = max_attempts or STATUS_MAX_ATTEMPTS
    interval_seconds = interval_seconds or STATUS_POLL_INTERVAL_SECONDS

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
            import time

            time.sleep(interval_seconds)

    return last_payload or {}


async def generate_video_batch(
    script: str,
    *,
    force_upload: bool = False,
    assets: list[dict[str, Any]] | None = None,
) -> HeyGenVideoResponse:
    """Generate HeyGen videos for each scene in the script via the automation agent."""

    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    if assets is None:
        asset_payload = await upload_audio_assets(force=force_upload)
        assets = asset_payload.get("assets", [])

    if not assets:
        raise HTTPException(
            status_code=404,
            detail="No HeyGen audio assets found. Generate narration audio first.",
        )

    asset_lookup = _build_asset_lookup(assets)
    agent_input = _prepare_agent_input(script, assets)

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
        scene.audio_asset_id = _resolve_asset_id(scene.scene_id, scene.audio_asset_id, asset_lookup)
        scene.talking_photo_id = _normalize_talking_photo_id(scene.talking_photo_id)

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
            response_json = _submit_video_job(payload)
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

        video_id = (response_json.get("data") or {}).get("video_id")
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
                    fail_message = (
                        data_section.get("error")
                        or status_payload.get("message")
                        or "Video rendering failed."
                    )
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
