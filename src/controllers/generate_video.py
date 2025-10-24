from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests
from fastapi import HTTPException

from config.config import settings

HEYGEN_UPLOAD_URL = "https://upload.heygen.com/v1/asset"
AUDIO_DIRECTORY = Path("generated_audio")
ASSET_CACHE_PATH = AUDIO_DIRECTORY / "heygen_assets.json"
AUDIO_MANIFEST_PATH = AUDIO_DIRECTORY / "scene_audio_map.json"


def _load_cached_assets() -> dict[str, Any]:
    """Read the on-disk HeyGen asset cache into memory."""

    if not ASSET_CACHE_PATH.exists():
        return {}

    try:
        with ASSET_CACHE_PATH.open("r", encoding="utf-8") as cache_file:
            return json.load(cache_file)
    except json.JSONDecodeError:
        return {}


def _load_scene_manifest() -> dict[str, str]:
    """Load the latest scene-to-file manifest authored by the audio pipeline."""

    if not AUDIO_MANIFEST_PATH.exists():
        return {}

    try:
        with AUDIO_MANIFEST_PATH.open("r", encoding="utf-8") as manifest_file:
            payload = json.load(manifest_file)
    except json.JSONDecodeError:
        return {}

    mapping: dict[str, str] = {}
    scenes_payload = payload.get("scenes") if isinstance(payload, dict) else None
    if isinstance(scenes_payload, list):
        for entry in scenes_payload:
            if not isinstance(entry, dict):
                continue
            scene_id = entry.get("scene_id")
            file_name = entry.get("file_name")
            if isinstance(scene_id, str) and isinstance(file_name, str):
                mapping[file_name] = scene_id

    return mapping


def _save_cached_assets(cache: dict[str, Any]) -> None:
    """Persist the asset cache so we avoid redundant HeyGen uploads."""

    ASSET_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ASSET_CACHE_PATH.open("w", encoding="utf-8") as cache_file:
        json.dump(cache, cache_file, indent=2)


def _resolve_scene_id(file_path: Path, scene_manifest: dict[str, str]) -> str | None:
    """Infer the scene identifier associated with a generated audio file."""

    mapped_scene = scene_manifest.get(file_path.name)
    if isinstance(mapped_scene, str) and mapped_scene.strip():
        return mapped_scene.strip()

    stem = file_path.stem
    if "__" in stem:
        stem = stem.split("__", 1)[0]

    stem = stem.strip()
    return stem or None


def _upload_single_audio(file_path: Path, scene_id: str | None) -> dict[str, Any]:
    """Upload an audio file to HeyGen and return the resulting asset payload."""

    headers = {
        "Content-Type": "audio/mpeg",
        "X-Api-Key": settings.HEYGEN_API_KEY,
        "folder_id": "8f1fd5e9a5c0456882803e2f48a256eb",
    }

    with file_path.open("rb") as audio_file:
        response = requests.post(
            HEYGEN_UPLOAD_URL,
            headers=headers,
            data=audio_file,
            timeout=120,
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"HeyGen upload failed for {file_path.name}: {response.text}",
        )

    payload = response.json()
    if payload.get("code") != 100:
        raise HTTPException(
            status_code=500,
            detail=f"HeyGen upload failed for {file_path.name}: {payload.get('msg') or payload}",
        )

    data = payload.get("data", {})
    if not data.get("id"):
        raise HTTPException(
            status_code=500,
            detail=f"HeyGen upload returned no asset ID for {file_path.name}.",
        )

    return {
        "file_name": file_path.name,
        "asset_id": data["id"],
        "file_type": data.get("file_type", "audio"),
        "name": data.get("name", file_path.stem),
        "folder_id": data.get("folder_id", ""),
        "meta": data.get("meta"),
        "scene_id": scene_id,
    }


def _list_audio_files() -> list[Path]:
    """Enumerate audio files awaiting upload, enforcing a helpful error if missing."""

    if not AUDIO_DIRECTORY.exists():
        raise HTTPException(
            status_code=404,
            detail="No audio files found. Directory 'generated_audio' does not exist.",
        )

    files = sorted(
        [
            path
            for path in AUDIO_DIRECTORY.glob("*.*")
            if path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"} and path.is_file()
        ]
    )

    if not files:
        raise HTTPException(
            status_code=404,
            detail="No audio files found in 'generated_audio'.",
        )

    return files


async def upload_audio_assets(force: bool = False) -> dict[str, Any]:
    """Upload all generated audio files to HeyGen and return their asset IDs.

    Args:
        force: If True, upload files even if they already exist in the cache.

    Returns:
        Mapping of local audio files to HeyGen asset identifiers and metadata.
    """

    if not settings.HEYGEN_API_KEY:
        raise HTTPException(status_code=400, detail="HEYGEN_API_KEY is not configured.")

    audio_files = _list_audio_files()
    asset_cache = _load_cached_assets()
    scene_manifest = _load_scene_manifest()

    if scene_manifest:
        manifest_file_names = set(scene_manifest.keys())
        audio_files = [file for file in audio_files if file.name in manifest_file_names]

    uploaded_assets: list[dict[str, Any]] = []

    for audio_file in audio_files:
        cache_key = audio_file.name
        scene_id = _resolve_scene_id(audio_file, scene_manifest)

        if not scene_id:
            raise HTTPException(
                status_code=400,
                detail=f"Unable to determine scene identifier for audio file '{audio_file.name}'.",
            )

        if not force and cache_key in asset_cache:
            cached_asset = asset_cache[cache_key]
            if isinstance(cached_asset, dict) and cached_asset.get("scene_id") != scene_id:
                cached_asset = {**cached_asset, "scene_id": scene_id}
                asset_cache[cache_key] = cached_asset
            uploaded_assets.append(cached_asset)
            continue

        asset_info = _upload_single_audio(audio_file, scene_id)
        asset_cache[cache_key] = asset_info
        uploaded_assets.append(asset_info)

    _save_cached_assets(asset_cache)

    return {
        "status": "success",
        "count": len(uploaded_assets),
        "assets": uploaded_assets,
        "cache_file": str(ASSET_CACHE_PATH),
        "scene_manifest": str(AUDIO_MANIFEST_PATH) if scene_manifest else None,
    }
