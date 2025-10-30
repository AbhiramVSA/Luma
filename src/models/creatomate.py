"""Pydantic models for Creatomate automation workflows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from models.heygen import HeyGenVideoResult


class CreatomateSceneAsset(BaseModel):
    """Scene-level metadata provided by the client for Creatomate assembly."""

    scene_id: str = Field(..., description="Identifier matching the screenplay scene label")
    image_url: str = Field(..., description="Hosted image asset associated with the scene")
    notes: str | None = Field(default=None, description="Free-form notes for the automation agent")

    @model_validator(mode="after")
    def _normalise(self) -> CreatomateSceneAsset:
        self.scene_id = self.scene_id.strip()
        self.image_url = self.image_url.strip()
        if not self.scene_id:
            raise ValueError("scene_id cannot be empty")
        if not self.image_url:
            raise ValueError("image_url cannot be empty")
        if self.notes is not None:
            trimmed = self.notes.strip()
            self.notes = trimmed if trimmed else None
        return self


class CreatomateRenderRequest(BaseModel):
    """API request body for end-to-end Creatomate renders."""

    script: str = Field(
        ..., min_length=10, description="Scene-based script used for narration and video generation"
    )
    template_id: str | None = Field(
        default=None,
        description=(
            "Creatomate template identifier. Falls back to configured default when omitted."
        ),
    )
    scenes: list[CreatomateSceneAsset] = Field(
        default_factory=list,
        description="Optional scene metadata (images, notes) keyed by scene_id",
    )
    force_upload_audio: bool = Field(
        default=True,
        description="Force re-uploading audio assets to HeyGen prior to video generation",
    )
    wait_for_render: bool = Field(
        default=False,
        description="When True, poll Creatomate until render completes before responding",
    )

    @model_validator(mode="after")
    def _normalise(self) -> CreatomateRenderRequest:
        self.script = self.script.strip()
        if not self.script:
            raise ValueError("script cannot be empty")

        seen: set[str] = set()
        for scene in self.scenes:
            key = scene.scene_id.strip().lower()
            if key in seen:
                raise ValueError(f"Duplicate scene_id detected: {scene.scene_id}")
            seen.add(key)
        return self


class CreatomateAgentOutput(BaseModel):
    """Structured payload returned by the Creatomate agent."""

    template_id: str = Field(..., description="Template identifier to submit to Creatomate")
    modifications: dict[str, str] = Field(
        default_factory=dict,
        description="Placeholder modifications mapping for Creatomate render",
    )

    @model_validator(mode="after")
    def _validate(self) -> CreatomateAgentOutput:
        self.template_id = self.template_id.strip()
        if not self.template_id:
            raise ValueError("template_id cannot be empty")
        if not self.modifications:
            raise ValueError("modifications cannot be empty")
        return self


class SceneVideoAsset(BaseModel):
    """Mapping of generated scene videos to Creatomate placeholders."""

    scene_id: str
    order: int
    video_url: str
    placeholder: str | None = None


class CreatomateRenderResponse(BaseModel):
    """Automated pipeline response combining intermediate assets and Creatomate job info."""

    status: Literal["success", "failed"]
    template_id: str
    modifications: dict[str, str] = Field(default_factory=dict)
    creatomate_job: dict[str, Any] = Field(default_factory=dict)
    audio_outputs: list[dict[str, Any]] = Field(default_factory=list)
    scene_videos: list[SceneVideoAsset] = Field(default_factory=list)
    heygen_results: list[HeyGenVideoResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
