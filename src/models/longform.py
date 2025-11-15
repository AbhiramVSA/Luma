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
    timing_analysis: SceneTimingAnalysis | None = Field(
        default=None,
        description="Measured Whisper/VAD timings for the processed scene, if available.",
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


class TranscriptSegment(BaseModel):
    """Single Whisper transcription chunk with timestamps."""

    text: str = Field(..., description="Auto-transcribed text snippet.")
    start_ms: int = Field(..., ge=0, description="Start timestamp in milliseconds.")
    end_ms: int = Field(..., ge=0, description="End timestamp in milliseconds.")


class SilenceWindow(BaseModel):
    """Silence span detected by VAD."""

    start_ms: int = Field(..., ge=0, description="Silence start in milliseconds.")
    end_ms: int = Field(..., ge=0, description="Silence end in milliseconds.")
    duration_ms: int = Field(..., ge=0, description="Total silence duration in milliseconds.")


class SegmentTimingReport(BaseModel):
    """Comparison of expected vs measured sentence timing."""

    expected_text: str = Field(..., description="Sentence text requested from plan.")
    expected_pause_seconds: float = Field(..., ge=0.0)
    measured_start_ms: int | None = Field(
        default=None,
        description="Whisper-estimated speech start for this sentence, if aligned.",
    )
    measured_end_ms: int | None = Field(
        default=None,
        description="Whisper-estimated speech end for this sentence, if aligned.",
    )
    measured_pause_ms: int | None = Field(
        default=None,
        description="Observed pause following this sentence derived from Whisper/VAD.",
    )


class SceneTimingAnalysis(BaseModel):
    """Aggregate timing diagnostics for a scene."""

    segments: list[SegmentTimingReport] = Field(
        default_factory=list,
        description="Aligned timing data for each requested sentence.",
    )
    transcript_segments: list[TranscriptSegment] = Field(
        default_factory=list,
        description="Raw Whisper transcript spans with timestamps.",
    )
    silence_windows: list[SilenceWindow] = Field(
        default_factory=list,
        description="Detected VAD silence spans throughout the scene audio.",
    )
