"""Whisper + VAD analysis helpers for longform narration."""

from __future__ import annotations

import io
import logging
from collections.abc import Mapping, Sequence
from typing import Any

import webrtcvad
from openai import AsyncOpenAI, OpenAIError
from pydub import AudioSegment

from config.config import settings
from models.longform import (
    SceneTimingAnalysis,
    SegmentPausePlan,
    SegmentTimingReport,
    SilenceWindow,
    TranscriptSegment,
)

logger = logging.getLogger(__name__)

DEFAULT_WHISPER_MODEL = "gpt-4o-mini-transcribe"
VAD_SAMPLE_RATE = 16_000
VAD_FRAME_MS = 30
MIN_SILENCE_MS = 400

_openai_client: AsyncOpenAI | None = None


def _ensure_async_openai() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required for Whisper analysis.")
        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _openai_client


def _extract_segments_payload(response: object) -> list[Any]:
    segments = getattr(response, "segments", None)
    if segments is None:
        to_dict = getattr(response, "to_dict", None)
        if callable(to_dict):
            mapping = to_dict()
            if isinstance(mapping, Mapping):
                segments = mapping.get("segments")
    if segments is None and isinstance(response, dict):
        segments = response.get("segments")
    return segments if isinstance(segments, list) else []


def _coerce_to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


async def _transcribe_with_whisper(audio_bytes: bytes) -> list[TranscriptSegment]:
    """Run Whisper transcription via OpenAI and return timestamped segments."""

    if not settings.OPENAI_API_KEY:
        logger.warning("Skipping Whisper transcription because OPENAI_API_KEY is missing.")
        return []

    client = _ensure_async_openai()
    buffer = io.BytesIO(audio_bytes)
    buffer.name = "scene.mp3"

    try:
        response = await client.audio.transcriptions.create(
            model=DEFAULT_WHISPER_MODEL,
            file=buffer,
            response_format="verbose_json",
            temperature=0,
        )
    except OpenAIError as error:
        logger.warning("Whisper transcription failed: %s", error)
        return []
    except Exception as error:  # pragma: no cover - network
        logger.warning("Unexpected Whisper transcription error: %s", error)
        return []

    segments: list[TranscriptSegment] = []
    for raw_segment in _extract_segments_payload(response):
        text_value = _segment_field(raw_segment, "text", default="")
        text = _coerce_to_str(text_value).strip()
        if not text:
            continue
        start = _coerce_to_float(_segment_field(raw_segment, "start", default=0.0), 0.0)
        end = _coerce_to_float(_segment_field(raw_segment, "end", default=start), start)
        segments.append(
            TranscriptSegment(
                text=text,
                start_ms=max(int(round(start * 1000)), 0),
                end_ms=max(int(round(end * 1000)), 0),
            )
        )

    return segments


def _segment_field(segment: object, key: str, default: Any) -> Any:
    if isinstance(segment, dict):
        return segment.get(key, default)
    return getattr(segment, key, default)


def _decode_audio(audio_bytes: bytes) -> AudioSegment:
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
    return audio.set_frame_rate(VAD_SAMPLE_RATE).set_channels(1).set_sample_width(2)


def _detect_vad_silence(audio_bytes: bytes) -> list[SilenceWindow]:
    """Return silence windows detected by WebRTC VAD."""

    try:
        mono_audio = _decode_audio(audio_bytes)
    except Exception as error:  # pragma: no cover - ffmpeg failure
        logger.warning("Unable to decode audio for VAD: %s", error)
        return []

    pcm_data = mono_audio.raw_data
    if pcm_data is None:
        return []

    sample_width = mono_audio.sample_width
    frame_byte_length = int(VAD_SAMPLE_RATE * (VAD_FRAME_MS / 1000) * sample_width)
    if frame_byte_length <= 0 or len(pcm_data) < frame_byte_length:
        return []

    vad = webrtcvad.Vad(2)
    silence_windows: list[SilenceWindow] = []
    silence_start_ms: int | None = None

    for offset in range(0, len(pcm_data) - frame_byte_length + 1, frame_byte_length):
        frame = pcm_data[offset : offset + frame_byte_length]
        frame_start_ms = int(((offset // sample_width) / VAD_SAMPLE_RATE) * 1000)
        is_speech = vad.is_speech(frame, VAD_SAMPLE_RATE)

        if not is_speech:
            if silence_start_ms is None:
                silence_start_ms = frame_start_ms
            continue

        if silence_start_ms is not None:
            duration = frame_start_ms - silence_start_ms
            if duration >= MIN_SILENCE_MS:
                silence_windows.append(
                    SilenceWindow(
                        start_ms=silence_start_ms,
                        end_ms=frame_start_ms,
                        duration_ms=duration,
                    )
                )
            silence_start_ms = None

    total_ms = len(mono_audio)
    if silence_start_ms is not None:
        duration = total_ms - silence_start_ms
        if duration >= MIN_SILENCE_MS:
            silence_windows.append(
                SilenceWindow(
                    start_ms=silence_start_ms,
                    end_ms=total_ms,
                    duration_ms=duration,
                )
            )

    return silence_windows


def _first_silence_after(
    timestamp_ms: int,
    windows: Sequence[SilenceWindow],
) -> SilenceWindow | None:
    for window in windows:
        if window.start_ms >= timestamp_ms:
            return window
    return None


def _build_segment_reports(
    expected: Sequence[SegmentPausePlan],
    transcript: Sequence[TranscriptSegment],
    silence_windows: Sequence[SilenceWindow],
) -> list[SegmentTimingReport]:
    reports: list[SegmentTimingReport] = []

    for index, expected_segment in enumerate(expected):
        transcript_segment = transcript[index] if index < len(transcript) else None
        next_segment = transcript[index + 1] if index + 1 < len(transcript) else None

        measured_pause = None
        if transcript_segment and next_segment:
            measured_pause = max(0, next_segment.start_ms - transcript_segment.end_ms)

        reports.append(
            SegmentTimingReport(
                expected_text=expected_segment.text,
                expected_pause_seconds=expected_segment.pause_after_seconds,
                measured_start_ms=transcript_segment.start_ms if transcript_segment else None,
                measured_end_ms=transcript_segment.end_ms if transcript_segment else None,
                measured_pause_ms=measured_pause,
            )
        )

    for report in reports:
        if report.measured_pause_ms is not None or report.measured_end_ms is None:
            continue
        trailing = _first_silence_after(report.measured_end_ms, silence_windows)
        if trailing:
            report.measured_pause_ms = trailing.duration_ms

    return reports


async def analyze_scene_audio(
    audio_bytes: bytes,
    expected_plan: Sequence[SegmentPausePlan],
) -> SceneTimingAnalysis:
    """Compute Whisper transcription + VAD pauses for a processed scene."""

    if not audio_bytes:
        return SceneTimingAnalysis()

    transcript_segments = await _transcribe_with_whisper(audio_bytes)
    silence_windows = _detect_vad_silence(audio_bytes)
    segment_reports = _build_segment_reports(expected_plan, transcript_segments, silence_windows)

    return SceneTimingAnalysis(
        segments=segment_reports,
        transcript_segments=list(transcript_segments),
        silence_windows=list(silence_windows),
    )
