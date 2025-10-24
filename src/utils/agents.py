import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from config.config import settings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ELEVENLABS_PROMPT_PATH = os.path.join(BASE_DIR, "../prompts/elevenlabs_prompt.md")
HEYGEN_PROMPT_PATH = os.path.join(BASE_DIR, "../prompts/heygen_prompt.md")
FREEPIK_PROMPT_PATH = os.path.join(BASE_DIR, "../prompts/freepik_prompt.md")


def load_prompt(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


provider = OpenAIProvider(api_key=settings.OPENAI_API_KEY)

model = OpenAIChatModel(model_name="gpt-5", provider=provider)

# Agent for Eleven Labs
audio_agent = Agent(model=model, system_prompt=load_prompt(ELEVENLABS_PROMPT_PATH))

# Agent for Heygen
heygen_agent = Agent(model=model, system_prompt=load_prompt(HEYGEN_PROMPT_PATH))

# Agent for freepik
freepik_agent = Agent(model=model, system_prompt=load_prompt(FREEPIK_PROMPT_PATH))
