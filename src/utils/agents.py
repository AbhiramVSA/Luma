from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from config.config import settings

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR.parent / "prompts"
ELEVENLABS_PROMPT_PATH = PROMPTS_DIR / "elevenlabs_prompt.md"
HEYGEN_PROMPT_PATH = PROMPTS_DIR / "heygen_prompt.md"
FREEPIK_PROMPT_PATH = PROMPTS_DIR / "freepik_prompt.md"
HEYGEN_AVATAR_PROMPT_PATH = PROMPTS_DIR / "heygen_avatar_prompt.md"


def load_prompt(path: Path) -> str:
    with path.open(encoding="utf-8") as prompt_file:
        return prompt_file.read()


provider = OpenAIProvider(api_key=settings.OPENAI_API_KEY)

model = OpenAIChatModel(model_name="gpt-5", provider=provider)

# Agent for Eleven Labs
audio_agent = Agent(model=model, system_prompt=load_prompt(ELEVENLABS_PROMPT_PATH))

# Agent for Heygen
heygen_agent = Agent(model=model, system_prompt=load_prompt(HEYGEN_PROMPT_PATH))

# Agent for Freepik Kling
freepik_agent = Agent(model=model, system_prompt=load_prompt(FREEPIK_PROMPT_PATH))

# Agent for HeyGen Avatar IV
heygen_avatar_agent = Agent(model=model, system_prompt=load_prompt(HEYGEN_AVATAR_PROMPT_PATH))
