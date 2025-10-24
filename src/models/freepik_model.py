"""Pydantic models for Freepik Kling image-to-video endpoint."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, model_validator


class TrajectoryPoint(BaseModel):
    """Represents a single (x, y) path coordinate for motion brushes."""

    x: int = Field(description="Horizontal coordinate in pixels")
    y: int = Field(description="Vertical coordinate in pixels")


class DynamicMask(BaseModel):
    """Dynamic mask definition accepted by the Kling API."""

    mask: str = Field(description="Base64 encoded image or publicly accessible URL")
    trajectories: list[TrajectoryPoint] = Field(
        default_factory=list,
        description="Optional trajectory points that define motion paths",
    )


class FreepikImageToVideoRequest(BaseModel):
    """Request payload for the Kling 2.1 Std image-to-video endpoint."""

    duration: Literal["5", "10"] = Field(description="Duration of the generated video in seconds")
    webhook_url: HttpUrl | None = Field(
        default=None,
        description="Optional webhook invoked on task status updates",
    )
    image: str | None = Field(
        default=None,
        description="Reference image as Base64 or URL; required when prompt is empty",
    )
    prompt: str | None = Field(
        default=None,
        description="Text prompt describing desired motion when no image is provided",
        max_length=2500,
    )
    negative_prompt: str | None = Field(
        default=None,
        description="Text describing motion to avoid",
        max_length=2500,
    )
    cfg_scale: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Model flexibility; lower is more flexible",
    )
    static_mask: str | None = Field(
        default=None,
        description="Static mask to constrain motion regions",
    )
    dynamic_masks: list[DynamicMask] | None = Field(
        default=None,
        description="Optional dynamic masks for motion brush animations",
    )

    @model_validator(mode="after")
    def ensure_prompt_or_image(self) -> FreepikImageToVideoRequest:
        if not (self.image or self.prompt):
            raise ValueError("Either 'image' or 'prompt' must be provided.")
        return self


class FreepikTaskStatus(BaseModel):
    """Subset of the Freepik task status returned upon submission."""

    task_id: UUID = Field(description="Identifier for the created Kling task")
    status: Literal["CREATED", "IN_PROGRESS", "COMPLETED", "FAILED"] = Field(
        description="Current processing status reported by Freepik",
    )
    generated: list[HttpUrl] = Field(
        default_factory=list,
        description="Collection of generated asset URLs when the task completes",
    )


class FreepikImageToVideoResponse(BaseModel):
    """Response body returned by Freepik when submitting a Kling task."""

    data: FreepikTaskStatus = Field(description="Wrapper containing the task metadata")
