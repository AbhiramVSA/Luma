"""Long-form scene audio synthesis with agent-driven segmentation."""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import random
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import requests
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from pydub import AudioSegment

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
LONGFORM_VOICE_ID = "iPsiOpS0MlTcbGDk1jRS"
SENTENCE_ENDINGS = {".", "?", "!", "।"}
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
ELEVENLABS_MAX_ATTEMPTS = 4
ELEVENLABS_INITIAL_BACKOFF_SECONDS = 1.5
ELEVENLABS_MAX_BACKOFF_SECONDS = 10.0
ELEVENLABS_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
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


def _condense_text(text: str, limit: int = 300) -> str:
    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    return collapsed[:limit] + ("…" if len(collapsed) > limit else "")


def _describe_elevenlabs_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _condense_text(value)

    return _condense_text(response.text)


def _sleep_with_backoff(attempt: int) -> None:
    delay = min(
        ELEVENLABS_INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
        ELEVENLABS_MAX_BACKOFF_SECONDS,
    )
    time.sleep(delay + random.uniform(0, 0.5))


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
        "voice_id_override": LONGFORM_VOICE_ID,
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

    plan.voice_id = LONGFORM_VOICE_ID
    return plan


async def _synthesize_scene_audio(
    plan: list[SegmentPausePlan],
    voice_id: str,
) -> bytes:
    if not plan:
        raise HTTPException(status_code=422, detail="Segmentation plan cannot be empty.")

    combined = AudioSegment.silent(duration=0)

    for index, segment in enumerate(plan):
        clause_text = segment.text.strip()
        if clause_text:
            clause_audio_bytes = await _generate_scene_audio(clause_text, voice_id)
            clause_audio = AudioSegment.from_file(
                io.BytesIO(clause_audio_bytes),
                format=AUDIO_FORMAT,
            )
            combined += clause_audio
        else:
            logger.debug("Skipping empty clause at index %d", index)

        pause_ms = max(int(round(segment.pause_after_seconds * 1000)), 0)
        if pause_ms > 0:
            combined += AudioSegment.silent(duration=pause_ms)

    buffer = io.BytesIO()
    combined.export(buffer, format=AUDIO_FORMAT)
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

    def _request_with_retry() -> bytes:
        last_error: Exception | None = None

        for attempt in range(1, ELEVENLABS_MAX_ATTEMPTS + 1):
            try:
                response = requests.post(
                    settings.ELEVENLABS_URL,
                    json=payload,
                    headers=headers,
                    timeout=ELEVENLABS_TIMEOUT_SECONDS,
                )
            except requests.RequestException as error:  # pragma: no cover - external service
                last_error = error
                logger.warning(
                    "ElevenLabs synthesis attempt %d/%d failed to reach API: %s",
                    attempt,
                    ELEVENLABS_MAX_ATTEMPTS,
                    error,
                )
            except Exception as error:  # pragma: no cover - external service
                last_error = error
                logger.warning(
                    "Unexpected ElevenLabs client error on attempt %d/%d: %s",
                    attempt,
                    ELEVENLABS_MAX_ATTEMPTS,
                    error,
                )
            else:
                if response.status_code == 200:
                    return response.content

                detail_preview = _describe_elevenlabs_error(response)
                if (
                    response.status_code in ELEVENLABS_RETRYABLE_STATUS
                    and attempt < ELEVENLABS_MAX_ATTEMPTS
                ):
                    logger.warning(
                        "ElevenLabs synthesis attempt %d/%d returned status %s; retrying: %s",
                        attempt,
                        ELEVENLABS_MAX_ATTEMPTS,
                        response.status_code,
                        detail_preview or "no response body",
                    )
                else:
                    logger.warning(
                        "ElevenLabs synthesis failed (status=%s): %s",
                        response.status_code,
                        detail_preview or "no response body",
                    )
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=detail_preview or "ElevenLabs request failed.",
                    )

            if attempt < ELEVENLABS_MAX_ATTEMPTS:
                _sleep_with_backoff(attempt)

        logger.error("ElevenLabs audio synthesis exhausted retries.")
        detail = "ElevenLabs audio synthesis failed."
        if last_error is not None:
            raise HTTPException(status_code=502, detail=detail) from last_error
        raise HTTPException(status_code=502, detail=detail)

    try:
        return await run_in_threadpool(_request_with_retry)
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
        final_plan = await _derive_segment_plan(
            scene_name=scene.name,
            scene_text=raw_text,
            fallback_plan=fallback_plan,
        )

        plan_source = "agent" if final_plan is not fallback_plan else "fallback"
        logger.info(
            "Scene '%s' using %s segmentation plan: %s",
            scene.name,
            plan_source,
            _plan_debug_snapshot(final_plan),
        )

        processed_audio = await _synthesize_scene_audio(final_plan, voice_id)

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
                processed_audio = await _synthesize_scene_audio(final_plan, voice_id)
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
