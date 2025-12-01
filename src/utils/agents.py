import logging
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from config.config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR.parent / "prompts"
ELEVENLABS_PROMPT_PATH = PROMPTS_DIR / "elevenlabs_prompt.md"
ELEVENLABS_LONGFORM_PROMPT_PATH = PROMPTS_DIR / "elevenlabs_longform_prompt.md"
HEYGEN_PROMPT_PATH = PROMPTS_DIR / "heygen_prompt.md"
FREEPIK_PROMPT_PATH = PROMPTS_DIR / "freepik_prompt.md"
HEYGEN_AVATAR_PROMPT_PATH = PROMPTS_DIR / "heygen_avatar_prompt.md"
CREATOMATE_PROMPT_PATH = PROMPTS_DIR / "creatomate_prompt.md"
LONGFORM_SANITIZER_PROMPT_PATH = PROMPTS_DIR / "longform_sanitizer_prompt.md"
LONGFORM_SPLICE_PROMPT_PATH = PROMPTS_DIR / "longform_splice_prompt.md"
LONGFORM_CLAUSE_PROMPT_PATH = PROMPTS_DIR / "longform_clause_prompt.md"


def load_prompt(path: Path) -> str:
    """Load a prompt file, but fall back to a safe default if the file is missing.

    This prevents import-time failures when the prompts directory isn't present
    (which previously caused the ElevenLabs audio tagging step to fail).
    """
    try:
        with path.open(encoding="utf-8") as prompt_file:
            return prompt_file.read()
    except FileNotFoundError:
        logger.warning("Prompt file not found: %s; using fallback prompt.", path)
        return (
            "You are a helpful assistant that analyzes audio and generates a scene-level "
            "segmentation plan. When given scene text or a transcript, return JSON with "
            "segments containing `text` and `pause_after_seconds` for each clause."
        )


provider = OpenAIProvider(api_key=settings.OPENAI_API_KEY)

# Use GPT-5 for inference as requested
model = OpenAIChatModel(model_name="gpt-5", provider=provider)

# Agent for Eleven Labs (audio tagging / plan inference)
audio_agent = Agent(model=model, system_prompt=load_prompt(ELEVENLABS_PROMPT_PATH))

# Agent for Eleven Labs long-form narration
longform_audio_agent = Agent(
    model=model,
    system_prompt=load_prompt(ELEVENLABS_LONGFORM_PROMPT_PATH),
)

# Agent to sanitize raw meditation scripts before TTS
longform_sanitizer_agent = Agent(
    model=model,
    system_prompt=load_prompt(LONGFORM_SANITIZER_PROMPT_PATH),
)

# Agent to evaluate generated audio pauses and propose splice adjustments
longform_splice_agent = Agent(
    model=model,
    system_prompt=load_prompt(LONGFORM_SPLICE_PROMPT_PATH),
)

# Agent to normalize clause-level segmentation when regex fallback is unreliable
longform_clause_agent = Agent(
    model=model,
    system_prompt=load_prompt(LONGFORM_CLAUSE_PROMPT_PATH),
)

# Agent for Heygen
heygen_agent = Agent(model=model, system_prompt=load_prompt(HEYGEN_PROMPT_PATH))

# Agent for Freepik Kling
freepik_agent = Agent(model=model, system_prompt=load_prompt(FREEPIK_PROMPT_PATH))

# Agent for HeyGen Avatar IV
heygen_avatar_agent = Agent(model=model, system_prompt=load_prompt(HEYGEN_AVATAR_PROMPT_PATH))

# Agent for Creatomate payload preparation
creatomate_agent = Agent(model=model, system_prompt=load_prompt(CREATOMATE_PROMPT_PATH))
