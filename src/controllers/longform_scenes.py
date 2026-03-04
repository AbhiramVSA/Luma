"""Long-form scene audio synthesis with agent-driven segmentation."""

from __future__ import annotations

import base64
import difflib
import hashlib
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
from pydub.silence import detect_silence

from config.config import settings
from models.elevenlabs import LongFormAudioPlan, PauseAdjustmentResponse
from models.longform import (
    LongformScenesResponse,
    SceneProcessingSummary,
    SceneTimingAnalysis,
    SegmentPausePlan,
    SilenceWindow,
    TranscriptSegment,
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


@dataclass(slots=True)
class ClauseWindow:
    start_ms: int
    end_ms: int

    def clamp(self, total_ms: int) -> ClauseWindow:
        start = max(0, min(self.start_ms, total_ms))
        end = max(start, min(self.end_ms, total_ms))
        return ClauseWindow(start_ms=start, end_ms=end)


@dataclass(slots=True)
class TranscriptCharTimeline:
    normalized: str
    start_times: list[int]
    end_times: list[int]


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


def _stable_scene_seed(segments: list[SegmentPausePlan]) -> int:
    normalized = "\n".join(segment.text.strip() for segment in segments if segment.text)
    if not normalized:
        return random.randint(0, 2**32 - 1)
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _clone_segment(segment: SegmentPausePlan) -> SegmentPausePlan:
    return segment.model_copy(deep=True)


def _build_scene_input_text(
    carryover: SegmentPausePlan | None,
    scene_text: str,
) -> str:
    scene_text = scene_text.strip()
    if carryover is None:
        return scene_text
    carryover_text = carryover.text.strip()
    if not carryover_text:
        return scene_text
    if not scene_text:
        return carryover_text
    return f"{carryover_text}\n\n{scene_text}".strip()


def _normalize_clause_for_alignment(text: str) -> str:
    cleaned = re.sub(r"[^\w]+", "", text).lower()
    return cleaned


def _token_similarity(lhs: str, rhs: str) -> float:
    if not lhs or not rhs:
        return 0.0
    return difflib.SequenceMatcher(None, lhs, rhs).ratio()


def _match_transcript_segments(
    plan: list[SegmentPausePlan],
    transcript_segments: list[TranscriptSegment],
) -> list[int | None]:
    if not plan or not transcript_segments:
        return [None] * len(plan)

    normalized_plan = [_normalize_clause_for_alignment(segment.text) for segment in plan]
    normalized_transcripts = [
        _normalize_clause_for_alignment(segment.text) for segment in transcript_segments
    ]

    matches: list[int | None] = [None] * len(plan)
    used_indexes: set[int] = set()

    for plan_index, plan_norm in enumerate(normalized_plan):
        best_idx: int | None = None
        best_score = 0.0
        for transcript_index, transcript_norm in enumerate(normalized_transcripts):
            if transcript_index in used_indexes:
                continue
            score = _token_similarity(plan_norm, transcript_norm)
            if score > best_score and score >= 0.45:
                best_idx = transcript_index
                best_score = score
        if best_idx is not None:
            matches[plan_index] = best_idx
            used_indexes.add(best_idx)

    next_transcript = 0
    for plan_index in range(len(plan)):
        if matches[plan_index] is not None:
            matched_index = matches[plan_index]
            if matched_index is not None:
                next_transcript = max(next_transcript, matched_index + 1)
            continue
        while next_transcript in used_indexes and next_transcript < len(transcript_segments):
            next_transcript += 1
        if next_transcript < len(transcript_segments):
            matches[plan_index] = next_transcript
            used_indexes.add(next_transcript)
            next_transcript += 1

    return matches


def _build_transcript_char_timeline(
    transcript_segments: list[TranscriptSegment],
    total_ms: int,
) -> TranscriptCharTimeline | None:
    normalized_chars: list[str] = []
    start_times: list[int] = []
    end_times: list[int] = []
    last_end = 0

    for segment in transcript_segments:
        if not segment.text:
            continue
        start = segment.start_ms if segment.start_ms is not None else last_end
        end = segment.end_ms if segment.end_ms is not None else start
        if end <= start:
            end = start + 40
        start = max(0, min(start, total_ms))
        end = max(start + 1, min(end, total_ms))
        normalized_text = _normalize_clause_for_alignment(segment.text)
        if not normalized_text:
            last_end = end
            continue
        duration = max(end - start, 1)
        length = len(normalized_text)
        for index, char in enumerate(normalized_text):
            ratio_start = index / length
            ratio_end = (index + 1) / length
            char_start = start + int(round(duration * ratio_start))
            char_end = start + int(round(duration * ratio_end))
            char_start = max(0, min(char_start, total_ms))
            char_end = max(char_start + 1, min(char_end, total_ms))
            normalized_chars.append(char)
            start_times.append(char_start)
            end_times.append(char_end)
        last_end = end

    if not normalized_chars:
        return None

    return TranscriptCharTimeline(
        normalized="".join(normalized_chars),
        start_times=start_times,
        end_times=end_times,
    )


def _locate_clause_span(
    clause_text: str,
    timeline: TranscriptCharTimeline,
    search_pos: int,
) -> tuple[int, int] | None:
    target = _normalize_clause_for_alignment(clause_text)
    if not target:
        return None

    normalized = timeline.normalized
    haystack = normalized[search_pos:]
    if not haystack:
        return None

    direct_index = haystack.find(target)
    if direct_index != -1:
        start = search_pos + direct_index
        return (start, min(start + len(target), len(normalized)))

    if len(target) <= 4:
        return None

    matcher = difflib.SequenceMatcher(None, haystack, target)
    match = matcher.find_longest_match(0, len(haystack), 0, len(target))
    if match.size < max(4, int(len(target) * 0.55)):
        return None

    start = search_pos + match.a
    end = min(start + len(target), len(normalized))
    return (start, end)


def _build_windows_from_transcripts(
    plan: list[SegmentPausePlan],
    transcript_segments: list[TranscriptSegment],
    total_ms: int,
) -> list[ClauseWindow]:
    """Derive clause windows by aligning normalized text to transcript char timeline."""

    if not plan or not transcript_segments:
        return []

    timeline = _build_transcript_char_timeline(transcript_segments, total_ms)
    windows: list[ClauseWindow] = []
    last_end = 0

    if timeline is not None:
        search_pos = 0
        for clause_index, clause in enumerate(plan):
            clause_norm = _normalize_clause_for_alignment(clause.text)
            span = _locate_clause_span(clause.text, timeline, search_pos)
            if span is None:
                approx_idx = min(search_pos, len(timeline.start_times) - 1)
                approx_end_idx = min(
                    approx_idx + max(len(clause_norm), 6), len(timeline.end_times) - 1
                )
                if approx_idx >= 0 and approx_idx < len(timeline.start_times):
                    start_ms = timeline.start_times[approx_idx]
                    end_ms = timeline.end_times[approx_end_idx]
                    start_ms = max(last_end, start_ms)
                    end_ms = max(start_ms + 40, end_ms)
                else:
                    fallback_start = last_end
                    remaining = len(plan) - clause_index
                    avg_length = (total_ms - fallback_start) // max(remaining, 1)
                    start_ms = fallback_start
                    end_ms = fallback_start + max(avg_length, 80)
                window = ClauseWindow(start_ms=start_ms, end_ms=min(end_ms, total_ms))
                windows.append(window)
                last_end = window.end_ms
                search_pos = approx_end_idx + 1
                continue

            start_idx, end_idx = span

            # Lookahead to prevent overlapping into the next segment
            if clause_index + 1 < len(plan):
                next_clause = plan[clause_index + 1]
                # Search for next clause starting shortly after current start
                lookahead_pos = start_idx + 1
                next_span = _locate_clause_span(next_clause.text, timeline, lookahead_pos)
                if next_span:
                    next_start_idx = next_span[0]
                    if next_start_idx < end_idx:
                        logger.debug(
                            "Clamping segment %d end (idx %d) to next segment start (idx %d)",
                            clause_index,
                            end_idx,
                            next_start_idx,
                        )
                        end_idx = next_start_idx

            start_idx = max(0, min(start_idx, len(timeline.start_times) - 1))
            end_idx = max(start_idx, min(end_idx - 1, len(timeline.end_times) - 1))
            start_ms = timeline.start_times[start_idx]
            end_ms = timeline.end_times[end_idx]
            start_ms = max(last_end, start_ms)
            end_ms = max(start_ms + 40, end_ms)

            window = ClauseWindow(start_ms=start_ms, end_ms=min(end_ms, total_ms))
            windows.append(window)
            search_pos = end_idx + 1
            last_end = window.end_ms

        if windows:
            windows[-1] = ClauseWindow(start_ms=windows[-1].start_ms, end_ms=total_ms)
            logger.debug("Using transcript-derived clause windows (count=%d)", len(windows))
            return windows

    # Fallback to segment-proportional approach if text alignment failed or timeline missing.

    normalized_transcripts = [
        _normalize_clause_for_alignment(segment.text) for segment in transcript_segments
    ]
    segment_lengths = [max(len(text), 1) for text in normalized_transcripts]

    windows = []
    segment_index = 0
    segment_consumed = 0
    last_end = 0

    def _segment_bounds(index: int, default_start: int) -> tuple[int, int]:
        transcript = transcript_segments[index]
        start = transcript.start_ms
        if start is None:
            if index > 0:
                prev_end = transcript_segments[index - 1].end_ms
                start = prev_end if prev_end is not None else default_start
            else:
                start = default_start
        end = transcript.end_ms if transcript.end_ms is not None else start
        if end <= start:
            end = start + 40
        return (max(0, start), min(total_ms, end))

    for clause_index, segment in enumerate(plan):
        target = _normalize_clause_for_alignment(segment.text)
        required_chars = max(len(target), 6)
        collected_chars = 0
        start_ms: int | None = None
        end_ms: int | None = None

        while collected_chars < required_chars and segment_index < len(transcript_segments):
            seg_length = segment_lengths[segment_index]
            if seg_length <= 0:
                segment_index += 1
                segment_consumed = 0
                continue

            available = seg_length - segment_consumed
            if available <= 0:
                segment_index += 1
                segment_consumed = 0
                continue

            take = min(available, required_chars - collected_chars)
            seg_start, seg_end = _segment_bounds(segment_index, last_end)
            seg_duration = max(seg_end - seg_start, 40)

            ratio_start = segment_consumed / seg_length
            ratio_end = (segment_consumed + take) / seg_length
            partial_start = seg_start + int(round(seg_duration * ratio_start))
            partial_end = seg_start + int(round(seg_duration * ratio_end))

            if start_ms is None:
                start_ms = partial_start
            end_ms = max(partial_end, start_ms + 40)

            collected_chars += take
            segment_consumed += take

            if segment_consumed >= seg_length:
                segment_index += 1
                segment_consumed = 0

            if target and collected_chars >= len(target) * 0.9:
                break

        if start_ms is None or end_ms is None:
            fallback_start = last_end
            remaining = len(plan) - clause_index
            avg_length = (total_ms - fallback_start) // max(remaining, 1)
            start_ms = fallback_start
            end_ms = fallback_start + max(avg_length, 80)
        else:
            start_ms = max(last_end, start_ms)
            end_ms = max(start_ms + 40, end_ms)

        window = ClauseWindow(start_ms=start_ms, end_ms=min(total_ms, end_ms))
        windows.append(window)
        last_end = window.end_ms

    if windows:
        windows[-1] = ClauseWindow(start_ms=windows[-1].start_ms, end_ms=total_ms)

    logger.debug("Using proportional clause windows (count=%d)", len(windows))
    return windows


def _even_clause_windows(count: int, total_ms: int) -> list[ClauseWindow]:
    if count <= 0 or total_ms <= 0:
        return []
    step = total_ms / count
    cursor = 0
    windows: list[ClauseWindow] = []
    for index in range(count):
        next_cursor = total_ms if index == count - 1 else int(round((index + 1) * step))
        next_cursor = max(cursor + 20, next_cursor)
        windows.append(ClauseWindow(start_ms=cursor, end_ms=next_cursor))
        cursor = next_cursor
    windows[-1].end_ms = total_ms
    return windows


def _silence_guided_windows(
    audio_segment: AudioSegment,
    count: int,
    *,
    min_silence_len: int = 350,
    silence_padding_ms: int = 20,
) -> list[ClauseWindow]:
    if count <= 0:
        return []
    total_ms = len(audio_segment)
    if count == 1:
        return [ClauseWindow(start_ms=0, end_ms=total_ms)]

    silence_threshold = int(audio_segment.dBFS - 16)
    silence_ranges = detect_silence(
        audio_segment,
        min_silence_len=min_silence_len,
        silence_thresh=silence_threshold,
        seek_step=10,
    )

    breakpoints: list[int] = []
    for start, end in silence_ranges:
        midpoint = max(0, min(total_ms, int((start + end) / 2)))
        if 0 < midpoint < total_ms:
            breakpoints.append(midpoint)
        if len(breakpoints) >= count - 1:
            break

    if len(breakpoints) < count - 1:
        return _even_clause_windows(count, total_ms)

    breakpoints = sorted(breakpoints[: count - 1])
    windows: list[ClauseWindow] = []
    cursor = 0
    for point in breakpoints:
        start = max(0, cursor - silence_padding_ms)
        end = min(total_ms, point + silence_padding_ms)
        window = ClauseWindow(start_ms=max(cursor, start), end_ms=max(start + 40, end))
        windows.append(window)
        cursor = point
    windows.append(ClauseWindow(start_ms=cursor, end_ms=total_ms))
    return windows


def _snap_to_nearby_silence(
    timestamp_ms: int,
    silence_windows: list[SilenceWindow],
    max_allowed_ms: int | None = None,
) -> int:
    if not silence_windows:
        return timestamp_ms
    best_value = timestamp_ms
    best_delta = SILENCE_SNAP_TOLERANCE_MS + 1

    for window in silence_windows:
        # Check if timestamp is already inside a silence window
        if window.start_ms <= timestamp_ms <= window.end_ms:
            return timestamp_ms

        # Check distance to start and end of silence
        for candidate in (window.start_ms, window.end_ms):
            if max_allowed_ms is not None and candidate > max_allowed_ms:
                continue

            delta = abs(candidate - timestamp_ms)
            if delta < best_delta:
                best_delta = delta
                best_value = candidate

        # Optimization: if we are way past the timestamp, stop searching
        if window.start_ms > timestamp_ms + SILENCE_SNAP_TOLERANCE_MS:
            break

    return best_value if best_delta <= SILENCE_SNAP_TOLERANCE_MS else timestamp_ms


def _snap_clause_boundaries(
    windows: list[ClauseWindow],
    silence_windows: list[SilenceWindow],
    total_ms: int,
) -> list[ClauseWindow]:
    if not silence_windows or not windows:
        return windows

    # Capture original start times to use as hard limits for forward snapping
    original_starts = [w.start_ms for w in windows]

    snapped: list[ClauseWindow] = []
    for index, window in enumerate(windows):
        start = window.start_ms
        end = window.end_ms
        if index == 0:
            start = max(0, _snap_to_nearby_silence(start, silence_windows))
        if index < len(windows) - 1:
            # Prevent snapping past the start of the next word (with small buffer)
            next_word_start = original_starts[index + 1]
            limit = next_word_start + 80  # Allow slight graze but not full word consumption

            snapped_boundary = _snap_to_nearby_silence(end, silence_windows, max_allowed_ms=limit)
            # If we failed to snap (returned original timestamp), and we are not in a silence,
            # we might be cutting a word. But we have no better option unless we search harder.
            # With 800ms tolerance, we should have found something.
            end = snapped_boundary
            windows[index + 1].start_ms = snapped_boundary
        snapped.append(ClauseWindow(start_ms=start, end_ms=end).clamp(total_ms))
    snapped[-1] = ClauseWindow(start_ms=snapped[-1].start_ms, end_ms=total_ms)
    return snapped


def _build_clause_windows(
    plan: list[SegmentPausePlan],
    timing: SceneTimingAnalysis | None,
    total_ms: int,
) -> list[ClauseWindow]:
    if not plan:
        return []
    if timing is None or not timing.transcript_segments:
        return _even_clause_windows(len(plan), total_ms)

    transcript_segments = timing.transcript_segments

    windows = _build_windows_from_transcripts(plan, transcript_segments, total_ms)
    if len(windows) != len(plan):
        match_indexes = _match_transcript_segments(plan, transcript_segments)
        windows = []
        last_end = 0
        for index, match in enumerate(match_indexes):
            if match is not None and 0 <= match < len(transcript_segments):
                segment = transcript_segments[match]
                start_ms = segment.start_ms if segment.start_ms is not None else last_end
                end_ms = segment.end_ms if segment.end_ms is not None else start_ms
            else:
                remaining = len(plan) - index
                avg_length = (total_ms - last_end) // max(remaining, 1)
                start_ms = last_end
                end_ms = start_ms + max(avg_length, 50)

            start_ms = max(last_end, start_ms)
            end_ms = max(start_ms + 40, end_ms)
            windows.append(ClauseWindow(start_ms=start_ms, end_ms=end_ms))
            last_end = end_ms

    if windows:
        windows[-1] = ClauseWindow(start_ms=windows[-1].start_ms, end_ms=total_ms)

    if timing.silence_windows:
        return _snap_clause_boundaries(windows, timing.silence_windows, total_ms)
    return [window.clamp(total_ms) for window in windows]


def _splice_scene_audio(
    source_audio: bytes,
    plan: list[SegmentPausePlan],
    timing: SceneTimingAnalysis | None,
) -> bytes:
    if not plan:
        raise HTTPException(status_code=422, detail="Segmentation plan cannot be empty.")

    audio_segment = AudioSegment.from_file(io.BytesIO(source_audio), format=AUDIO_FORMAT)
    total_ms = len(audio_segment)

    clause_windows = _build_clause_windows(plan, timing, total_ms)
    if len(clause_windows) != len(plan):
        if timing is None or not timing.transcript_segments:
            logger.warning(
                "Clause window mismatch without transcript data; using silence-guided windows.",
            )
            clause_windows = _silence_guided_windows(audio_segment, len(plan))
        else:
            logger.warning(
                "Clause window count mismatch (plan=%d windows=%d); using even distribution.",
                len(plan),
                len(clause_windows),
            )
            clause_windows = _even_clause_windows(len(plan), total_ms)

    stitched = AudioSegment.silent(duration=0)

    for index, (segment, window) in enumerate(zip(plan, clause_windows, strict=True)):
        bounded = window.clamp(total_ms)
        if bounded.end_ms <= bounded.start_ms:
            bounded = ClauseWindow(
                start_ms=bounded.start_ms,
                end_ms=min(total_ms, bounded.start_ms + 80),
            )
        clause_audio = audio_segment[bounded.start_ms : bounded.end_ms]
        if len(clause_audio) == 0:
            logger.warning("Empty clause audio detected at index %d; injecting silence", index)
            clause_audio = AudioSegment.silent(duration=80)
        stitched += clause_audio

        pause_ms = max(int(round(segment.pause_after_seconds * 1000)), 0)
        if pause_ms > 0:
            stitched += AudioSegment.silent(duration=pause_ms)

    output = io.BytesIO()
    stitched.export(output, format=AUDIO_FORMAT)
    output.seek(0)
    return output.getvalue()


def _carryover_trim_offset_ms(
    plan: list[SegmentPausePlan],
    timing: SceneTimingAnalysis | None,
    total_ms: int,
    carryover_count: int,
) -> int:
    if carryover_count <= 0 or not plan:
        return 0
    windows = _build_clause_windows(plan, timing, total_ms)
    if not windows:
        return 0
    cutoff_index = min(carryover_count - 1, len(windows) - 1)
    return windows[cutoff_index].end_ms


def _audio_segment_to_bytes(segment: AudioSegment) -> bytes:
    buffer = io.BytesIO()
    segment.export(buffer, format=AUDIO_FORMAT)
    buffer.seek(0)
    return buffer.getvalue()


def _trim_timing_analysis(
    timing: SceneTimingAnalysis | None,
    trim_ms: int,
    skip_segments: int,
) -> SceneTimingAnalysis | None:
    if timing is None:
        return None

    trim_ms = max(0, trim_ms)
    skip_segments = max(0, skip_segments)

    trimmed_reports = []
    for report in timing.segments[skip_segments:]:
        start_ms = report.measured_start_ms
        end_ms = report.measured_end_ms
        trimmed_reports.append(
            report.model_copy(
                update={
                    "measured_start_ms": None if start_ms is None else max(0, start_ms - trim_ms),
                    "measured_end_ms": None if end_ms is None else max(0, end_ms - trim_ms),
                }
            )
        )

    trimmed_transcripts: list[TranscriptSegment] = []
    for segment in timing.transcript_segments:
        start = segment.start_ms - trim_ms
        end = segment.end_ms - trim_ms
        if end <= 0:
            continue
        trimmed_transcripts.append(
            TranscriptSegment(
                text=segment.text,
                start_ms=max(0, start),
                end_ms=max(max(0, start), end),
            )
        )

    trimmed_silence: list[SilenceWindow] = []
    for window in timing.silence_windows:
        start = window.start_ms - trim_ms
        end = window.end_ms - trim_ms
        if end <= 0:
            continue
        start_adj = max(0, start)
        end_adj = max(start_adj, end)
        trimmed_silence.append(
            SilenceWindow(
                start_ms=start_adj,
                end_ms=end_adj,
                duration_ms=max(0, end_adj - start_adj),
            )
        )

    return SceneTimingAnalysis(
        segments=trimmed_reports,
        transcript_segments=trimmed_transcripts,
        silence_windows=trimmed_silence,
    )


AUDIO_FORMAT = "mp3"
ELEVENLABS_TIMEOUT_SECONDS = 240
ELEVENLABS_MAX_ATTEMPTS = 4
ELEVENLABS_INITIAL_BACKOFF_SECONDS = 1.5
ELEVENLABS_MAX_BACKOFF_SECONDS = 10.0
ELEVENLABS_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
ELEVENLABS_MODEL_ID = "eleven_v3"
ELEVENLABS_DIALOGUE_STABILITY = 0.5
SPLICE_AGENT_MAX_AUDIO_BYTES = 200_000
PAUSE_DEVIATION_THRESHOLD = 0.2
PAUSE_UPDATE_EPSILON = 1e-3
SILENCE_SNAP_TOLERANCE_MS = 800


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
        plan_payload = json.loads(agent_response.output)
        plan = LongFormAudioPlan.model_validate(plan_payload)
    except Exception as error:  # pragma: no cover - external service
        logger.warning("ElevenLabs audio tagging agent failed: %s", error)
        logger.info(
            "Falling back to local plan generation for %d scenes using GPT-5 defaults.",
            len(scenes),
        )

        # Construct a simple fallback LongFormAudioPlan so processing can continue.
        # We keep the voice id default and build minimal segments from scene text.
        segments = []
        for scene in scenes:
            text = scene.raw_text
            char_count = max(1, len(text))
            est_seconds = max(1.0, len(text) / 15.0)
            segments.append(
                {
                    "segment_id": scene.name,
                    "text": text,
                    "emotion": "neutral",
                    "character_count": char_count,
                    "estimated_duration_seconds": est_seconds,
                    "pause_after_seconds": 0.0,
                    "enforce_comma_pause": True,
                }
            )

        plan_payload = {
            "voice_id": LONGFORM_VOICE_ID,
            "segments": segments,
            "total_segments": len(segments),
            "total_estimated_duration_seconds": (
                sum(s["estimated_duration_seconds"] for s in segments)
            ),
            "stitching_instructions": {
                "crossfade_ms": 0,
                "normalize_volume": False,
                "output_format": "mp3",
            },
        }
        try:
            plan = LongFormAudioPlan.model_validate(plan_payload)
        except Exception as sub_err:
            logger.error("Fallback audio plan construction failed: %s", sub_err)
            raise HTTPException(
                status_code=502, detail="ElevenLabs audio tagging failed."
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
    *,
    source_timing: SceneTimingAnalysis | None = None,
    source_audio_bytes: bytes | None = None,
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

    if source_timing is not None:
        payload["source_measurements"] = {}
        if source_timing.transcript_segments:
            payload["source_measurements"]["transcript_segments"] = [
                segment.model_dump() for segment in source_timing.transcript_segments
            ]
        if source_timing.silence_windows:
            payload["source_measurements"]["silence_windows"] = [
                window.model_dump() for window in source_timing.silence_windows
            ]
        if not payload["source_measurements"]:
            payload.pop("source_measurements", None)

    if audio_bytes and len(audio_bytes) <= SPLICE_AGENT_MAX_AUDIO_BYTES:
        payload["audio_base64"] = base64.b64encode(audio_bytes).decode("ascii")
    else:
        payload["audio_notice"] = {
            "included": False,
            "audio_size_bytes": len(audio_bytes) if audio_bytes else 0,
            "reason": "audio payload exceeds limit" if audio_bytes else "no audio available",
        }

    if source_audio_bytes and len(source_audio_bytes) <= SPLICE_AGENT_MAX_AUDIO_BYTES:
        payload["source_audio_base64"] = base64.b64encode(source_audio_bytes).decode("ascii")
    elif source_audio_bytes:
        payload["source_audio_notice"] = {
            "included": False,
            "audio_size_bytes": len(source_audio_bytes),
            "reason": "audio payload exceeds limit",
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


async def _generate_scene_audio(
    scene_text: str,
    voice_id: str,
    *,
    seed: int | None = None,
) -> bytes:
    if not settings.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY is not configured.")
    if not voice_id.strip():
        raise HTTPException(
            status_code=422,
            detail="ElevenLabs voice_id is required for synthesis.",
        )

    payload: dict[str, object] = {
        "inputs": [
            {
                "text": scene_text,
                "voice_id": voice_id.strip(),
            }
        ],
        "model_id": ELEVENLABS_MODEL_ID,
        "settings": {
            "stability": ELEVENLABS_DIALOGUE_STABILITY,
        },
    }
    if seed is not None:
        payload["seed"] = seed
    headers = {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    logger.info(
        "ElevenLabs synthesis preview (voice=%s seed=%s len=%d): %s",
        voice_id.strip(),
        seed if seed is not None else "auto",
        len(scene_text),
        _condense_text(scene_text, 240),
    )

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
    carryover_segment: SegmentPausePlan | None = None

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

        carryover_for_scene = _clone_segment(carryover_segment) if carryover_segment else None
        plan_source = "agent" if final_plan is not fallback_plan else "fallback"
        logger.info(
            "Scene '%s' using %s segmentation plan: %s",
            scene.name,
            plan_source,
            _plan_debug_snapshot(final_plan),
        )

        scene_input_text = _build_scene_input_text(carryover_for_scene, raw_text)
        analysis_plan = ([carryover_for_scene] if carryover_for_scene else []) + list(final_plan)
        seed_plan = analysis_plan if carryover_for_scene else final_plan
        scene_seed = _stable_scene_seed(seed_plan)
        scene_audio = await _generate_scene_audio(scene_input_text, voice_id, seed=scene_seed)

        audio_segment = AudioSegment.from_file(io.BytesIO(scene_audio), format=AUDIO_FORMAT)
        total_ms = len(audio_segment)

        try:
            combined_timing = await analyze_scene_audio(scene_audio, analysis_plan)
        except Exception as error:  # pragma: no cover - diagnostic path
            logger.warning("Source timing analysis failed for scene '%s': %s", scene.name, error)
            combined_timing = None

        carryover_count = 1 if carryover_for_scene else 0
        carryover_trim_ms = _carryover_trim_offset_ms(
            analysis_plan,
            combined_timing,
            total_ms,
            carryover_count,
        )
        carryover_trim_ms = max(0, min(carryover_trim_ms, total_ms))

        trimmed_segment = audio_segment[carryover_trim_ms:]
        if len(trimmed_segment) == 0:
            trimmed_segment = AudioSegment.silent(duration=50)
        trimmed_audio = _audio_segment_to_bytes(trimmed_segment)

        source_timing = _trim_timing_analysis(combined_timing, carryover_trim_ms, carryover_count)

        processed_audio = _splice_scene_audio(trimmed_audio, final_plan, source_timing)

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
            source_timing=source_timing,
            source_audio_bytes=trimmed_audio,
        )

        if adjustments:
            updated_plan, changed = _apply_pause_adjustments(final_plan, adjustments)
            if changed:
                final_plan = updated_plan
                processed_audio = _splice_scene_audio(trimmed_audio, final_plan, source_timing)
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

        carryover_segment = _clone_segment(final_plan[-1]) if final_plan else None

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
