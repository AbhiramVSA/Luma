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


class HeyGenAvatarAgentOutput(BaseModel):
    """Structured fields required for HeyGen Avatar IV generation."""

    video_title: str = Field(..., max_length=80)
    script: str = Field(..., min_length=20, max_length=2000)
    voice_id: str = Field(..., min_length=3, max_length=100)
    video_orientation: Literal["portrait", "landscape"] = Field(default="portrait")
    fit: Literal["cover", "contain"] = Field(default="cover")
    custom_motion_prompt: str = Field(..., max_length=500)
    enhance_custom_motion_prompt: bool = Field(default=True)

    @model_validator(mode="after")
    def _sanitize(self) -> HeyGenAvatarAgentOutput:
        self.video_title = self.video_title.strip()
        self.script = self.script.strip()
        self.voice_id = self.voice_id.strip()
        self.custom_motion_prompt = self.custom_motion_prompt.strip()
        if not self.video_title:
            raise ValueError("video_title cannot be empty")
        if not self.script:
            raise ValueError("script cannot be empty")
        if not self.voice_id:
            raise ValueError("voice_id cannot be empty")
        if not self.custom_motion_prompt:
            raise ValueError("custom_motion_prompt cannot be empty")
        return self


class HeyGenAvatarVideoRequest(BaseModel):
    """Request body for generating an Avatar IV video."""

    image_asset_id: str = Field(..., description="Image key returned by HeyGen asset upload API")
    script: str = Field(..., min_length=10, description="Narration text the avatar should speak")
    video_brief: str | None = Field(
        default=None,
        description="Optional high-level creative brief supplied to the agent",
    )
    voice_preferences: str | None = Field(
        default=None,
        description="Voice attributes or preferred HeyGen voice id",
    )
    orientation_hint: Literal["portrait", "landscape"] | None = Field(default=None)
    fit_hint: Literal["cover", "contain"] | None = Field(default=None)
    enhance_motion_override: bool | None = Field(default=None)
    force_upload_audio: bool = Field(
        default=False,
        description="Re-upload local audio assets to HeyGen before generating",
    )

    @model_validator(mode="after")
    def _normalise_fields(self) -> HeyGenAvatarVideoRequest:
        self.script = self.script.strip()
        if not self.script:
            raise ValueError("script cannot be empty")

        if self.video_brief is not None:
            brief = self.video_brief.strip()
            self.video_brief = brief or self.script
        else:
            self.video_brief = self.script

        if self.orientation_hint:
            self.orientation_hint = self.orientation_hint.lower()  # type: ignore[assignment]
        if self.fit_hint:
            self.fit_hint = self.fit_hint.lower()  # type: ignore[assignment]

        return self


class HeyGenAvatarVideoResponse(BaseModel):
    """Response payload for Avatar IV video generation."""

    status: Literal["success", "failed"]
    job: dict[str, Any] = Field(default_factory=dict)
    prompts: HeyGenAvatarAgentOutput | None = None
    audio_asset_id: str | None = None
    audio_reference: str | None = None
    request_payload: dict[str, Any] | None = Field(default=None)
    errors: list[str] = Field(default_factory=list)
