import os
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env", override=True)


class Settings(BaseSettings):
    OPENAI_API_KEY: str = Field(default="")
    GROQ_API_KEY: str = Field(default="")
    ELEVENLABS_API_KEY: str = Field(default="")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
settings = Settings() 

