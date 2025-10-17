import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from config.config import settings
from models.elevenlabs import ScriptRequest
from utils.agents import audio_agent

router = APIRouter()

ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ELEVENLABS_URL = settings.ELEVENLABS_URL
OUTPUT_DIR = Path("generated_audio")
AUDIO_MANIFEST_PATH = OUTPUT_DIR / "scene_audio_map.json"


@router.post("/generate-audio")
async def generate_audio(script: str) -> dict[str, object]:
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
                "audio_file": str(file_path),
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
        "manifest_file": str(AUDIO_MANIFEST_PATH),
    }
