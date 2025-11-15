"""Long-form scene audio synthesis with agent-driven segmentation."""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import requests
from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydub import AudioSegment
from pydub.silence import detect_silence

from config.config import settings
from models.elevenlabs_model import LongFormAudioPlan
from models.longform import (
    LongformScenesResponse,
    SceneProcessingSummary,
    SegmentPausePlan,
)
from utils.agents import longform_audio_agent

logger = logging.getLogger(__name__)

DEFAULT_PAUSE_SECONDS = 1.5
SENTENCE_ENDINGS = {".", "?", "!", "।"}
PAUSE_ANNOTATION_PATTERN = (
    r"(?:[*_]{0,2})"
    r"\(\s*(?P<pause>\d+(?:\.\d+)?)\s*(?:sec(?:onds?)?|s)\s*\)"
    r"(?:[*_]{0,2})"
)

EXPLICIT_PAUSE_PATTERN = re.compile(PAUSE_ANNOTATION_PATTERN, re.IGNORECASE)
SENTENCE_PATTERN = re.compile(
    r"(?P<sentence>.+?[\.?\?!।])\s*(?:" + PAUSE_ANNOTATION_PATTERN + r")?",
    re.IGNORECASE | re.DOTALL,
)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "longform_segmentation_prompt.md"
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


def _load_segmentation_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as error:
        logger.error("Failed to load segmentation prompt: %s", error)
        raise HTTPException(status_code=500, detail="Segmentation prompt not available.") from error


SEGMENTATION_AGENT = Agent(
    model=OpenAIChatModel(
        model_name="gpt-5",
        provider=OpenAIProvider(api_key=settings.OPENAI_API_KEY),
    ),
    system_prompt=_load_segmentation_prompt(),
    output_type=SceneSegmentationPlan,  # type: ignore[arg-type]
)

AUDIO_FORMAT = "mp3"
ELEVENLABS_TIMEOUT_SECONDS = 120


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


def _extract_sentence_plan(scene_text: str) -> list[SegmentPausePlan]:
    segments: list[SegmentPausePlan] = []
    last_end = 0

    for match in SENTENCE_PATTERN.finditer(scene_text):
        sentence = match.group("sentence").strip()
        pause_value = match.group("pause")
        pause_seconds = float(pause_value) if pause_value is not None else 0.0
        if pause_value is None and sentence and sentence[-1] in SENTENCE_ENDINGS:
            pause_seconds = DEFAULT_PAUSE_SECONDS

        cleaned_sentence = EXPLICIT_PAUSE_PATTERN.sub("", sentence).strip()
        if cleaned_sentence:
            segments.append(
                SegmentPausePlan(text=cleaned_sentence, pause_after_seconds=pause_seconds)
            )
        last_end = match.end()

    remainder = scene_text[last_end:].strip()
    if remainder:
        cleaned_remainder = EXPLICIT_PAUSE_PATTERN.sub("", remainder).strip()
        if cleaned_remainder:
            pause_seconds = (
                DEFAULT_PAUSE_SECONDS
                if cleaned_remainder and cleaned_remainder[-1] in SENTENCE_ENDINGS
                else 0.0
            )
            segments.append(
                SegmentPausePlan(text=cleaned_remainder, pause_after_seconds=pause_seconds)
            )

    if not segments:
        raise HTTPException(status_code=422, detail="No sentences detected within scene text.")

    return segments


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
    split_points: list[int] = []
    for start, end in silence_ranges:
        midpoint = int((start + end) / 2)
        if 0 < midpoint < len(audio):
            split_points.append(midpoint)
        if len(split_points) == len(plan) - 1:
            break

    if len(split_points) < len(plan) - 1:
        split_points = _fallback_split_points(audio, plan)

    deduped_points: list[int] = []
    for point in sorted(split_points):
        if point <= 0 or point >= len(audio):
            continue
        if deduped_points and abs(point - deduped_points[-1]) < 30:
            continue
        deduped_points.append(point)

    split_points = deduped_points[: len(plan) - 1]

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


async def _run_segmentation_agent(
    scene_name: str,
    scene_text: str,
    audio_bytes: bytes,
) -> list[SegmentPausePlan]:
    prompt = (
        "Analyse this meditation scene and list each sentence with the pause you believe "
        "should follow based solely on the text.\n\nScene: "
        f"{scene_name}\n\n{scene_text}"
    )

    try:
        run_result = await SEGMENTATION_AGENT.run(prompt)
    except Exception as error:  # pragma: no cover - external service
        logger.warning("Segmentation agent failed for %s: %s", scene_name, error)
        raise HTTPException(status_code=502, detail="Segmentation agent failed.") from error

    agent_plan = run_result.output
    try:
        return list(agent_plan.segments)
    except ValidationError as error:
        logger.warning("Segmentation agent returned invalid payload for %s: %s", scene_name, error)
        raise HTTPException(status_code=502, detail="Segmentation agent output invalid.") from error


def _validate_agent_plan(
    expected: list[SegmentPausePlan],
    candidate: list[SegmentPausePlan],
    scene_name: str,
) -> list[SegmentPausePlan]:
    if len(expected) != len(candidate):
        logger.warning(
            "Segmentation mismatch in scene '%s': expected %d segments, got %d",
            scene_name,
            len(expected),
            len(candidate),
        )
        return expected

    for index, (exp, cand) in enumerate(zip(expected, candidate, strict=False)):
        if exp.text.strip() != cand.text.strip():
            logger.warning(
                "Segmentation text mismatch in scene '%s' at index %d", scene_name, index
            )
            return expected
        if cand.pause_after_seconds < 0:
            logger.warning("Negative pause detected in scene '%s' at index %d", scene_name, index)
            return expected

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

        expected_plan = _extract_sentence_plan(raw_text)
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

        try:
            agent_segments = await _run_segmentation_agent(scene.name, raw_text, audio_bytes)
        except HTTPException:
            agent_segments = expected_plan

        final_plan = _validate_agent_plan(expected_plan, agent_segments, scene.name)

        processed_audio = _slice_and_pause(audio_bytes, final_plan)
        processed_scene_audio.append(processed_audio)

        summaries.append(
            SceneProcessingSummary(
                scene_name=scene.name,
                segments=final_plan,
                processed_audio_path=_to_data_url(processed_audio),
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
