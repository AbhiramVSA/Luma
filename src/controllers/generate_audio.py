from src.utils.agents import audio_agent
from src.config.config import settings
from elevenlabs.client import ElevenLabs


async def generate_prompt(script: str):
    prompt = await audio_agent.run(script)

def generate_audio(prompt: str):
    elevenlabs = ElevenLabs(
    api_key=settings.ELEVENLABS_API_KEY,
    )
    audio = elevenlabs.text_to_dialogue.convert(
    inputs=[
        {
            "text": "[cheerfully] Hello, how are you?",
            "voice_id": "9BWtsMINqrJLrRacOk9x",
        },
        {
            "text": "[stuttering] I'm... I'm doing well, thank you",
            "voice_id": "IKne3meq5aSn9XLyUdCD",
        }
    ]
)
    
    return audio



