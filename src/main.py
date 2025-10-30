"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.v1.api import api_router

app = FastAPI(
    title="InnerBhakti Video Generation Automation",
    description="API for generating audio and video content using AI services",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

generated_audio_dir = Path("generated_audio")
generated_audio_dir.mkdir(parents=True, exist_ok=True)

generated_assets_dir = Path("generated_assets")
generated_assets_dir.mkdir(parents=True, exist_ok=True)
generated_images_dir = generated_assets_dir / "images"
generated_images_dir.mkdir(parents=True, exist_ok=True)

app.mount(
    "/generated_audio",
    StaticFiles(directory=generated_audio_dir, check_dir=False),
    name="generated_audio",
)

app.mount(
    "/generated_assets",
    StaticFiles(directory=generated_assets_dir, check_dir=False),
    name="generated_assets",
)

app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)
