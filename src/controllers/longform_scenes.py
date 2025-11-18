"""Long-form scene audio synthesis with agent-driven segmentation."""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, cast

import requests
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from pydub import AudioSegment
from pydub.silence import detect_silence

from config.config import settings
from models.elevenlabs_model import LongFormAudioPlan, PauseAdjustmentResponse
from models.longform import (
    LongformScenesResponse,
    SceneProcessingSummary,
    SceneTimingAnalysis,
    SegmentPausePlan,
)
from utils.agents import (
    longform_audio_agent,
    longform_clause_agent,
    longform_splice_agent,
)
from utils.audio_analysis import analyze_scene_audio

logger = logging.getLogger(__name__)

DEFAULT_PAUSE_SECONDS = 1.5
SENTENCE_ENDINGS = {".", "?", "!", "।"}
SPLIT_SILENCE_MAX_OFFSET_MS = 1200
PAUSE_LABEL_PATTERN = r"(?:sec(?:onds?)?|secs?|s)"
PAUSE_ANNOTATION_PATTERN = (
    r"\*?\(?\s*(?:(?P<pause>\d+(?:\.\d+)?)\s*"
    + PAUSE_LABEL_PATTERN
    + r"\b|"
    + PAUSE_LABEL_PATTERN
    + r"\s*(?P<pause_alt>\d+(?:\.\d+)?))\s*\)?\*?"
)

EXPLICIT_PAUSE_PATTERN = re.compile(PAUSE_ANNOTATION_PATTERN, re.IGNORECASE)
SENTENCE_PATTERN = re.compile(
    r"(?P<sentence>.+?[\.\?!।])\s*(?:" + PAUSE_ANNOTATION_PATTERN + r")?",
    re.IGNORECASE | re.DOTALL,
)

MARKUP_NORMALIZATION_PATTERN = re.compile(r"[\s\*_`~\u200b\u200c\u200d]+", re.UNICODE)
MULTIPART_BOUNDARY = "longform-scenes-boundary"


@dataclass(slots=True)
class SceneBlock:
    name: str
    lines: list[str]

    @property
    def raw_text(self) -> str:
        return " ".join(line.strip() for line in self.lines if line.strip()).strip()


class SceneSegmentationPlan(BaseModel):
    segments: list[SegmentPausePlan]


def _serialize_segments_for_agent(segments: list[SegmentPausePlan]) -> list[dict[str, Any]]:
    return [segment.model_dump() for segment in segments]


def _parse_clause_agent_segments(raw_output: object) -> list[SegmentPausePlan]:
    if isinstance(raw_output, str):
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as error:
            logger.warning("Clause agent output was not valid JSON: %s", error)
            return []
    else:
        payload = raw_output

    try:
        plan = SceneSegmentationPlan.model_validate(payload)
    except ValidationError as error:
        logger.warning("Clause agent payload failed validation: %s", error)
        return []

    return list(plan.segments)


def _plan_debug_snapshot(plan: list[SegmentPausePlan], limit: int = 80) -> list[dict[str, object]]:
    snapshot: list[dict[str, object]] = []
    for index, segment in enumerate(plan):
        text = segment.text.strip().replace("\n", " ")
        snapshot.append(
            {
                "index": index,
                "text": text[:limit] + ("…" if len(text) > limit else ""),
                "pause": segment.pause_after_seconds,
            }
        )
    return snapshot


def _normalized_scene_text(segments: list[SegmentPausePlan]) -> str:
    combined = "".join(segment.text.strip() for segment in segments if segment.text)
    return MARKUP_NORMALIZATION_PATTERN.sub("", combined)


AUDIO_FORMAT = "mp3"
ELEVENLABS_TIMEOUT_SECONDS = 240
SPLICE_AGENT_MAX_AUDIO_BYTES = 800_000
PAUSE_DEVIATION_THRESHOLD = 0.2
PAUSE_UPDATE_EPSILON = 1e-3


def _is_scene_header(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if EXPLICIT_PAUSE_PATTERN.search(stripped):
        return False
    return stripped[-1] not in SENTENCE_ENDINGS


def _parse_script(script: str) -> list[SceneBlock]:
    scenes: list[SceneBlock] = []
    current_name: str | None = None
    current_lines: list[str] = []
    fallback_index = 1

    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if _is_scene_header(line):
            if current_name and current_lines:
                scenes.append(SceneBlock(name=current_name, lines=current_lines.copy()))
            current_name = line
            current_lines = []
        else:
            if current_name is None:
                current_name = f"Scene {fallback_index}"
                fallback_index += 1
            current_lines.append(line)

    if current_name and current_lines:
        scenes.append(SceneBlock(name=current_name, lines=current_lines.copy()))

    if not scenes:
        raise HTTPException(status_code=422, detail="Unable to identify any scenes in the script.")

    return scenes


def _remove_pause_markers(text: str) -> str:
    return EXPLICIT_PAUSE_PATTERN.sub("", text)


def _strip_inline_pause_labels(text: str) -> str:
    tokens = [
        "sec",
        "secs",
        "second",
        "seconds",
    ]
    pattern = re.compile(r"\b(" + "|".join(tokens) + r")\b", re.IGNORECASE)
    return pattern.sub("", text)


def _fallback_sentence_plan(scene_text: str) -> list[SegmentPausePlan]:
    segments: list[SegmentPausePlan] = []
    last_end = 0

    for match in SENTENCE_PATTERN.finditer(scene_text):
        sentence = match.group("sentence").strip()
        pause_value = match.group("pause") or match.group("pause_alt")

        # First, completely remove ALL pause markers from the sentence text
        cleaned_sentence = EXPLICIT_PAUSE_PATTERN.sub("", sentence).strip()

        # Then determine the pause duration
        pause_seconds = float(pause_value) if pause_value is not None else 0.0
        if pause_value is None and cleaned_sentence and cleaned_sentence[-1] in SENTENCE_ENDINGS:
            pause_seconds = DEFAULT_PAUSE_SECONDS

        if cleaned_sentence:
            segments.append(
                SegmentPausePlan(text=cleaned_sentence, pause_after_seconds=pause_seconds)
            )
        last_end = match.end()

    remainder = scene_text[last_end:].strip()
    if remainder:
        # Check if remainder has a pause annotation
        pause_match = EXPLICIT_PAUSE_PATTERN.search(remainder)
        pause_seconds = 0.0

        if pause_match:
            pause_match_value = pause_match.group("pause") or pause_match.group("pause_alt")
            if pause_match_value is not None:
                pause_seconds = float(pause_match_value)

        cleaned_remainder = EXPLICIT_PAUSE_PATTERN.sub("", remainder).strip()

        if cleaned_remainder:
            # If no explicit pause but ends with sentence ending, use default
            if pause_seconds == 0.0 and cleaned_remainder[-1] in SENTENCE_ENDINGS:
                pause_seconds = DEFAULT_PAUSE_SECONDS
            segments.append(
                SegmentPausePlan(text=cleaned_remainder, pause_after_seconds=pause_seconds)
            )
        elif pause_seconds > 0.0:
            # If remainder was only a pause marker, apply it to the last segment
            if segments:
                segments[-1].pause_after_seconds = pause_seconds

    if not segments:
        raise HTTPException(status_code=422, detail="No sentences detected within scene text.")

    return segments


async def _derive_segment_plan(
    scene_name: str,
    scene_text: str,
    audio_bytes: bytes,
    fallback_plan: list[SegmentPausePlan],
) -> list[SegmentPausePlan]:
    if not settings.OPENAI_API_KEY:
        logger.debug("OPENAI_API_KEY missing; returning fallback segmentation for '%s'", scene_name)
        return fallback_plan

    logger.debug(
        "Fallback clause plan for '%s': %s",
        scene_name,
        _plan_debug_snapshot(fallback_plan),
    )

    clause_payload = {
        "scene_name": scene_name,
        "scene_text": scene_text,
        "fallback_segments": _serialize_segments_for_agent(fallback_plan),
        "audio_metadata": {
            "byte_length": len(audio_bytes),
        },
    }

    try:
        agent_result = await longform_clause_agent.run(
            json.dumps(clause_payload, ensure_ascii=False)
        )
    except Exception as error:  # pragma: no cover - external service
        logger.warning("Clause segmentation agent failed for '%s': %s", scene_name, error)
        return fallback_plan

    agent_segments = _parse_clause_agent_segments(agent_result.output)
    if not agent_segments:
        logger.warning("Clause segmentation agent returned no usable plan for '%s'", scene_name)
        return fallback_plan

    logger.info("Clause agent plan for '%s': %s", scene_name, _plan_debug_snapshot(agent_segments))

    return _validate_agent_plan(fallback_plan, agent_segments, scene_name)


async def _build_elevenlabs_plan(scenes: list[SceneBlock]) -> LongFormAudioPlan:
    if not scenes:
        raise HTTPException(status_code=422, detail="No scenes available for synthesis.")

    payload = {
        "mode": "scene_collection",
        "scenes": [
            {
                "scene_id": scene.name,
                "text": scene.raw_text,
                "pause_after_seconds": 0.0,
                "enforce_comma_pause": True,
            }
            for scene in scenes
        ],
    }

    try:
        agent_response = await longform_audio_agent.run(json.dumps(payload, ensure_ascii=False))
    except Exception as error:  # pragma: no cover - external service
        logger.warning("ElevenLabs audio tagging agent failed: %s", error)
        raise HTTPException(status_code=502, detail="ElevenLabs audio tagging failed.") from error

    try:
        plan_payload = json.loads(agent_response.output)
        plan = LongFormAudioPlan.model_validate(plan_payload)
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("ElevenLabs audio tagging agent returned invalid payload: %s", error)
        raise HTTPException(
            status_code=502,
            detail="ElevenLabs audio tagging output invalid.",
        ) from error

    if len(plan.segments) != len(scenes):
        logger.warning(
            "ElevenLabs plan mismatch: expected %d segments, got %d",
            len(scenes),
            len(plan.segments),
        )
        raise HTTPException(
            status_code=502,
            detail="ElevenLabs audio plan did not align with parsed scenes.",
        )

    return plan


def _fallback_split_points(audio: AudioSegment, plan: list[SegmentPausePlan]) -> list[int]:
    total_ms = len(audio)
    char_weights = [max(len(segment.text.strip()), 1) for segment in plan]
    total_weight = sum(char_weights) or 1
    split_points: list[int] = []
    cumulative_weight = 0

    for weight in char_weights[:-1]:
        cumulative_weight += weight
        target = int(round(total_ms * (cumulative_weight / total_weight)))
        target = min(max(target, 1), total_ms - 1)
        if split_points and target <= split_points[-1]:
            target = min(split_points[-1] + 1, total_ms - 1)
        split_points.append(target)

    return split_points


def _map_silence_to_targets(
    target_points: list[int],
    silence_midpoints: list[int],
    total_ms: int,
) -> list[int]:
    if not target_points:
        return []

    available = sorted(point for point in silence_midpoints if 0 < point < total_ms)
    chosen_points: list[int] = []

    for target in target_points:
        best_index: int | None = None
        best_point: int | None = None
        best_delta: int | None = None

        for index, point in enumerate(available):
            delta = abs(point - target)
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_point = point
                best_index = index
            if delta <= 80:  # perfect match, stop searching
                break

        if (
            best_point is not None
            and best_delta is not None
            and best_delta <= SPLIT_SILENCE_MAX_OFFSET_MS
        ):
            chosen = best_point
            del available[best_index]  # type: ignore[arg-type]
        else:
            chosen = target

        if chosen_points and chosen <= chosen_points[-1]:
            chosen = min(max(chosen, chosen_points[-1] + 1), total_ms - 1)

        chosen_points.append(chosen)

    return chosen_points


def _measure_trailing_silence(
    segment: AudioSegment,
    silence_thresh: float,
    chunk_size: int = 10,
) -> int:
    """Return the trailing silence duration (ms) for a segment."""

    if len(segment) == 0:
        return 0

    trimmed = segment
    trailing_ms = 0
    reverse_cursor = len(trimmed)

    while reverse_cursor > 0:
        start = max(reverse_cursor - chunk_size, 0)
        chunk = cast(AudioSegment, trimmed[start:reverse_cursor])
        if chunk.dBFS > silence_thresh:
            break
        trailing_ms += reverse_cursor - start
        reverse_cursor = start

    return trailing_ms


def _trim_trailing_silence_to(
    segment: AudioSegment,
    target_ms: int,
    silence_thresh: float,
) -> tuple[AudioSegment, int]:
    """Trim trailing silence so it does not exceed target_ms.

    Returns the updated segment plus the amount of trailing silence kept (in ms).
    """

    existing_ms = _measure_trailing_silence(segment, silence_thresh)
    if existing_ms <= target_ms:
        return segment, existing_ms

    trim_amount = existing_ms - target_ms
    keep_ms = max(len(segment) - trim_amount, 0)
    trimmed_segment = cast(AudioSegment, segment[:keep_ms])
    return trimmed_segment, target_ms


def _slice_and_pause(audio_bytes: bytes, plan: list[SegmentPausePlan]) -> bytes:
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=AUDIO_FORMAT)
    if not plan:
        return audio_bytes

    if len(plan) == 1:
        pause_ms = int(round(plan[0].pause_after_seconds * 1000))
        processed = audio + AudioSegment.silent(duration=pause_ms)
        buffer = io.BytesIO()
        processed.export(buffer, format=AUDIO_FORMAT)
        buffer.seek(0)
        return buffer.getvalue()

    silence_ranges = detect_silence(
        audio,
        min_silence_len=350,
        silence_thresh=audio.dBFS - 16,
        seek_step=10,
    )
    silence_midpoints: list[int] = []
    for start, end in silence_ranges:
        midpoint = int((start + end) / 2)
        if 0 < midpoint < len(audio):
            silence_midpoints.append(midpoint)
    target_points = _fallback_split_points(audio, plan)

    if silence_midpoints:
        split_points = _map_silence_to_targets(target_points, silence_midpoints, len(audio))
    else:
        split_points = target_points

    stitched = AudioSegment.silent(duration=0)
    cursor = 0
    for index, split_point in enumerate(split_points):
        segment_audio = audio[cursor:split_point]
        pause_ms = int(round(plan[index].pause_after_seconds * 1000))

        silence_thresh = audio.dBFS - 16
        tolerance_ms = 60
        existing_silence_ms = _measure_trailing_silence(segment_audio, silence_thresh)

        # Trim excess silence if ElevenLabs inserted more than requested beyond tolerance.
        if existing_silence_ms - pause_ms > tolerance_ms and pause_ms >= 0:
            segment_audio, existing_silence_ms = _trim_trailing_silence_to(
                segment_audio,
                pause_ms,
                silence_thresh,
            )

        stitched += segment_audio

        if pause_ms > 0 and pause_ms - existing_silence_ms > tolerance_ms:
            stitched += AudioSegment.silent(duration=pause_ms - existing_silence_ms)

        cursor = split_point

    stitched += audio[cursor:]
    final_pause_ms = int(round(plan[-1].pause_after_seconds * 1000))
    if final_pause_ms > 0:
        silence_thresh = audio.dBFS - 16
        existing_final_ms = _measure_trailing_silence(stitched, silence_thresh)
        if existing_final_ms - final_pause_ms > 60:
            stitched, _ = _trim_trailing_silence_to(stitched, final_pause_ms, silence_thresh)
        elif final_pause_ms - existing_final_ms > 60:
            stitched += AudioSegment.silent(duration=final_pause_ms - existing_final_ms)

    buffer = io.BytesIO()
    stitched.export(buffer, format=AUDIO_FORMAT)
    buffer.seek(0)
    return buffer.getvalue()


def _build_clause_metrics(
    plan: list[SegmentPausePlan],
    timing_analysis: SceneTimingAnalysis | None,
) -> list[dict[str, float | int | str | None]]:
    if timing_analysis is None:
        return []

    metrics: list[dict[str, float | int | str | None]] = []
    reports = timing_analysis.segments or []

    for index, segment in enumerate(plan):
        report = reports[index] if index < len(reports) else None
        observed_pause_seconds = None
        measured_start_ms = None
        measured_end_ms = None
        measured_pause_ms = None

        if report is not None:
            measured_start_ms = report.measured_start_ms
            measured_end_ms = report.measured_end_ms
            measured_pause_ms = report.measured_pause_ms
            if measured_pause_ms is not None:
                observed_pause_seconds = round(measured_pause_ms / 1000.0, 3)

        metrics.append(
            {
                "clause_index": index,
                "text": segment.text,
                "target_pause_seconds": segment.pause_after_seconds,
                "observed_pause_seconds": observed_pause_seconds,
                "measured_start_ms": measured_start_ms,
                "measured_end_ms": measured_end_ms,
                "measured_pause_ms": measured_pause_ms,
            }
        )

    return metrics


def _needs_splice_review(metrics: list[dict[str, float | int | str | None]]) -> bool:
    for metric in metrics:
        observed = metric.get("observed_pause_seconds")
        target = metric.get("target_pause_seconds")
        if (
            isinstance(observed, int | float)
            and isinstance(target, int | float)
            and abs(float(observed) - float(target)) > PAUSE_DEVIATION_THRESHOLD
        ):
            return True
    return False


async def _request_splice_adjustments(
    scene_name: str,
    plan: list[SegmentPausePlan],
    timing_analysis: SceneTimingAnalysis | None,
    audio_bytes: bytes,
) -> dict[int, float]:
    metrics = _build_clause_metrics(plan, timing_analysis)
    if not metrics or not _needs_splice_review(metrics):
        return {}

    payload: dict[str, object] = {
        "scene_id": scene_name,
        "clauses": metrics,
        "measurement_source": "whisper+vad",
        "expected_clause_count": len(plan),
    }

    if timing_analysis is not None:
        if timing_analysis.transcript_segments:
            payload["transcript_segments"] = [
                segment.model_dump() for segment in timing_analysis.transcript_segments
            ]
        if timing_analysis.silence_windows:
            payload["silence_windows"] = [
                window.model_dump() for window in timing_analysis.silence_windows
            ]

    if audio_bytes and len(audio_bytes) <= SPLICE_AGENT_MAX_AUDIO_BYTES:
        payload["audio_base64"] = base64.b64encode(audio_bytes).decode("ascii")
    else:
        payload["audio_notice"] = {
            "included": False,
            "audio_size_bytes": len(audio_bytes) if audio_bytes else 0,
            "reason": "audio payload exceeds limit" if audio_bytes else "no audio available",
        }

    try:
        response = await longform_splice_agent.run(json.dumps(payload, ensure_ascii=False))
    except Exception as error:  # pragma: no cover - external service
        logger.warning("Splice agent failed for scene '%s': %s", scene_name, error)
        return {}

    try:
        adjustments_payload = json.loads(response.output)
        adjustments = PauseAdjustmentResponse.model_validate(adjustments_payload)
    except (json.JSONDecodeError, ValidationError) as error:
        logger.warning("Invalid splice agent payload for scene '%s': %s", scene_name, error)
        return {}

    return {item.clause_index: item.desired_pause_seconds for item in adjustments.adjustments}


def _apply_pause_adjustments(
    plan: list[SegmentPausePlan],
    adjustments: dict[int, float],
) -> tuple[list[SegmentPausePlan], bool]:
    if not adjustments:
        return plan, False

    updated_plan: list[SegmentPausePlan] = []
    changed = False

    for index, segment in enumerate(plan):
        override = adjustments.get(index)
        if override is None:
            updated_plan.append(segment)
            continue

        sanitized_pause = max(0.0, float(override))
        if not math.isfinite(sanitized_pause):
            sanitized_pause = segment.pause_after_seconds

        if abs(sanitized_pause - segment.pause_after_seconds) > PAUSE_UPDATE_EPSILON:
            changed = True
            updated_plan.append(segment.model_copy(update={"pause_after_seconds": sanitized_pause}))
        else:
            updated_plan.append(segment)

    return (updated_plan if changed else plan), changed


async def _generate_scene_audio(scene_text: str, voice_id: str) -> bytes:
    if not settings.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY is not configured.")
    if not voice_id.strip():
        raise HTTPException(
            status_code=422,
            detail="ElevenLabs voice_id is required for synthesis.",
        )

    payload = {
        "inputs": [
            {
                "text": scene_text,
                "voice_id": voice_id.strip(),
            }
        ]
    }
    headers = {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    def _request() -> bytes:
        response = requests.post(
            settings.ELEVENLABS_URL,
            json=payload,
            headers=headers,
            timeout=ELEVENLABS_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            logger.warning(
                "ElevenLabs synthesis failed (status=%s): %s",
                response.status_code,
                response.text,
            )
            raise HTTPException(status_code=response.status_code, detail=response.text)
        return response.content

    try:
        return await run_in_threadpool(_request)
    except HTTPException:
        raise
    except Exception as error:  # pragma: no cover - external service
        logger.error("ElevenLabs audio synthesis request failed: %s", error)
        raise HTTPException(status_code=502, detail="ElevenLabs audio synthesis failed.") from error


def _validate_agent_plan(
    expected: list[SegmentPausePlan],
    candidate: list[SegmentPausePlan],
    scene_name: str,
) -> list[SegmentPausePlan]:
    if not candidate:
        logger.warning("Clause agent produced an empty plan for scene '%s'", scene_name)
        return expected

    expected_text = _normalized_scene_text(expected)
    candidate_text = _normalized_scene_text(candidate)
    if expected_text != candidate_text:
        logger.warning(
            "Clause agent altered text content for scene '%s'; reverting to fallback", scene_name
        )
        logger.debug(
            "Expected snapshot: %s -- Candidate snapshot: %s",
            _plan_debug_snapshot(expected),
            _plan_debug_snapshot(candidate),
        )
        return expected

    for index, cand in enumerate(candidate):
        if cand.pause_after_seconds < 0:
            logger.warning(
                "Negative pause detected in scene '%s' at index %d; reverting to fallback",
                scene_name,
                index,
            )
            return expected

    if len(expected) != len(candidate):
        logger.debug(
            "Clause agent adjusted segment count for scene '%s' (expected=%d candidate=%d)",
            scene_name,
            len(expected),
            len(candidate),
        )

    return candidate


def _to_data_url(audio_bytes: bytes) -> str:
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    return f"data:audio/mpeg;base64,{encoded}"


async def process_longform_script(script: str) -> tuple[LongformScenesResponse, bytes]:
    scenes = _parse_script(script)
    audio_plan = await _build_elevenlabs_plan(scenes)
    voice_id = audio_plan.voice_id.strip()
    if not voice_id:
        raise HTTPException(
            status_code=502,
            detail="ElevenLabs audio plan did not include a voice_id.",
        )

    summaries: list[SceneProcessingSummary] = []
    processed_scene_audio: list[bytes] = []

    for index, scene in enumerate(scenes):
        raw_text = scene.raw_text
        if not raw_text:
            logger.warning("Skipping empty scene '%s'", scene.name)
            continue

        fallback_plan = _fallback_sentence_plan(raw_text)
        cleaned_text = _remove_pause_markers(raw_text)

        plan_segment = audio_plan.segments[index]
        if (
            plan_segment.segment_id.strip()
            and plan_segment.segment_id.strip() != scene.name.strip()
        ):
            logger.debug(
                "Plan segment id mismatch (plan=%s scene=%s)",
                plan_segment.segment_id,
                scene.name,
            )
        plan_text = plan_segment.text.strip() or cleaned_text
        audio_input_text = _remove_pause_markers(plan_text)

        audio_bytes = await _generate_scene_audio(audio_input_text, voice_id)

        final_plan = await _derive_segment_plan(
            scene_name=scene.name,
            scene_text=raw_text,
            audio_bytes=audio_bytes,
            fallback_plan=fallback_plan,
        )

        plan_source = "agent" if final_plan is not fallback_plan else "fallback"
        logger.info(
            "Scene '%s' using %s segmentation plan: %s",
            scene.name,
            plan_source,
            _plan_debug_snapshot(final_plan),
        )

        processed_audio = _slice_and_pause(audio_bytes, final_plan)

        try:
            timing_analysis = await analyze_scene_audio(processed_audio, final_plan)
        except Exception as error:  # pragma: no cover - diagnostic path
            logger.warning("Timing analysis failed for scene '%s': %s", scene.name, error)
            timing_analysis = None

        adjustments = await _request_splice_adjustments(
            scene.name,
            final_plan,
            timing_analysis,
            processed_audio,
        )

        if adjustments:
            updated_plan, changed = _apply_pause_adjustments(final_plan, adjustments)
            if changed:
                final_plan = updated_plan
                processed_audio = _slice_and_pause(audio_bytes, final_plan)
                try:
                    timing_analysis = await analyze_scene_audio(processed_audio, final_plan)
                except Exception as error:  # pragma: no cover - diagnostic path
                    logger.warning(
                        "Timing analysis failed after splice for scene '%s': %s",
                        scene.name,
                        error,
                    )
                    timing_analysis = None

        processed_scene_audio.append(processed_audio)

        summaries.append(
            SceneProcessingSummary(
                scene_name=scene.name,
                segments=final_plan,
                processed_audio_path=_to_data_url(processed_audio),
                timing_analysis=timing_analysis,
            )
        )

    if not processed_scene_audio:
        raise HTTPException(status_code=422, detail="No scenes produced audio output.")

    final_audio = AudioSegment.silent(duration=0)
    for audio_bytes in processed_scene_audio:
        final_audio += AudioSegment.from_file(io.BytesIO(audio_bytes), format=AUDIO_FORMAT)

    final_buffer = io.BytesIO()
    final_audio.export(final_buffer, format=AUDIO_FORMAT)
    final_buffer.seek(0)
    final_bytes = final_buffer.getvalue()

    response_payload = LongformScenesResponse(
        scenes=summaries,
        final_audio_path=_to_data_url(final_bytes),
    )

    return response_payload, final_bytes


def build_multipart_response(
    metadata: LongformScenesResponse,
    final_audio: bytes,
) -> Iterable[bytes]:
    metadata_json = metadata.model_dump_json()

    yield f"--{MULTIPART_BOUNDARY}\r\n".encode()
    yield b"Content-Type: application/json\r\n\r\n"
    yield metadata_json.encode("utf-8")
    yield b"\r\n"

    yield f"--{MULTIPART_BOUNDARY}\r\n".encode()
    yield b"Content-Type: audio/mpeg\r\n"
    yield b"Content-Disposition: attachment; filename=longform.mp3\r\n\r\n"
    yield final_audio
    yield b"\r\n"
    yield f"--{MULTIPART_BOUNDARY}--\r\n".encode()


def multipart_media_type() -> str:
    return f"multipart/mixed; boundary={MULTIPART_BOUNDARY}"
