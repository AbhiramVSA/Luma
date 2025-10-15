"""FastAPI application entry point."""

from fastapi import FastAPI

from api.v1.api import api_router

app = FastAPI(
    title="InnerBhakti Video Generation Automation",
    description="API for generating audio and video content using AI services",
    version="0.1.0",
)

app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)
