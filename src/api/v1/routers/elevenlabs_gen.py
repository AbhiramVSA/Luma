from fastapi import APIRouter, HTTPException
from pydantic import ValidationError
import requests
import json
from config.config import settings
from models.elevenlabs import ScriptRequest
from utils.agents import audio_agent
from pathlib import Path

router = APIRouter()

ELEVENLABS_API_KEY = settings.ELEVENLABS_API_KEY
ELEVENLABS_URL = settings.ELEVENLABS_URL


@router.post("/generate-audio")
async def generate_audio(script: str):
    """
    Takes structured script (with dialogues & voices)
    Enhances dialogues with expressive audio tags
    Calls ElevenLabs text-to-dialogue API to generate per-scene audio
    """
    
    structured_output_raw = await audio_agent.run(script)
    
    print(structured_output_raw)

    try:
        # Extract the JSON string from AgentRunResult.output and parse it
        json_output = json.loads(structured_output_raw.output)
        # Validate and coerce into Pydantic model
        structured_output = ScriptRequest.model_validate(json_output)
        
    except ValidationError as e:
        
        raise HTTPException(status_code=422, detail=f"Invalid agent output: {e}")
    
    print(structured_output)

    # Create generated_audio directory if it doesn't exist
    output_dir = Path("generated_audio")
    output_dir.mkdir(exist_ok=True)

    outputs = []

    for scene in structured_output.scenes:
        # Combine dialogues into ElevenLabs-compatible structure
        inputs = [{"text": d.text, "voice_id": d.voice_id} for d in scene.dialogues]

        payload = {
            "inputs": inputs
        }

        headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }

        response = requests.post(settings.ELEVENLABS_URL, json=payload, headers=headers)

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        # The response is binary audio data
        filename = f"{scene.scene_id}.mp3"
        filepath = output_dir / filename
        with open(filepath, "wb") as f:
            f.write(response.content)

        outputs.append({
            "scene_id": scene.scene_id,
            "audio_file": str(filepath),
        })

    return {"status": "success", "outputs": outputs}
