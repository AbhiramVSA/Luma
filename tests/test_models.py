"""Tests for Pydantic model validation."""

import pytest
from pydantic import ValidationError

from models.auth import LoginRequest, TokenResponse
from models.elevenlabs import LongFormAudioRequest, LongFormSceneInput
from models.freepik import FreepikPromptBundle
from models.heygen import (
    HeyGenAvatarAgentOutput,
    HeyGenAvatarVideoRequest,
    HeyGenSceneConfig,
    HeyGenVideoRequest,
)


class TestLoginRequest:
    def test_valid_login(self):
        req = LoginRequest(email="test@example.com", password="secure123")
        assert req.email == "test@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="not-an-email", password="secure123")

    def test_short_password_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="test@example.com", password="short")


class TestTokenResponse:
    def test_defaults(self):
        resp = TokenResponse(access_token="abc123")
        assert resp.token_type == "bearer"


class TestLongFormSceneInput:
    def test_valid_scene(self):
        scene = LongFormSceneInput(text="This is narration text for the scene.")
        assert scene.text == "This is narration text for the scene."

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            LongFormSceneInput(text="")

    def test_short_text_rejected(self):
        with pytest.raises(ValidationError):
            LongFormSceneInput(text="short")

    def test_scene_id_stripped(self):
        scene = LongFormSceneInput(scene_id="  intro  ", text="Valid scene text here.")
        assert scene.scene_id == "intro"


class TestLongFormAudioRequest:
    def test_requires_script_or_scenes(self):
        with pytest.raises(ValidationError):
            LongFormAudioRequest()

    def test_script_mode(self):
        req = LongFormAudioRequest(script="Some narration script text here.")
        assert req.script is not None

    def test_empty_scenes_rejected(self):
        with pytest.raises(ValidationError):
            LongFormAudioRequest(scenes=[])


class TestHeyGenVideoRequest:
    def test_defaults(self):
        req = HeyGenVideoRequest(script="Test script for scene generation")
        assert req.force_upload is False


class TestHeyGenSceneConfig:
    def test_default_background(self):
        config = HeyGenSceneConfig(scene_id="scene_1", talking_photo_id="photo_1")
        assert config.background is not None
        assert config.background.type == "color"
        assert config.background.value == "#FFFFFF"


class TestHeyGenAvatarVideoRequest:
    def test_video_brief_defaults_to_script(self):
        req = HeyGenAvatarVideoRequest(
            image_asset_id="img_1",
            script="This is a test narration script",
        )
        assert req.video_brief == req.script

    def test_short_script_rejected(self):
        with pytest.raises(ValidationError):
            HeyGenAvatarVideoRequest(image_asset_id="img_1", script="short")


class TestHeyGenAvatarAgentOutput:
    def test_valid_output(self):
        out = HeyGenAvatarAgentOutput(
            video_title="Test Video",
            script="This is a test narration script that is long enough",
            voice_id="ryan_smith",
            custom_motion_prompt="Natural gestures and warm eye contact",
        )
        assert out.video_orientation == "portrait"
        assert out.enhance_custom_motion_prompt is True

    def test_empty_title_rejected(self):
        with pytest.raises(ValidationError):
            HeyGenAvatarAgentOutput(
                video_title="   ",
                script="This is a test narration script that is long enough",
                voice_id="ryan_smith",
                custom_motion_prompt="Natural gestures",
            )


class TestFreepikPromptBundle:
    def test_valid_bundle(self):
        bundle = FreepikPromptBundle(prompt="Cinematic sunset scene with warm lighting")
        assert bundle.cfg_scale == 0.5
        assert bundle.duration == "5"

    def test_empty_prompt_rejected(self):
        with pytest.raises(ValidationError):
            FreepikPromptBundle(prompt="  ")
