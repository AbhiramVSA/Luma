from pydantic import BaseModel, Field, model_validator


class LongFormSceneInput(BaseModel):
    scene_id: str | None = None
    title: str | None = None
    text: str = Field(..., min_length=10)
    pause_after_seconds: float = Field(default=0.0, ge=0.0)
    enforce_comma_pause: bool = Field(
        default=True,
        description="If true, apply 1.5s pauses after punctuation",
    )

    @model_validator(mode="after")
    def _normalize_scene(self) -> "LongFormSceneInput":
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("text cannot be empty")
        if self.scene_id is not None:
            scene = self.scene_id.strip()
            self.scene_id = scene or None
        if self.title is not None:
            title = self.title.strip()
            self.title = title or None
        return self


class DialogueLine(BaseModel):
    text: str
    character: str
    emotion: str | None = None
    voice_id: str


class Scene(BaseModel):
    scene_id: str
    title: str
    dialogues: list[DialogueLine]


class ScriptRequest(BaseModel):
    scenes: list[Scene]


class StitchingInstructions(BaseModel):
    crossfade_ms: int = Field(..., ge=0)
    normalize_volume: bool
    output_format: str = Field(..., description="Audio container for the stitched export")


class LongFormSegment(BaseModel):
    segment_id: str
    text: str
    emotion: str
    character_count: int = Field(..., ge=1)
    estimated_duration_seconds: float = Field(..., ge=0.0)
    pause_after_seconds: float = Field(default=0.0, ge=0.0)
    enforce_comma_pause: bool = Field(
        default=True,
        description="If true, insert SSML pauses after punctuation.",
    )

    @model_validator(mode="after")
    def _validate_fields(self) -> "LongFormSegment":
        self.segment_id = self.segment_id.strip()
        self.text = self.text.strip()
        self.emotion = self.emotion.strip()
        if not self.segment_id:
            raise ValueError("segment_id cannot be empty")
        if not self.text:
            raise ValueError("text cannot be empty")
        if not self.emotion:
            raise ValueError("emotion cannot be empty")
        return self


class LongFormAudioPlan(BaseModel):
    voice_id: str
    segments: list[LongFormSegment]
    total_segments: int = Field(..., ge=1)
    total_estimated_duration_seconds: float = Field(..., ge=0.0)
    stitching_instructions: StitchingInstructions

    @model_validator(mode="after")
    def _validate_plan(self) -> "LongFormAudioPlan":
        self.voice_id = self.voice_id.strip()
        if not self.voice_id:
            raise ValueError("voice_id cannot be empty")
        if not self.segments:
            raise ValueError("segments cannot be empty")
        if self.total_segments != len(self.segments):
            self.total_segments = len(self.segments)
        return self


class LongFormAudioRequest(BaseModel):
    script: str | None = Field(
        default=None,
        description="Long-form narration script (legacy mode; prefer structured scenes)",
    )
    scenes: list[LongFormSceneInput] | None = Field(
        default=None,
        description="Ordered list of narration scenes with optional pauses",
    )
    voice_id: str | None = Field(
        default=None,
        description="Optional override for the generated voice id",
    )
    filename_prefix: str | None = Field(
        default=None,
        description="Optional prefix applied to generated audio filenames",
    )

    @model_validator(mode="after")
    def _normalize_fields(self) -> "LongFormAudioRequest":
        if self.script is not None:
            script = self.script.strip()
            self.script = script or None
        if self.scenes is not None and len(self.scenes) == 0:
            raise ValueError("scenes cannot be empty")
        if self.script is None and not self.scenes:
            raise ValueError("Either script or scenes must be provided")
        if self.voice_id is not None:
            voice = self.voice_id.strip()
            self.voice_id = voice or None
        if self.filename_prefix is not None:
            prefix = self.filename_prefix.strip()
            self.filename_prefix = prefix or None
        return self
