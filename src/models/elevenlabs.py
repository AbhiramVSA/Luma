from pydantic import BaseModel


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
