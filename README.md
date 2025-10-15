# InnerBhakti Video Generation Automation

> Automated production pipeline for generating expressive audio content from scripts using AI-powered dialogue enhancement and ElevenLabs text-to-speech.

## 🎯 Overview

This project automates the video production pipeline by transforming written scripts into production-ready assets:

- **AI-Enhanced Dialogues**: Automatically analyzes scripts and adds expressive audio tags based on emotional context
- **Multi-Scene Processing**: Processes complete scripts with multiple scenes in a single API call
- **ElevenLabs Integration**: Generates high-quality voice-over audio for each scene
- **Organized Output**: Saves audio files in structured folders for easy management

---

## ✨ Features

### Currently Implemented
✅ **Script Parsing & AI Enhancement**
- Parses structured scene-based scripts
- Extracts dialogue lines with context-aware audio tag suggestions
- Uses GPT-5 via pydantic-ai for intelligent dialogue enhancement

✅ **ElevenLabs Audio Generation**
- Converts enhanced dialogues to high-quality speech
- Supports multiple voices and characters
- Generates separate audio files per scene

✅ **REST API**
- FastAPI-based REST endpoints
- Automatic API documentation (Swagger/ReDoc)
- Input validation with Pydantic models

✅ **Code Quality**
- Ruff linter and formatter integration
- Type hints throughout codebase
- Modular architecture with clear separation of concerns

### Planned Features
🔜 **HeyGen Video Integration**
- Generate avatar videos synchronized with audio
- Support for multiple avatar styles

🔜 **B-roll Generation**
- AI-powered b-roll clip selection
- Scene-appropriate visual content

🔜 **Google Drive Integration**
- Automatic upload of generated assets
- Organized folder structure

---

## 🚀 Getting Started

### Prerequisites
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager
- OpenAI API key (for GPT-5)
- ElevenLabs API key

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AbhiramVSA/innerbhakti-video-generation-automation.git
   cd innerbhakti-video-generation-automation
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
   ELEVENLABS_URL=https://api.elevenlabs.io/v1/text-to-dialogue
   ```

### Running the API

```bash
# Activate virtual environment
uv run src/main.py
```

The server will start at `http://localhost:8002`

**API Documentation:**
- Swagger UI: http://localhost:8002/docs
- ReDoc: http://localhost:8002/redoc

---

## 📖 API Usage

### Generate Audio from Script

**Endpoint:** `POST /api/v1/elevenlabs/generate-audio`

**Request Body:**
```json
{
  "script": "[Scene 1 – HOOK 1 | 0–5s]\n\nVisual: Woman sitting on couch\nDialogue (VO): \"Main aur mere husband jab bhi baat karte thay hamara jhagda ho jaata tha!\"\n\n[Scene 2 – HOOK 2 | 5–10s]\n..."
}
```

**Response:**
```json
{
  "status": "success",
  "outputs": [
    {
      "scene_id": "scene_1",
      "audio_file": "generated_audio/scene_1.mp3"
    },
    {
      "scene_id": "scene_2",
      "audio_file": "generated_audio/scene_2.mp3"
    }
  ]
}
```

### Script Format

The API expects scripts in the following format:

```
[Scene X – TITLE | timing]

Visual: Description of visual elements
Dialogue (VO): "The actual dialogue text"
SFX: Sound effects description
VFX: Visual effects description
Transition: Transition description
```

**Example:**
```
[Scene 1 – HOOK 1 | 0–5s]

Visual: Woman (early 30s) sitting on a cozy couch, facing the camera.
Dialogue (VO): "Main aur mere husband jab bhi baat karte thay hamara jhagda ho jaata tha!"
SFX: Light, tense instrumental music.
```

---

## 🏗️ Project Structure

```
innerbhakti-video-generation-automation/
├── src/
│   ├── api/
│   │   └── v1/
│   │       ├── api.py              # Main API router
│   │       └── routers/
│   │           └── elevenlabs_gen.py  # ElevenLabs endpoints
│   ├── config/
│   │   └── config.py               # Configuration and settings
│   ├── controllers/
│   │   └── generate_audio.py       # Audio generation logic
│   ├── models/
│   │   └── elevenlabs.py          # Pydantic models
│   ├── prompts/
│   │   └── elevenlabs_prompt.md   # AI agent system prompts
│   ├── utils/
│   │   └── agents.py              # AI agent configurations
│   └── main.py                    # FastAPI application entry
├── generated_audio/               # Output folder for audio files
├── pyproject.toml                # Project dependencies
├── .env                          # Environment variables (create this)
└── README.md
```

---

## 🛠️ Development

### Code Quality

Run linting and formatting:
```bash
# Check for issues
uv run ruff check src

# Auto-fix issues
uv run ruff check src --fix

# Format code
uv run ruff format src
```

### Testing

Run the test script:
```bash
python src/test.py
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-5 | Yes |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Yes |
| `ELEVENLABS_URL` | ElevenLabs API endpoint | Yes (default provided) |

### Voice Configuration

Update voice IDs in the AI agent prompt (`src/prompts/elevenlabs_prompt.md`) or pass custom voice IDs in the script using:

```
Dialogue (VO, voice:YOUR_VOICE_ID): "Your dialogue here"
```

---

## 📝 How It Works

1. **Script Input**: User provides a structured script via API
2. **AI Processing**: GPT-5 agent parses the script and:
   - Extracts dialogue lines from each scene
   - Analyzes emotional context and scene descriptions
   - Adds expressive audio tags (e.g., `[frustrated]`, `[hopeful]`)
   - Generates structured JSON output
3. **Validation**: Output is validated against Pydantic models
4. **Audio Generation**: For each scene:
   - Sends enhanced dialogues to ElevenLabs API
   - Receives audio stream
   - Saves to `generated_audio/scene_X.mp3`
5. **Response**: Returns list of generated audio file paths

---

## 🤝 Contributing

This project is under active development. Contributions, ideas, and feedback are welcome!

---

## 📄 License

[Add your license here]

---

## 🔗 Links

- [ElevenLabs Documentation](https://elevenlabs.io/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic AI Documentation](https://ai.pydantic.dev/)

---

**Built with ❤️ for InnerBhakti**
