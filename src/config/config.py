from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

load_dotenv(dotenv_path=".env", override=True)


class Settings(BaseSettings):
    OPENAI_API_KEY: str = Field(default="")
    GROQ_API_KEY: str = Field(default="")
    ELEVENLABS_API_KEY: str = Field(default="")
    ELEVENLABS_URL: str = Field(default="https://api.elevenlabs.io/v1/text-to-dialogue")
    HEYGEN_API_KEY: str = Field(default="")
    HEYGEN_DEFAULT_TALKING_PHOTO_ID: str = Field(default="Monica_inSleeveless_20220819")
    FREEPIK_API_KEY: str = Field(default="")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
