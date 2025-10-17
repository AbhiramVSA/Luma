# InnerBhakti Video Generation Automation

> Enterprise-grade automation platform for AI-powered video content production. Transform scripts into production-ready video content with talking avatars, expressive audio, and intelligent scene management.

## 🎯 Overview

This platform delivers an end-to-end video generation pipeline for InnerBhakti, automating the entire production workflow from script to finished video:

- **AI-Powered Scene Analysis**: GPT-powered agents parse scripts, extract dialogue, and intelligently map assets
- **Professional Voice Synthesis**: ElevenLabs text-to-speech generates natural, expressive audio with multi-character support
- **Automated Video Production**: HeyGen talking photo integration produces synchronized video content with customizable avatars
- **Intelligent Asset Management**: UUID-based audio file naming ensures unique identifiers while maintaining scene relationships
- **Production-Grade API**: RESTful architecture with comprehensive validation, error handling, and status tracking

---

## ✨ Features

### Core Capabilities

#### 🎬 Complete Video Generation Pipeline
- **End-to-End Automation**: Script input → AI processing → audio synthesis → video rendering → status tracking
- **HeyGen Talking Photo Integration**: Generate videos with AI avatars (720×1280 portrait format optimized for social media)
- **Real-Time Status Polling**: Automated job monitoring with configurable retry logic (up to 2 minutes polling by default)
- **Video URL Delivery**: Direct access to completed videos with thumbnail previews

#### 🎙️ Advanced Audio Processing
- **Unique Audio Identifiers**: UUID-suffixed filenames (`scene_1__a1b2c3d4.mp3`) prevent collisions across regenerations
- **Scene Manifest System**: JSON manifest (`scene_audio_map.json`) tracks scene-to-file relationships
- **Smart Asset Caching**: Avoid redundant uploads to HeyGen with persistent asset cache
- **Multi-Format Support**: MP3, WAV, M4A, AAC audio formats

#### 🤖 Intelligent AI Agents
- **Script Analysis Agent**: Extracts scene structure, dialogue, and character information
- **HeyGen Configuration Agent**: Maps audio assets to scenes with flexible pattern matching
- **Context-Aware Processing**: Handles scene identifiers with underscores, hyphens, or numeric patterns

#### 🔧 Production-Ready Architecture
- **FastAPI Framework**: High-performance async API with automatic OpenAPI documentation
- **Pydantic Validation**: Type-safe request/response models with comprehensive error messages
- **Modular Design**: Clean separation between routes, controllers, models, and utilities
- **Environment-Based Config**: Secure credential management via `.env` files

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.13+**
- **[uv](https://github.com/astral-sh/uv)** - Fast Python package installer and resolver
- **API Keys**:
  - OpenAI API key (GPT-4 or GPT-5 for AI agents)
  - ElevenLabs API key (text-to-speech synthesis)
  - HeyGen API key (video generation with talking photos)

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

3. **Configure environment variables**
   
   Copy the example environment file and add your credentials:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your API keys:
   ```env
   OPENAI_API_KEY=sk-proj-...
   ELEVENLABS_API_KEY=...
   ELEVENLABS_URL=https://api.elevenlabs.io/v1/text-to-dialogue
   HEYGEN_API_KEY=...
   HEYGEN_DEFAULT_TALKING_PHOTO_ID=Monica_inSleeveless_20220819
   ```

### Running the Server

Start the FastAPI development server:

```bash
uv run fastapi dev src/main.py
```

The API will be available at `http://127.0.0.1:8002`

**Interactive Documentation:**
- **Swagger UI**: http://127.0.0.1:8002/docs (interactive API testing)
- **ReDoc**: http://127.0.0.1:8002/redoc (clean reference documentation)

---

## 📖 API Reference

### 1. Complete Video Generation

**Endpoint:** `POST /api/v1/heygen/generate-video`

Generate complete videos from scripts with audio synthesis, avatar configuration, and HeyGen rendering.

#### Request Schema

```json
{
  "script": "string (required)",
  "force_upload": "boolean (optional, default: false)"
}
```

#### Script Format

```
[Scene 1 – Introduction]
Visual: Professional setting
Dialogue (VO): "Welcome to our platform"
Talking photo: Monica_inSleeveless_20220819
Scene 1 heygen id: "optional_existing_asset_id"

[Scene 2 – Main Content]
Dialogue (VO): "Here's what we offer"
```

**Key Points:**
- Scene identifiers must follow `[Scene X ...]` format
- `Talking photo:` line sets the HeyGen avatar (optional, falls back to `HEYGEN_DEFAULT_TALKING_PHOTO_ID`)
- `Scene X heygen id:` references existing audio assets (optional, auto-matched from generated audio)
- `force_upload: true` bypasses cache and re-uploads all audio files

#### Response Schema

```json
{
  "status": "success | partial | failed",
  "results": [
    {
      "scene_id": "scene_1",
      "status": "completed | processing | submitted | failed",
      "video_id": "abc123def456",
      "video_url": "https://...",
      "thumbnail_url": "https://...",
      "message": "Video rendering completed.",
      "request_payload": { ... },
      "status_detail": { ... }
    }
  ],
  "missing_assets": [],
  "errors": []
}
```

**Status Codes:**
- `200 OK`: Request processed (check `status` field for success/partial/failed)
- `400 Bad Request`: Missing API keys or invalid scene identifiers
- `422 Unprocessable Entity`: Invalid script format or agent output
- `500 Internal Server Error`: Unexpected failures

**Processing Time:** 2-5 minutes per scene (includes audio generation, upload, video rendering, and polling)

---

### 2. Audio Generation Only

**Endpoint:** `POST /api/v1/elevenlabs/generate-audio`

Generate audio files without video rendering.

#### Request

```json
{
  "script": "[Scene 1]\nDialogue (VO): \"Hello world\"\n\n[Scene 2]\nDialogue (VO): \"Welcome\""
}
```

#### Response

```json
{
  "status": "success",
  "outputs": [
    {
      "scene_id": "scene_1",
      "file_name": "scene_1__a1b2c3d4.mp3",
      "audio_file": "generated_audio/scene_1__a1b2c3d4.mp3"
    }
  ],
  "manifest_file": "generated_audio/scene_audio_map.json"
}
```

**Processing Time:** 10-30 seconds per scene

---

### 3. Upload Audio Assets

**Endpoint:** `POST /api/v1/heygen/upload-audio-assets`

Manually upload audio files to HeyGen without generating video.

#### Request

```json
{
  "force": false
}
```

#### Response

```json
{
  "status": "success",
  "count": 5,
  "assets": [
    {
      "file_name": "scene_1__a1b2c3d4.mp3",
      "asset_id": "f0eb18273553456a8b22c6c767bec4a2",
      "scene_id": "scene_1",
      "file_type": "audio",
      "folder_id": "..."
    }
  ],
  "cache_file": "generated_audio/heygen_assets.json",
  "scene_manifest": "generated_audio/scene_audio_map.json"
}
```

---

## 🏗️ Architecture

### Project Structure

```
innerbhakti-video-generation-automation/
├── src/
│   ├── api/v1/
│   │   ├── api.py                    # Main API aggregator
│   │   └── routers/
│   │       ├── elevenlabs_route.py   # Audio generation endpoints
│   │       ├── heygen.py             # Video generation endpoints
│   │       └── heygen_route.py       # Compatibility layer
│   ├── config/
│   │   └── config.py                 # Settings management (Pydantic)
│   ├── controllers/
│   │   └── generate_video.py        # HeyGen upload & asset orchestration
│   ├── models/
│   │   ├── elevenlabs.py            # Audio request/response schemas
│   │   └── heygen.py                # Video request/response schemas
│   ├── prompts/
│   │   ├── elevenlabs_prompt.md     # Audio agent instructions
│   │   └── heygen_prompt.md         # Video agent instructions
│   ├── utils/
│   │   └── agents.py                # Pydantic AI agent configurations
│   └── main.py                      # FastAPI app entry point
├── generated_audio/                  # Audio/manifest storage
│   ├── scene_audio_map.json        # Scene → filename manifest
│   └── heygen_assets.json          # Asset upload cache
├── .env                             # Environment variables (gitignored)
├── .env.example                     # Template for credentials
├── pyproject.toml                   # Project metadata & dependencies
└── README.md
```

### Data Flow

```
┌─────────────┐
│   Script    │
│   Input     │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Audio Agent (GPT)  │
│  Dialogue Extraction│
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  ElevenLabs API     │
│  Audio Synthesis    │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  UUID Audio Files   │
│  + Scene Manifest   │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  HeyGen Agent (GPT) │
│  Asset Mapping      │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  HeyGen Upload API  │
│  Asset Registration │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  HeyGen Video API   │
│  Job Submission     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Status Polling     │
│  (5s × 24 attempts) │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Video URLs         │
│  + Thumbnails       │
└─────────────────────┘
```

### Key Design Patterns

- **Async/Await**: Non-blocking I/O for external API calls
- **Dependency Injection**: Settings injected via Pydantic BaseSettings
- **Repository Pattern**: Asset cache and manifest persistence
- **Agent Pattern**: GPT-powered parsing with structured outputs
- **Retry with Backoff**: Polling loop for video completion

---

## 🛠️ Development Guide

### Code Quality Standards

This project follows strict quality standards enforced through automated tooling:

```bash
# Lint the codebase
uv run ruff check src

# Auto-fix linting issues
uv run ruff check src --fix

# Format code consistently
uv run ruff format src

# Compile all Python modules (syntax check)
uv run python -m compileall src
```

**Ruff Configuration** (see `pyproject.toml`):
- Line length: 120 characters
- Python 3.13+ syntax
- Import sorting and formatting
- Type hint validation

---

### Testing

#### Audio Generation
```bash
# Test ElevenLabs audio synthesis
uv run python src/test.py
```

#### Video Generation
```bash
# Quick avatar extraction test (~10 seconds)
uv run python test_heygen.py avatar

# Full video workflow test (5-10 minutes)
uv run python test_heygen.py video

# Check status of a specific video
uv run python test_heygen.py status <video_id>
```

---

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `OPENAI_API_KEY` | OpenAI API key for GPT agents | ✅ Yes | - |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | ✅ Yes | - |
| `ELEVENLABS_URL` | ElevenLabs dialogue endpoint | ✅ Yes | `https://api.elevenlabs.io/v1/text-to-dialogue` |
| `HEYGEN_API_KEY` | HeyGen video generation API key | ✅ Yes (for video) | - |
| `HEYGEN_DEFAULT_TALKING_PHOTO_ID` | Default avatar when script omits one | ⚠️ Recommended | `Monica_inSleeveless_20220819` |
| `GROQ_API_KEY` | Groq LLM API key (alternative to OpenAI) | ❌ Optional | - |
| `FREEPIK_API_KEY` | Freepik image generation (future use) | ❌ Optional | - |

---

### Adding New Features

#### 1. Define Pydantic Models
```python
# src/models/your_service.py
from pydantic import BaseModel, Field

class YourRequest(BaseModel):
    input_data: str = Field(description="Your input")

class YourResponse(BaseModel):
    output_data: str
```

#### 2. Create Controller Logic
```python
# src/controllers/your_logic.py
async def process_request(data: str) -> dict:
    # Business logic here
    return {"result": "processed"}
```

#### 3. Add Router Endpoint
```python
# src/api/v1/routers/your_route.py
from fastapi import APIRouter
from models.your_service import YourRequest, YourResponse

router = APIRouter()

@router.post("/your-endpoint", response_model=YourResponse)
async def your_endpoint(request: YourRequest) -> YourResponse:
    result = await process_request(request.input_data)
    return YourResponse(output_data=result["result"])
```

#### 4. Register Router
```python
# src/api/v1/api.py
from .routers import your_route

api_router.include_router(
    your_route.router, prefix="/your-service", tags=["your-service"]
)
```

---

## � Security & Best Practices

### API Key Management
- Never commit `.env` files to version control (included in `.gitignore`)
- Use environment-specific keys for development/staging/production
- Rotate API keys periodically
- Restrict HeyGen folder permissions via API settings

### Error Handling
- All endpoints return structured error responses with HTTP status codes
- Agent failures surface detailed validation errors (422)
- External API errors propagate with original status codes
- Asset lookup failures produce actionable `missing_assets` lists

### Performance Optimization
- **Asset Caching**: Avoid redundant HeyGen uploads by leveraging `heygen_assets.json`
- **Batch Processing**: Generate multiple scenes in parallel (ElevenLabs supports concurrent requests)
- **Polling Efficiency**: Configurable `STATUS_POLL_INTERVAL_SECONDS` (default 5s) and `STATUS_MAX_ATTEMPTS` (default 24)
- **UUID Filenames**: Prevent race conditions when regenerating scenes

---

## 📊 Monitoring & Debugging

### Logs
The FastAPI server outputs structured logs for all requests:
```
INFO:     127.0.0.1:52341 - "POST /api/v1/heygen/generate-video HTTP/1.1" 200 OK
```

Enable debug mode in `src/main.py`:
```python
uvicorn.run(app, host="127.0.0.1", port=8002, log_level="debug")
```

### Common Issues

**Audio Generation Failures**
- **Symptom**: `422 Unprocessable Entity` from audio endpoint
- **Cause**: Script format doesn't match expected structure
- **Fix**: Ensure scenes follow `[Scene X ...]` format with `Dialogue (VO):` lines

**Missing Assets**
- **Symptom**: `missing_assets: ["scene_2"]` in video response
- **Cause**: No audio file found matching scene identifier
- **Fix**: Run `/api/v1/elevenlabs/generate-audio` first, or verify manifest file

**HeyGen Upload Errors**
- **Symptom**: `HeyGen upload failed for scene_1__abc.mp3: 401 Unauthorized`
- **Cause**: Invalid `HEYGEN_API_KEY`
- **Fix**: Verify API key in `.env` and check HeyGen dashboard

**Video Polling Timeout**
- **Symptom**: `status: "processing"` after 2 minutes
- **Cause**: Video rendering exceeds polling window
- **Fix**: Increase `STATUS_MAX_ATTEMPTS` in `src/api/v1/routers/heygen.py`

---

## 🚢 Production Deployment

### Docker Deployment (Recommended)

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY src/ ./src/

# Expose API port
EXPOSE 8002

# Run with production ASGI server
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

### Environment Setup
```bash
docker build -t innerbhakti-video-gen .
docker run -d \
  -p 8002:8002 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e ELEVENLABS_API_KEY=$ELEVENLABS_API_KEY \
  -e HEYGEN_API_KEY=$HEYGEN_API_KEY \
  -v $(pwd)/generated_audio:/app/generated_audio \
  innerbhakti-video-gen
```

### Health Check Endpoint
Add to `src/main.py`:
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
```

---

## 🤝 Contributing

This project is developed for **InnerBhakti** internal use. For feature requests or bug reports:

1. Open an issue with detailed reproduction steps
2. Follow existing code style (Ruff-compliant)
3. Add tests for new endpoints
4. Update this README with new features

---

## 📄 License

Proprietary - Internal use only for InnerBhakti

---

## 🔗 Resources

- **[FastAPI Documentation](https://fastapi.tiangolo.com/)** - Modern Python web framework
- **[Pydantic AI](https://ai.pydantic.dev/)** - Type-safe AI agent framework
- **[ElevenLabs API Docs](https://elevenlabs.io/docs)** - Text-to-speech platform
- **[HeyGen API](https://docs.heygen.com/)** - Video generation service
- **[uv Package Manager](https://github.com/astral-sh/uv)** - Fast Python tooling

---

## 📞 Support

For technical support or questions about this platform:
- **Internal Team**: Contact the backend development team
- **API Issues**: Check `/docs` endpoint for live API schema
- **Production Incidents**: Review logs and consult error handling section above

---

**Developed with ❤️ for InnerBhakti | Version 0.1.0**
