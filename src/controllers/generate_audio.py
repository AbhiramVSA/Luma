from typing import Sequence

from elevenlabs import play
from elevenlabs.client import ElevenLabs
from elevenlabs.types.dialogue_input import DialogueInput
from pydantic_ai import AgentRunResult

from config.config import settings
from utils.agents import audio_agent


async def generate_prompt(script: str) -> AgentRunResult[str]:
    """Use the audio agent to enrich a raw script."""

    return await audio_agent.run(script)


def synthesize_dialogue(inputs: Sequence[DialogueInput]) -> None:
    """Generate dialogue audio with ElevenLabs and play the stream."""

    elevenlabs = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

    audio_stream = elevenlabs.text_to_dialogue.convert(inputs=inputs)
    play(audio_stream)


def demo_dialogue() -> None:
    """Example wrapper showcasing how to invoke dialogue synthesis."""

    dialogue_inputs: list[DialogueInput] = [
        DialogueInput(
            text="[cheerfully] Hello, how are you?",
            voice_id="9BWtsMINqrJLrRacOk9x",
        ),
        DialogueInput(
            text="[stuttering] I'm... I'm doing well, thank you",
            voice_id="IKne3meq5aSn9XLyUdCD",
        ),
    ]

    synthesize_dialogue(dialogue_inputs)
