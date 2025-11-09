"""Controller helpers for ElevenLabs audio workflows."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from fastapi import HTTPException
from pydantic import ValidationError

from config.config import settings
from models.elevenlabs_model import (
    LongFormAudioPlan,
    LongFormAudioRequest,
    ScriptRequest,
)
from utils.agents import audio_agent, longform_audio_agent

OUTPUT_DIR = Path("generated_audio")
AUDIO_MANIFEST_PATH = OUTPUT_DIR / "scene_audio_map.json"
AUDIO_CACHE_PATH = OUTPUT_DIR / "heygen_assets.json"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac"}
LONGFORM_MANIFEST_PREFIX = "longform_manifest"
PUNCTUATION_PAUSE_SECONDS = 1.5
PUNCTUATION_MARKS = {",", ".", "।"}

logger = logging.getLogger(__name__)


def _sanitize_component(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def _sanitize_scene_text(text: str) -> str:
    sanitized_lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.lower().startswith("meta"):
            continue
        sanitized_lines.append(raw_line)
    cleaned = "\n".join(sanitized_lines).strip()
    return cleaned


def _split_text_into_clauses(text: str) -> list[tuple[str, bool]]:
    clauses: list[tuple[str, bool]] = []
    buffer: list[str] = []
    for char in text:
        buffer.append(char)
        if char in PUNCTUATION_MARKS:
            clause = "".join(buffer).strip()
            if clause:
                clauses.append((clause, True))
            buffer = []
    trailing = "".join(buffer).strip()
    if trailing:
        clauses.append((trailing, False))
    return clauses


def _get_ffmpeg_path() -> str:
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        raise HTTPException(status_code=500, detail="ffmpeg executable not found on PATH.")
    return ffmpeg_path


def _codec_args_for_format(extension: str) -> list[str]:
    ext = extension.lower()
    if ext == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if ext in {"wav", "wave"}:
        return ["-c:a", "pcm_s16le"]
    if ext == "flac":
        return ["-c:a", "flac"]
    if ext in {"aac", "m4a"}:
        return ["-c:a", "aac", "-b:a", "256k"]
    return []


def _concat_audio_segments_ffmpeg(
    segment_paths: list[Path],
    output_path: Path,
    output_extension: str,
    crossfade_seconds: float,
) -> None:
    output_path = output_path.resolve()
    segment_paths = [path.resolve() for path in segment_paths]

    if not segment_paths:
        raise HTTPException(status_code=422, detail="No audio segments available for stitching.")

    if len(segment_paths) == 1:
        shutil.copyfile(segment_paths[0], output_path)
        return

    ffmpeg_path = _get_ffmpeg_path()
    codec_args = _codec_args_for_format(output_extension)

    if crossfade_seconds <= 0:
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            suffix=".txt",
            encoding="utf-8",
        ) as list_file:
            list_path = Path(list_file.name)
            for path in segment_paths:
                list_file.write(f"file '{path.as_posix()}'\n")

        try:
            cmd = [
                ffmpeg_path,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
            ]
            if codec_args:
                cmd.extend(codec_args)
            cmd.append(str(output_path))
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"ffmpeg concat failed: {exc.stderr.decode('utf-8', 'ignore')}",
            ) from exc
        finally:
            list_path.unlink(missing_ok=True)
        return

    temp_dir = Path(tempfile.mkdtemp(prefix="longform_ffmpeg_"))
    current_path: Path = segment_paths[0]
    try:
        for index, next_path in enumerate(segment_paths[1:], start=1):
            temp_output = temp_dir / f"xf_{index}.{output_extension}"
            cmd = [
                ffmpeg_path,
                "-y",
                "-i",
                str(current_path),
                "-i",
                str(next_path),
                "-filter_complex",
                f"[0:a][1:a]acrossfade=d={crossfade_seconds}:curve1=tri:curve2=tri",
            ]
            if codec_args:
                cmd.extend(codec_args)
            cmd.append(str(temp_output))

            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"ffmpeg acrossfade failed: {exc.stderr.decode('utf-8', 'ignore')}",
                ) from exc

            if current_path not in segment_paths:
                current_path.unlink(missing_ok=True)
            current_path = temp_output

        shutil.move(current_path, output_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _normalize_audio_ffmpeg(output_path: Path, output_extension: str) -> None:
    ffmpeg_path = _get_ffmpeg_path()
    codec_args = _codec_args_for_format(output_extension)
    temp_path = output_path.with_name(f"{output_path.stem}__norm{output_path.suffix}")

    cmd = [ffmpeg_path, "-y", "-i", str(output_path), "-af", "loudnorm"]
    if codec_args:
        cmd.extend(codec_args)
    cmd.append(str(temp_path))

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg normalization failed: {exc.stderr.decode('utf-8', 'ignore')}",
        ) from exc

    shutil.move(temp_path, output_path)


def _create_silence_segment(
    duration_seconds: float,
    output_path: Path,
    output_extension: str,
) -> None:
    if duration_seconds <= 0:
        return

    ffmpeg_path = _get_ffmpeg_path()
    codec_args = _codec_args_for_format(output_extension)

    cmd = [
        ffmpeg_path,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        f"{duration_seconds}",
    ]
    if codec_args:
        cmd.extend(codec_args)
    cmd.append(str(output_path))

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"ffmpeg silence generation failed: {exc.stderr.decode('utf-8', 'ignore')}",
        ) from exc


def list_generated_audio_files() -> list[Path]:
    """Return generated audio files sorted by modified time (newest first)."""

    if not OUTPUT_DIR.exists():
        return []

    files = [
        path
        for path in OUTPUT_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    ]

    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def format_file_size(num_bytes: int) -> str:
    """Render a human readable file size label."""

    if num_bytes < 1024:
        return f"{num_bytes} B"

    size = float(num_bytes)
    for unit in ["KB", "MB", "GB", "TB"]:
        size /= 1024.0
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"

    return f"{num_bytes} B"


async def synthesize_audio_assets(script: str) -> tuple[ScriptRequest, dict[str, Any]]:
    """Generate audio assets for a script and return the structured plan plus output metadata."""

    logger.info("Starting ElevenLabs scene audio synthesis (script_length=%d)", len(script or ""))
    agent_response = await audio_agent.run(script)
    try:
        agent_payload = json.loads(agent_response.output)
        script_config = ScriptRequest.model_validate(agent_payload)
    except ValidationError as exc:
        logger.warning("Invalid ElevenLabs agent output: %s", exc)
        raise HTTPException(status_code=422, detail=f"Invalid agent output: {exc}") from exc

    OUTPUT_DIR.mkdir(exist_ok=True)

    scene_outputs: list[dict[str, str]] = []
    manifest_records: list[dict[str, str]] = []
    generated_timestamp = datetime.utcnow().isoformat() + "Z"

    for scene in script_config.scenes:
        scene_inputs = [
            {"text": dialogue.text, "voice_id": dialogue.voice_id} for dialogue in scene.dialogues
        ]

        api_payload = {"inputs": scene_inputs}
        api_headers = {
            "xi-api-key": settings.ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }

        api_response = requests.post(settings.ELEVENLABS_URL, json=api_payload, headers=api_headers)
        if api_response.status_code != 200:
            logger.warning(
                "ElevenLabs API returned %s for scene %s: %s",
                api_response.status_code,
                scene.scene_id,
                api_response.text,
            )
            raise HTTPException(status_code=api_response.status_code, detail=api_response.text)

        for existing_file in OUTPUT_DIR.glob(f"{scene.scene_id}__*.mp3"):
            with suppress(OSError):
                existing_file.unlink()

        file_suffix = uuid4().hex[:8]
        file_name = f"{scene.scene_id}__{file_suffix}.mp3"
        file_path = OUTPUT_DIR / file_name

        with file_path.open("wb") as audio_file:
            audio_file.write(api_response.content)

        scene_outputs.append(
            {
                "scene_id": scene.scene_id,
                "file_name": file_name,
                "audio_file": f"/generated_audio/{file_name}",
            }
        )
        manifest_records.append({"scene_id": scene.scene_id, "file_name": file_name})

    if manifest_records:
        manifest_payload = {
            "generated_at": generated_timestamp,
            "scenes": manifest_records,
        }
        with AUDIO_MANIFEST_PATH.open("w", encoding="utf-8") as manifest_file:
            json.dump(manifest_payload, manifest_file, indent=2)
        logger.info("Wrote ElevenLabs scene manifest with %d entries", len(manifest_records))

    payload: dict[str, Any] = {
        "status": "success",
        "outputs": scene_outputs,
        "manifest_file": f"/generated_audio/{AUDIO_MANIFEST_PATH.name}",
    }

    logger.info("Completed ElevenLabs scene audio synthesis (scenes=%d)", len(scene_outputs))
    return script_config, payload


async def synthesize_longform_audio(request: LongFormAudioRequest) -> dict[str, Any]:
    """Generate long-form narration, returning individual segments and a stitched master file."""

    if not settings.ELEVENLABS_API_KEY:
        raise HTTPException(status_code=400, detail="ELEVENLABS_API_KEY is not configured.")

    using_scene_mode = bool(request.scenes)
    scene_count = len(request.scenes or [])
    input_mode = "scene_collection" if using_scene_mode else "script"

    logger.info(
        "Starting long-form synthesis (mode=%s, scenes=%d, voice_override=%s)",
        input_mode,
        scene_count,
        bool(request.voice_id),
    )
    scene_definitions: list[dict[str, Any]] = []

    if using_scene_mode and request.scenes:
        for index, scene in enumerate(request.scenes, start=1):
            scene_id = scene.scene_id.strip() if scene.scene_id else f"scene_{index}"
            if not scene_id:
                scene_id = f"scene_{index}"
            scene_title = scene.title.strip() if scene.title else None
            sanitized_text = _sanitize_scene_text(scene.text)
            if not sanitized_text:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Scene "
                        f"'{scene_id}' does not contain narration after removing meta directives."
                    ),
                )
            scene_definitions.append(
                {
                    "scene_id": scene_id,
                    "title": scene_title,
                    "text": sanitized_text,
                    "pause_after_seconds": scene.pause_after_seconds,
                    "enforce_comma_pause": scene.enforce_comma_pause,
                }
            )

        agent_payload_input: dict[str, Any] = {
            "mode": "scene_collection",
            "scenes": scene_definitions,
        }
        if request.voice_id:
            agent_payload_input["voice_id_override"] = request.voice_id.strip()

        agent_input = json.dumps(agent_payload_input, ensure_ascii=False)
    else:
        agent_input = request.script or ""
        if request.voice_id:
            agent_input = (
                "VOICE_ID_OVERRIDE: "
                f"{request.voice_id}\nUse this voice_id for every generated segment.\n\n"
                f"{agent_input}"
            )

    agent_response = await longform_audio_agent.run(agent_input)
    try:
        agent_payload = json.loads(agent_response.output)
        plan = LongFormAudioPlan.model_validate(agent_payload)
    except (json.JSONDecodeError, ValidationError) as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=422,
            detail=f"Invalid long-form agent output: {exc}",
        ) from exc

    if request.voice_id:
        plan.voice_id = request.voice_id.strip()
        logger.info("Applied voice override from request: %s", plan.voice_id)

    if not plan.voice_id:
        raise HTTPException(
            status_code=422,
            detail="voice_id missing from request and agent output.",
        )

    scene_titles: dict[str, str | None] = {}
    if using_scene_mode and scene_definitions:
        if len(plan.segments) != len(scene_definitions):
            raise HTTPException(
                status_code=422,
                detail="Agent output does not align with provided scenes. Please retry.",
            )

        for scene_entry, segment in zip(scene_definitions, plan.segments, strict=True):
            segment.segment_id = scene_entry["scene_id"]
            segment.pause_after_seconds = scene_entry["pause_after_seconds"]
            segment.text = scene_entry["text"]
            segment.enforce_comma_pause = scene_entry.get("enforce_comma_pause", True)
            scene_titles[segment.segment_id] = scene_entry.get("title")

        plan.total_segments = len(plan.segments)

    logger.info(
        "Long-form plan validated: voice=%s segments=%d estimated_duration=%.1fs",
        plan.voice_id,
        len(plan.segments),
        plan.total_estimated_duration_seconds,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prefix = _sanitize_component(request.filename_prefix or "longform", "longform")
    generated_timestamp = datetime.utcnow().isoformat() + "Z"
    crossfade_ms = max(0, plan.stitching_instructions.crossfade_ms)

    any_scene_pause = any(segment.pause_after_seconds > 0 for segment in plan.segments)
    if any_scene_pause and crossfade_ms != 0:
        crossfade_ms = 0
        plan.stitching_instructions.crossfade_ms = 0
        logger.info("Disabled crossfade to honour explicit scene pauses.")

    segment_outputs: list[dict[str, Any]] = []
    manifest_segments: list[dict[str, Any]] = []
    segment_paths: list[Path] = []
    silence_workspace: Path | None = None

    api_headers = {
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }

    export_format = plan.stitching_instructions.output_format or "mp3"
    export_extension = export_format.lower().lstrip(".") or "mp3"

    for index, segment in enumerate(plan.segments):
        segment_text = (segment.text or "").strip()
        if not segment_text:
            raise HTTPException(
                status_code=422,
                detail=f"Segment '{segment.segment_id}' does not contain narratable text.",
            )

        clause_entries = (
            _split_text_into_clauses(segment_text)
            if getattr(segment, "enforce_comma_pause", True)
            else [(segment_text, False)]
        )
        if not clause_entries:
            clause_entries = [(segment_text, False)]

        segment_suffix = uuid4().hex[:8]
        segment_component = _sanitize_component(segment.segment_id, "segment")
        file_name = f"{prefix}_{segment_component}__{segment_suffix}.{export_extension}"
        file_path = OUTPUT_DIR / file_name

        clause_workspace = Path(tempfile.mkdtemp(prefix="longform_clause_"))
        clause_paths: list[Path] = []

        try:
            for clause_index, (clause_text, needs_pause) in enumerate(clause_entries):
                cleaned_clause = clause_text.strip()
                if not cleaned_clause:
                    continue

                request_payload = {
                    "inputs": [
                        {
                            "text": cleaned_clause,
                            "voice_id": plan.voice_id,
                        }
                    ]
                }

                api_response = requests.post(
                    settings.ELEVENLABS_URL,
                    json=request_payload,
                    headers=api_headers,
                )
                if api_response.status_code != 200:
                    raise HTTPException(
                        status_code=api_response.status_code,
                        detail=api_response.text,
                    )

                clause_file = (
                    clause_workspace
                    / f"{segment_component}_clause_{clause_index:03d}.{export_extension}"
                )
                with clause_file.open("wb") as audio_file:
                    audio_file.write(api_response.content)

                clause_paths.append(clause_file)

                if needs_pause and getattr(segment, "enforce_comma_pause", True):
                    silence_path = (
                        clause_workspace
                        / f"pause_{clause_index:03d}_{uuid4().hex[:8]}.{export_extension}"
                    )
                    _create_silence_segment(
                        PUNCTUATION_PAUSE_SECONDS,
                        silence_path,
                        export_extension,
                    )
                    clause_paths.append(silence_path)

            if not clause_paths:
                raise HTTPException(
                    status_code=422,
                    detail=f"No audio produced for segment '{segment.segment_id}'.",
                )

            if len(clause_paths) == 1:
                shutil.copyfile(clause_paths[0], file_path)
            else:
                _concat_audio_segments_ffmpeg(
                    segment_paths=clause_paths,
                    output_path=file_path,
                    output_extension=export_extension,
                    crossfade_seconds=0.0,
                )
        finally:
            shutil.rmtree(clause_workspace, ignore_errors=True)

        logger.debug(
            "Segment synthesised: id=%s emotion=%s pause=%.2fs",
            segment.segment_id,
            segment.emotion,
            segment.pause_after_seconds,
        )

        output_payload: dict[str, Any] = {
            "segment_id": segment.segment_id,
            "emotion": segment.emotion,
            "character_count": segment.character_count,
            "estimated_duration_seconds": segment.estimated_duration_seconds,
            "pause_after_seconds": segment.pause_after_seconds,
            "enforce_comma_pause": getattr(segment, "enforce_comma_pause", True),
            "file_name": file_name,
            "audio_file": f"/generated_audio/{file_name}",
        }
        if using_scene_mode:
            title_value = scene_titles.get(segment.segment_id)
            if title_value:
                output_payload["scene_title"] = title_value

        segment_outputs.append(output_payload)

        manifest_segment: dict[str, Any] = {
            "segment_id": segment.segment_id,
            "file_name": file_name,
            "emotion": segment.emotion,
            "character_count": segment.character_count,
            "estimated_duration_seconds": segment.estimated_duration_seconds,
            "pause_after_seconds": segment.pause_after_seconds,
            "enforce_comma_pause": getattr(segment, "enforce_comma_pause", True),
        }
        if using_scene_mode:
            title_value = scene_titles.get(segment.segment_id)
            if title_value:
                manifest_segment["scene_title"] = title_value

        manifest_segments.append(manifest_segment)

        segment_paths.append(file_path.resolve())

        if segment.pause_after_seconds > 0:
            if silence_workspace is None:
                silence_workspace = Path(tempfile.mkdtemp(prefix="longform_silence_"))
            silence_path = silence_workspace / f"pause_{index}_{uuid4().hex[:8]}.{export_extension}"
            _create_silence_segment(segment.pause_after_seconds, silence_path, export_extension)
            segment_paths.append(silence_path.resolve())

    if not segment_paths:
        raise HTTPException(status_code=422, detail="No segments generated by long-form agent.")

    combined_suffix = uuid4().hex[:8]
    combined_filename = f"{prefix}_combined__{combined_suffix}.{export_extension}"
    combined_path = OUTPUT_DIR / combined_filename

    try:
        _concat_audio_segments_ffmpeg(
            segment_paths=segment_paths,
            output_path=combined_path,
            output_extension=export_extension,
            crossfade_seconds=crossfade_ms / 1000.0,
        )
    finally:
        if silence_workspace:
            shutil.rmtree(silence_workspace, ignore_errors=True)

    if plan.stitching_instructions.normalize_volume:
        _normalize_audio_ffmpeg(combined_path, export_extension)
        logger.debug("Applied loudness normalisation to %s", combined_filename)

    manifest_payload = {
        "generated_at": generated_timestamp,
        "voice_id": plan.voice_id,
        "total_segments": plan.total_segments,
        "total_estimated_duration_seconds": plan.total_estimated_duration_seconds,
        "segments": manifest_segments,
        "combined": {
            "file_name": combined_filename,
            "audio_file": f"/generated_audio/{combined_filename}",
        },
        "stitching_instructions": plan.stitching_instructions.model_dump(),
        "input_mode": "scene_collection" if using_scene_mode else "script",
    }

    manifest_name = f"{LONGFORM_MANIFEST_PREFIX}_{uuid4().hex[:8]}.json"
    manifest_path = OUTPUT_DIR / manifest_name
    with manifest_path.open("w", encoding="utf-8") as manifest_file:
        json.dump(manifest_payload, manifest_file, indent=2)

    logger.info(
        "Long-form synthesis complete: file=%s segments=%d mode=%s",
        combined_filename,
        len(plan.segments),
        input_mode,
    )

    return {
        "status": "success",
        "generated_at": generated_timestamp,
        "voice_id": plan.voice_id,
        "input_mode": input_mode,
        "plan": plan.model_dump(),
        "segments": segment_outputs,
        "combined": {
            "file_name": combined_filename,
            "audio_file": f"/generated_audio/{combined_filename}",
        },
        "manifest_file": f"/generated_audio/{manifest_name}",
    }


def describe_audio_directory() -> dict[str, Any]:
    """Return metadata about locally cached audio assets."""

    logger.info("Enumerating generated audio directory contents")
    files: list[dict[str, Any]] = []
    for path in list_generated_audio_files():
        stats = path.stat()
        files.append(
            {
                "file_name": path.name,
                "relative_path": f"{OUTPUT_DIR.name}/{path.name}",
                "size_bytes": stats.st_size,
                "size_readable": format_file_size(stats.st_size),
                "modified_at": datetime.utcfromtimestamp(stats.st_mtime).isoformat() + "Z",
                "download_url": f"/generated_audio/{path.name}",
            }
        )

    longform_manifests = sorted(
        manifest_path.name
        for manifest_path in OUTPUT_DIR.glob(f"{LONGFORM_MANIFEST_PREFIX}_*.json")
    )

    payload = {
        "count": len(files),
        "files": files,
        "manifest_present": AUDIO_MANIFEST_PATH.exists(),
        "asset_cache_present": AUDIO_CACHE_PATH.exists(),
        "longform_manifest_count": len(longform_manifests),
        "longform_manifests": longform_manifests,
    }

    logger.info(
        "Enumerated generated audio directory (file_count=%d longform_manifests=%d)",
        payload["count"],
        payload["longform_manifest_count"],
    )
    return payload


def clear_audio_storage() -> dict[str, Any]:
    """Delete generated audio outputs and supporting metadata from disk."""

    logger.info("Clearing generated audio storage")
    deleted_files: list[str] = []
    errors: list[str] = []

    for path in list_generated_audio_files():
        try:
            path.unlink()
            deleted_files.append(path.name)
        except OSError as exc:  # pragma: no cover - filesystem specific
            errors.append(f"Failed to delete {path.name}: {exc}")
            logger.warning("Failed to delete audio file %s: %s", path.name, exc)

    removed_metadata: list[str] = []
    for metadata_file in [AUDIO_MANIFEST_PATH, AUDIO_CACHE_PATH]:
        if metadata_file.exists():
            try:
                metadata_file.unlink()
                removed_metadata.append(metadata_file.name)
            except OSError as exc:  # pragma: no cover - filesystem specific
                errors.append(f"Failed to delete {metadata_file.name}: {exc}")
                logger.warning("Failed to delete metadata file %s: %s", metadata_file.name, exc)

    for manifest_file in OUTPUT_DIR.glob(f"{LONGFORM_MANIFEST_PREFIX}_*.json"):
        try:
            manifest_file.unlink()
            removed_metadata.append(manifest_file.name)
        except OSError as exc:  # pragma: no cover - filesystem specific
            errors.append(f"Failed to delete {manifest_file.name}: {exc}")
            logger.warning("Failed to delete longform manifest %s: %s", manifest_file.name, exc)

    if errors:
        logger.error("Errors encountered while clearing audio storage: %s", "; ".join(errors))
        raise HTTPException(status_code=500, detail="; ".join(errors))

    logger.info(
        "Cleared generated audio storage (deleted_files=%d removed_metadata=%d)",
        len(deleted_files),
        len(removed_metadata),
    )
    return {
        "status": "success",
        "deleted": len(deleted_files),
        "deleted_files": deleted_files,
        "removed_metadata": removed_metadata,
    }
