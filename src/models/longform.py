"""Pydantic models for long-form scene audio synthesis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LongformScenesRequest(BaseModel):
    """Incoming payload containing the entire multi-scene script."""

    script: str = Field(
        ...,
        description="Full meditation script containing scene headers and dialogue.",
    )


class SegmentPausePlan(BaseModel):
    """Represents a single sentence and the pause that should follow it."""

    text: str = Field(..., description="Exact sentence text with explicit pause markers removed.")
    pause_after_seconds: float = Field(
        ..., ge=0.0, description="Pause duration to insert after this sentence, in seconds."
    )


class SceneProcessingSummary(BaseModel):
    """Metadata returned for each processed scene."""

    scene_name: str = Field(..., description="Scene header extracted from the script.")
    segments: list[SegmentPausePlan] = Field(
        default_factory=list,
        description="Ordered sentence segmentation and pauses for the scene.",
    )
    processed_audio_path: str = Field(
        ..., description="Data URL or temporary path referencing the processed scene audio."
    )


class LongformScenesResponse(BaseModel):
    """Aggregated response spanning all processed scenes."""

    scenes: list[SceneProcessingSummary] = Field(
        default_factory=list,
        description="Scene-level segmentation metadata and processed audio references.",
    )
    final_audio_path: str = Field(
        ...,
        description="Data URL or temporary path referencing the fully stitched audio.",
    )
