"""FastAPI application entry point."""

import logging
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException as FastAPIHTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from api.v1.api import api_router

LOG_FORMAT = "[%(asctime)s] %(levelname)s %(name)s:%(lineno)d - %(message)s"

if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

logger = logging.getLogger("innerbhakti.api")

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.perf_counter()
    logger.info("HTTP %s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("HTTP %s %s failed", request.method, request.url.path)
        raise

    duration_ms = (time.perf_counter() - start_time) * 1000.0
    logger.info(
        "HTTP %s %s completed in %.2f ms (status=%s)",
        request.method,
        request.url.path,
        duration_ms,
        response.status_code,
    )
    return response


@app.exception_handler(FastAPIHTTPException)
async def handle_http_exception(request: Request, exc: FastAPIHTTPException):
    logger.warning(
        "Handled HTTPException path=%s method=%s status=%s detail=%s",
        request.url.path,
        request.method,
        exc.status_code,
        exc.detail,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    logger.exception("Unhandled exception path=%s method=%s", request.url.path, request.method)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8002)
