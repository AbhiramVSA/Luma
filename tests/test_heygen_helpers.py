"""Tests for pure helper functions in controllers.heygen."""

from controllers.heygen import (
    _build_asset_lookup,
    _normalize_talking_photo_id,
    _resolve_asset_id,
    resolve_avatar_audio_asset,
)


class TestBuildAssetLookup:
    def test_basic_lookup(self):
        assets = [
            {"file_name": "scene_1__abc123.mp3", "asset_id": "id1"},
            {"file_name": "scene_2__def456.mp3", "asset_id": "id2"},
        ]
        lookup = _build_asset_lookup(assets)
        assert lookup.get("scene_1") == "id1"
        assert lookup.get("scene_2") == "id2"

    def test_ignores_missing_asset_id(self):
        assets = [{"file_name": "scene_1.mp3"}]
        lookup = _build_asset_lookup(assets)
        assert len(lookup) == 0

    def test_scene_id_from_metadata(self):
        assets = [
            {"file_name": "audio.mp3", "asset_id": "id1", "scene_id": "intro"},
        ]
        lookup = _build_asset_lookup(assets)
        assert lookup.get("intro") == "id1"

    def test_empty_assets(self):
        assert _build_asset_lookup([]) == {}


class TestResolveAssetId:
    def test_explicit_id_takes_priority(self):
        result = _resolve_asset_id("scene_1", "explicit_id", {"scene_1": "lookup_id"})
        assert result == "explicit_id"

    def test_lookup_by_scene_id(self):
        result = _resolve_asset_id("scene_1", None, {"scene_1": "lookup_id"})
        assert result == "lookup_id"

    def test_numeric_scene_variants(self):
        result = _resolve_asset_id("scene-2", None, {"scene_2": "id2"})
        assert result == "id2"

    def test_not_found_returns_none(self):
        result = _resolve_asset_id("unknown", None, {"scene_1": "id1"})
        assert result is None


class TestNormalizeTalkingPhotoId:
    def test_valid_id_passthrough(self):
        assert _normalize_talking_photo_id("my_photo_id") == "my_photo_id"

    def test_strips_whitespace(self):
        assert _normalize_talking_photo_id("  my_id  ") == "my_id"

    def test_none_returns_default(self):
        result = _normalize_talking_photo_id(None)
        assert result  # Should return the default, not empty

    def test_empty_string_returns_default(self):
        result = _normalize_talking_photo_id("")
        assert result  # Should return the default


class TestResolveAvatarAudioAsset:
    def test_matches_script_reference(self):
        assets = [{"asset_id": "id1", "scene_id": "scene_1", "file_name": "scene_1.mp3"}]
        lookup = {"scene_1": "id1"}
        asset_id, alias = resolve_avatar_audio_asset("Scene_1 intro text", assets, lookup)
        assert asset_id == "id1"

    def test_falls_back_to_first_asset(self):
        assets = [{"asset_id": "id1", "scene_id": "intro"}]
        lookup = {"intro": "id1"}
        asset_id, alias = resolve_avatar_audio_asset("unrelated text", assets, lookup)
        assert asset_id == "id1"

    def test_empty_assets_returns_none(self):
        asset_id, alias = resolve_avatar_audio_asset("text", [], {})
        assert asset_id is None
        assert alias is None
