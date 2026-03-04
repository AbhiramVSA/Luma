from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OPENAI_API_KEY: str = Field(default="")
    GROQ_API_KEY: str = Field(default="")
    ELEVENLABS_API_KEY: str = Field(default="")
    ELEVENLABS_URL: str = Field(default="https://api.elevenlabs.io/v1/text-to-dialogue")
    HEYGEN_API_KEY: str = Field(default="")
    HEYGEN_DEFAULT_TALKING_PHOTO_ID: str = Field(default="Monica_inSleeveless_20220819")
    HEYGEN_UPLOAD_FOLDER_ID: str = Field(default="")
    FREEPIK_API_KEY: str = Field(default="")
    CREATOMATE_API_KEY: str = Field(default="")
    CREATOMATE_DEFAULT_TEMPLATE_ID: str = Field(default="")

    DATABASE_URL: str = Field(default="", description="Neon/Postgres connection string")
    JWT_SECRET_KEY: str = Field(default="", description="Secret key for signing auth tokens")
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRES_MINUTES: int = Field(default=60, ge=5, le=24 * 60)

    FRONTEND_ORIGIN: Annotated[str | None, Field(alias="FRONTEND_URL")] = None
    CORS_ADDITIONAL_ORIGINS: str | None = Field(default=None)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        origins: list[str] = []
        if self.FRONTEND_ORIGIN:
            origins.append(self.FRONTEND_ORIGIN.rstrip("/"))
        if self.CORS_ADDITIONAL_ORIGINS:
            for origin in self.CORS_ADDITIONAL_ORIGINS.split(","):
                cleaned = origin.strip().rstrip("/")
                if cleaned:
                    origins.append(cleaned)
        if not origins:
            origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
        return origins


settings = Settings()
