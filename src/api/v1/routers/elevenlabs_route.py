import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from config.config import settings
from models.elevenlabs_model import ScriptRequest
from utils.agents import audio_agent

router = APIRouter()

ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ELEVENLABS_URL = settings.ELEVENLABS_URL
OUTPUT_DIR = Path("generated_audio")
AUDIO_MANIFEST_PATH = OUTPUT_DIR / "scene_audio_map.json"
AUDIO_CACHE_PATH = OUTPUT_DIR / "heygen_assets.json"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}


def _iter_audio_files() -> list[Path]:
    """Return all generated audio files sorted by modified time."""

    if not OUTPUT_DIR.exists():
        return []

    files = [
        path
        for path in OUTPUT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ]

    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _format_size(num_bytes: int) -> str:
    """Render a human readable file size label."""

    if num_bytes < 1024:
        return f"{num_bytes} B"

    size = float(num_bytes)
    for unit in ["KB", "MB", "GB", "TB"]:
        size /= 1024.0
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"

    return f"{num_bytes} B"


@router.post("/generate-audio")
async def generate_audio(script: str = Body(..., embed=True)) -> dict[str, object]:
    """Generate per-scene audio clips through the ElevenLabs dialogue API."""

    agent_response = await audio_agent.run(script)
    print(agent_response)

    try:
        agent_payload = json.loads(agent_response.output)
        script_config = ScriptRequest.model_validate(agent_payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid agent output: {exc}") from exc

    print(script_config)

    OUTPUT_DIR.mkdir(exist_ok=True)

    scene_outputs: list[dict[str, str]] = []
    manifest_records: list[dict[str, str]] = []
    generated_timestamp = datetime.utcnow().isoformat() + "Z"

    for scene in script_config.scenes:
        scene_inputs = [{"text": dialogue.text, "voice_id": dialogue.voice_id} for dialogue in scene.dialogues]

        api_payload = {"inputs": scene_inputs}
        api_headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }

        api_response = requests.post(ELEVENLABS_URL, json=api_payload, headers=api_headers)
        if api_response.status_code != 200:
            raise HTTPException(status_code=api_response.status_code, detail=api_response.text)

        for existing_file in OUTPUT_DIR.glob(f"{scene.scene_id}__*.mp3"):
            try:
                existing_file.unlink()
            except OSError:
                pass

        file_suffix = uuid4().hex[:8]
        file_name = f"{scene.scene_id}__{file_suffix}.mp3"
        file_path = OUTPUT_DIR / file_name

        with file_path.open("wb") as audio_file:
            audio_file.write(api_response.content)

        scene_outputs.append(
            {
                "scene_id": scene.scene_id,
                "file_name": file_name,
                "audio_file": f"/generated_audio/{file_name}",
            }
        )
        manifest_records.append({"scene_id": scene.scene_id, "file_name": file_name})

    if manifest_records:
        manifest_payload = {
            "generated_at": generated_timestamp,
            "scenes": manifest_records,
        }
        with AUDIO_MANIFEST_PATH.open("w", encoding="utf-8") as manifest_file:
            json.dump(manifest_payload, manifest_file, indent=2)

    return {
        "status": "success",
        "outputs": scene_outputs,
        "manifest_file": f"/generated_audio/{AUDIO_MANIFEST_PATH.name}",
    }


@router.get("/audio-files")
async def list_audio_files() -> dict[str, object]:
    """Enumerate locally cached audio files available for reuse or download."""

    files: list[dict[str, object]] = []
    for path in _iter_audio_files():
        stats = path.stat()
        files.append(
            {
                "file_name": path.name,
                "relative_path": f"{OUTPUT_DIR.name}/{path.name}",
                "size_bytes": stats.st_size,
                "size_readable": _format_size(stats.st_size),
                "modified_at": datetime.utcfromtimestamp(stats.st_mtime).isoformat() + "Z",
                "download_url": f"/generated_audio/{path.name}",
            }
        )

    return {
        "count": len(files),
        "files": files,
        "manifest_present": AUDIO_MANIFEST_PATH.exists(),
        "asset_cache_present": AUDIO_CACHE_PATH.exists(),
    }


@router.delete("/audio-files")
async def clear_audio_files() -> dict[str, object]:
    """Remove generated audio assets and supporting metadata from disk."""

    deleted_files: list[str] = []
    errors: list[str] = []

    for path in _iter_audio_files():
        try:
            path.unlink()
            deleted_files.append(path.name)
        except OSError as exc:  # pragma: no cover - filesystem specific
            errors.append(f"Failed to delete {path.name}: {exc}")

    removed_metadata: list[str] = []
    for metadata_file in [AUDIO_MANIFEST_PATH, AUDIO_CACHE_PATH]:
        if metadata_file.exists():
            try:
                metadata_file.unlink()
                removed_metadata.append(metadata_file.name)
            except OSError as exc:  # pragma: no cover - filesystem specific
                errors.append(f"Failed to delete {metadata_file.name}: {exc}")

    if errors:
        raise HTTPException(status_code=500, detail="; ".join(errors))

    return {
        "status": "success",
        "deleted": len(deleted_files),
        "deleted_files": deleted_files,
        "removed_metadata": removed_metadata,
    }
