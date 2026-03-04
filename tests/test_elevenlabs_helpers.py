"""Tests for pure helper functions in controllers.elevenlabs."""

import pytest

# These functions are pure and don't require external services.
from controllers.elevenlabs import (
    _default_pause_for_punctuation,
    _sanitize_component,
    _sanitize_scene_text,
    _split_text_into_clauses,
    format_file_size,
)


class TestSanitizeComponent:
    def test_alphanumeric_passthrough(self):
        assert _sanitize_component("scene_1", "fallback") == "scene_1"

    def test_strips_special_characters(self):
        assert _sanitize_component("hello world!", "fb") == "hello_world_"

    def test_empty_string_returns_fallback(self):
        assert _sanitize_component("", "default") == "default"

    def test_only_special_chars_returns_fallback(self):
        assert _sanitize_component("...", "fb") == "fb"

    def test_strips_leading_trailing_dots(self):
        assert _sanitize_component(".abc.", "fb") == "abc"


class TestSanitizeSceneText:
    def test_removes_meta_lines(self):
        text = "Meta: some info\nActual narration text."
        assert _sanitize_scene_text(text) == "Actual narration text."

    def test_preserves_normal_text(self):
        text = "Hello world.\nSecond line."
        assert _sanitize_scene_text(text) == "Hello world.\nSecond line."

    def test_empty_after_stripping(self):
        assert _sanitize_scene_text("Meta: only meta") == ""


class TestSplitTextIntoClauses:
    def test_splits_on_period(self):
        result = _split_text_into_clauses("Hello. World.")
        assert len(result) == 2
        assert result[0] == ("Hello.", ".")
        assert result[1] == ("World.", ".")

    def test_splits_on_hindi_punctuation(self):
        result = _split_text_into_clauses("नमस्ते। दुनिया।")
        assert len(result) == 2

    def test_trailing_text_without_punctuation(self):
        result = _split_text_into_clauses("Hello. World")
        assert len(result) == 2
        assert result[1] == ("World", None)

    def test_empty_string(self):
        assert _split_text_into_clauses("") == []

    def test_comma_splitting(self):
        result = _split_text_into_clauses("First, second.")
        assert len(result) == 2
        assert result[0][1] == ","
        assert result[1][1] == "."


class TestDefaultPauseForPunctuation:
    def test_period_pause(self):
        assert _default_pause_for_punctuation(".") == 1.5

    def test_comma_pause(self):
        assert _default_pause_for_punctuation(",") == 0.5

    def test_none_returns_zero(self):
        assert _default_pause_for_punctuation(None) == 0.0

    def test_unknown_falls_back_to_period(self):
        assert _default_pause_for_punctuation(";") == 1.5


class TestFormatFileSize:
    def test_bytes(self):
        assert format_file_size(500) == "500 B"

    def test_kilobytes(self):
        result = format_file_size(2048)
        assert "KB" in result

    def test_megabytes(self):
        result = format_file_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_zero_bytes(self):
        assert format_file_size(0) == "0 B"
