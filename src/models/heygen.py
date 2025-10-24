"""Pydantic models for HeyGen video generation workflows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class HeyGenBackground(BaseModel):
    """Background configuration for HeyGen videos."""

    type: Literal["color", "image"] = Field(description="Background type (color or image)")
    value: str = Field(description="Hex color value or asset reference")


class HeyGenSceneConfig(BaseModel):
    """Scene-level configuration extracted by the HeyGen agent."""

    scene_id: str = Field(description="Unique scene identifier, e.g., scene_1")
    title: str | None = Field(default=None, description="Optional scene title")
    talking_photo_id: str = Field(description="HeyGen talking photo identifier to use")
    background: HeyGenBackground | None = Field(
        default=None,
        description="Background definition (defaults applied later if missing)",
    )
    audio_asset_id: str | None = Field(
        default=None,
        description="HeyGen audio asset id associated with the scene",
    )

    @model_validator(mode="after")
    def ensure_defaults(self) -> HeyGenSceneConfig:
        if self.background is None:
            self.background = HeyGenBackground(type="color", value="#FFFFFF")
        return self


class HeyGenStructuredOutput(BaseModel):
    """Structured response returned by the HeyGen agent."""

    scenes: list[HeyGenSceneConfig] = Field(default_factory=list)


class HeyGenVideoResult(BaseModel):
    """Result of requesting a HeyGen video generation job."""

    scene_id: str
    status: Literal["submitted", "processing", "completed", "failed"]
    video_id: str | None = Field(default=None, description="HeyGen video identifier")
    video_url: str | None = Field(
        default=None, description="Temporary streaming URL for the generated video"
    )
    thumbnail_url: str | None = Field(
        default=None, description="Thumbnail image URL for the generated video"
    )
    message: str | None = None
    request_payload: dict[str, Any] | None = None
    status_detail: dict[str, Any] | None = Field(
        default=None,
        description="Raw payload returned by HeyGen video_status.get for troubleshooting",
    )


class HeyGenVideoRequest(BaseModel):
    """FastAPI request body for HeyGen video generation."""

    script: str = Field(description="Scene-based script annotated with HeyGen asset ids")
    force_upload: bool = Field(
        default=False,
        description="Force re-uploading audio files to HeyGen before generating videos",
    )


class HeyGenVideoResponse(BaseModel):
    """FastAPI response body summarising video generation results."""

    status: Literal["success", "partial", "failed"]
    results: list[HeyGenVideoResult] = Field(default_factory=list)
    missing_assets: list[str] = Field(
        default_factory=list,
        description="Scene identifiers that have no matching audio asset id",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Human-readable errors encountered during processing",
    )
