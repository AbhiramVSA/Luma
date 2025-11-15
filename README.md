# Luma Video Generation Automation

> Enterprise-grade automation platform for AI-powered video content production. Transform scripts into production-ready video content with talking avatars, expressive audio, and intelligent scene management.

## Overview

Luma provides a comprehensive video generation pipeline that automates the complete production workflow from script to finished video. The platform integrates multiple AI services to deliver high-quality video content at scale.

**Key Capabilities:**

- **AI-Powered Scene Analysis**: GPT-powered agents parse scripts, extract dialogue, and intelligently map assets to scenes
- **Professional Voice Synthesis**: ElevenLabs text-to-speech generates natural, expressive audio with multi-character support
- **Automated Video Production**: HeyGen talking photo integration produces synchronized video content with customizable avatars
- **Intelligent Asset Management**: UUID-based audio file naming ensures unique identifiers while maintaining scene relationships, while sanitized asset filtering prevents malformed entries from entering the pipeline
- **Production-Grade API**: RESTful architecture with comprehensive validation, error handling, and status tracking
- **Operator Console**: Next.js frontend provides dashboards for managing audio, video, and asset workflows

---

## Features

### Core Capabilities

#### Complete Video Generation Pipeline
- **End-to-End Automation**: Script input → AI processing → audio synthesis → video rendering → status tracking
- **HeyGen Talking Photo Integration**: Generate videos with AI avatars (720×1280 portrait format optimized for social media)
- **Real-Time Status Polling**: Automated job monitoring with configurable retry logic (up to 2 minutes polling by default)
- **Video URL Delivery**: Direct access to completed videos with thumbnail previews

#### Advanced Audio Processing
- **Unique Audio Identifiers**: UUID-suffixed filenames (`scene_1__a1b2c3d4.mp3`) prevent collisions across regenerations
- **Scene Manifest System**: JSON manifest (`scene_audio_map.json`) tracks scene-to-file relationships
- **Smart Asset Caching**: Avoid redundant uploads to HeyGen with persistent asset cache
- **Multi-Format Support**: MP3, WAV, M4A, AAC audio formats
- **Longform Scene Audio**: Agent-driven meditation narration with intelligent pause insertion, silence trimming, and multi-scene stitching
- **Clause-Level Synthesis**: Break narration into natural speech segments with configurable pause durations
- **Audio Sanitation**: Automatic removal of pause annotations (e.g., "(5 sec)") from spoken text while preserving timing metadata

#### Intelligent AI Agents
- **Script Analysis Agent**: Extracts scene structure, dialogue, and character information
- **HeyGen Configuration Agent**: Maps audio assets to scenes with flexible pattern matching
- **Longform Sanitizer Agent**: Strips pause annotations from meditation scripts and produces clause-level narration specs
- **Longform Splice Agent**: Validates generated audio pause accuracy and provides adjustment instructions
- **Scene Segmentation Agent**: Analyzes meditation narration to determine sentence boundaries and optimal pause durations
- **Context-Aware Processing**: Handles scene identifiers with underscores, hyphens, or numeric patterns

#### Frontend Operator Console
- **Next.js 14 Application**: Modern React 19 application built with shadcn/ui components and Tailwind CSS
- **Persistent Workflows**: Audio and video results are cached locally using localStorage for seamless workflow continuation
- **Audio Library Management**: Interface for downloading, inspecting, and clearing cached assets with detailed metadata
- **Longform Scene Tester**: Dedicated interface for generating meditation audio with multi-scene narration, pause visualization, and downloadable master tracks
- **Performance Optimized**: Implements deferred rendering, memoization, and motion-safe transitions for responsive user experience

#### Production-Ready Architecture
- **FastAPI Framework**: High-performance async API with automatic OpenAPI documentation
- **Pydantic Validation**: Type-safe request/response models with comprehensive error messages
- **Modular Design**: Clean separation between routes, controllers, models, and utilities
- **Environment-Based Config**: Secure credential management via `.env` files

---

## Getting Started

### Prerequisites

- **Python 3.13+** with uv package manager
- **Node.js 18+** with pnpm (or npm)
- **Required API Keys:**
  - OpenAI API key for GPT-4 or GPT-5 (agent orchestration)
  - ElevenLabs API key (text-to-speech synthesis)
  - HeyGen API key (video generation with talking avatars)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/AbhiramVSA/Luma.git
   cd Luma
   ```

2. **Install backend dependencies**
   ```bash
   uv sync
   ```

3. **Configure backend environment variables**
   
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

4. **Install frontend dependencies**
   ```bash
   cd content-gen
   pnpm install  # or npm install
   cd ..
   ```

### Running the Backend API

Start the FastAPI development server:

```bash
uv run fastapi dev src/main.py
```

The API will be available at `http://127.0.0.1:8002`

**Interactive Documentation:**
- **Swagger UI**: http://127.0.0.1:8002/docs (interactive API testing)
- **ReDoc**: http://127.0.0.1:8002/redoc (clean reference documentation)

### Running the Frontend Console

Start the Next.js operator console in a new terminal:

```bash
cd content-gen
pnpm dev # or npm run dev
```

The UI runs at `http://127.0.0.1:3000` and connects to the backend API at `http://127.0.0.1:8002`. If deploying to a different host, update the API endpoint URLs in the component files under `content-gen/components`.

---

## Frontend Operator Console

The Next.js operator console provides a comprehensive interface for managing the video generation pipeline with real-time monitoring and workflow persistence.

### Interface Features

#### Main Dashboard
- **Tabbed Navigation**: Dedicated views for Audio Generation, Video Generation, Image-to-Video, Longform Scene Stitching, and Audio Library
- **Real-Time Health Monitoring**: Backend API availability indicator with automatic polling
- **State Persistence**: Browser-based caching preserves generated outputs across sessions

#### Audio Generation Tab
- **Script Editor**: Multi-line textarea with formatting examples for scene structure
- **Audio Preview**: Embedded player controls for immediate playback verification
- **Asset Downloads**: Direct access to MP3 files and scene manifest JSON
- **Cache Management**: Clear functionality for removing cached outputs

#### Video Generation Tab
- **Cache Control**: Toggle to force re-upload of assets, bypassing HeyGen cache
- **Progress Monitoring**: Real-time aggregation of scene statuses (completed, processing, failed)
- **Auto-Refresh**: Automatic 30-second polling when videos are in processing state
- **Detailed Results**: Per-scene cards with video player, thumbnail, download links, and status information

#### Audio Library Tab
- **File Browser**: Complete listing of generated audio files with metadata (filename, size, timestamp)
- **Bulk Operations**: Refresh inventory or clear all cached files
- **Metadata Display**: Badges indicating manifest presence and HeyGen cache status
- **Download Capability**: Individual file downloads through static file serving

#### Longform Scenes Tab
- **Meditation Script Editor**: Multi-line textarea for pasting meditation scripts with scene headers and pause annotations
- **Example Templates**: One-click loading of sample meditation scripts demonstrating proper formatting
- **Scene Audio Preview**: Individual audio players for each processed scene with segmentation details
- **Master Track Generation**: Automatic stitching of all scenes into a single downloadable MP3 file
- **Pause Visualization**: Per-sentence display showing inferred pause durations and clause text
- **Multipart Response Handling**: Client-side parsing of boundary-delimited metadata and audio binary data

### User Experience

The interface implements modern UX patterns including:
- Smooth fade-in, scale, and hover transitions
- Accessibility compliance with `prefers-reduced-motion` support
- Responsive layouts using Tailwind breakpoint utilities
- Performance optimization through React's `useDeferredValue` and memoization techniques

### Technology Stack
- **Framework**: Next.js 14.2 with App Router architecture
- **UI Components**: shadcn/ui (Radix UI primitives with Tailwind CSS)
- **State Management**: React 19 hooks with localStorage persistence layer
- **Styling**: Tailwind CSS 4 with custom animation utilities
- **Icons**: Lucide React icon library

---

## API Reference

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

### 2. HeyGen Avatar IV Generation

**Endpoint:** `POST /api/v1/heygen/avatar-iv/generate`

Create single-avatar Avatar IV videos by pairing a HeyGen image asset (`image_key`) with pre-uploaded audio. An LLM agent fills in the remaining required payload fields (title, script, voice, orientation, fit, and motion prompt) and falls back to safe defaults when the model output is invalid.

#### Request Parameters

| Field                     | Type    | Required | Description |
|---------------------------|---------|----------|-------------|
| `image_asset_id`          | string  | Yes      | Image key returned by HeyGen asset upload API |
| `script`                  | string  | Yes      | Narration text pasted by the user; also feeds the agent |
| `video_brief`             | string  | No       | Optional creative brief (defaults to `script` when omitted) |
| `voice_preferences`       | string  | No       | Voice guidance or explicit HeyGen voice id |
| `orientation_hint`        | enum    | No       | `portrait` or `landscape` preference (overrides agent)
| `fit_hint`                | enum    | No       | `cover` or `contain` preference (overrides agent)
| `enhance_motion_override` | bool    | No       | Force the `enhance_custom_motion_prompt` flag |
| `force_upload_audio`      | bool    | No       | Re-upload audio assets before lookup |

Audio assets are resolved automatically from `generated_audio/heygen_assets.json`; if multiple assets exist, the router matches on scene identifiers referenced in the script and falls back to the first available asset.

#### Response Shape

```json
{
  "status": "success",
  "job": { "code": 100, "data": { "video_id": "..." } },
  "prompts": {
    "video_title": "...",
    "script": "...",
    "voice_id": "...",
    "video_orientation": "portrait",
    "fit": "cover",
    "custom_motion_prompt": "...",
    "enhance_custom_motion_prompt": true
  },
  "audio_asset_id": "...",
  "audio_reference": "scene_1",
  "request_payload": { "image_key": "...", "audio_asset_id": "...", "script": "..." }
}
```

Failures return `status = "failed"` with details listed under `errors`.

---

### 3. Audio Generation Only

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

### 4. Longform Scene Audio Generation

**Endpoint:** `POST /api/v1/longform_scenes`

Generate multi-scene meditation audio with intelligent pause insertion, silence analysis, and automatic stitching. This endpoint processes scripts with explicit scene headers and optional pause annotations, returning both individual scene audio and a final master track.

#### Request Schema

```json
{
  "script": "string (required)"
}
```

#### Script Format

Meditation scripts should follow this structure:

```
शुरुआत
धीरे-धीरे अपनी आँखें बंद करें और एक गहरी सांस लें... (5 sec)
अब अपनी सांस छोड़ें और अपने कंधों को ढीला छोड़ दें।

जगह और पोज़शन
आप खुद को एक शांत जंगल में कल्पना करें। (10 sec)
हर ओर हरी-भरी प्रकृति और हल्की हवा चल रही है।

मुख्य यात्रा
अपने हृदय पर ध्यान केंद्रित करें। (15 sec)
```

**Key Points:**
- Scene headers are standalone lines without sentence-ending punctuation
- Pause annotations like `(5 sec)` are automatically extracted and removed from narration
- Default pause is 1.5 seconds after sentences ending with `.`, `?`, `!`, or `।`
- Agent-driven segmentation validates and adjusts pause timings based on audio analysis

#### Response Schema

The endpoint returns a multipart response containing:
1. **JSON Metadata**: Scene summaries with segmentation details and data URLs
2. **Audio Binary**: Final stitched MP3 file

```json
{
  "scenes": [
    {
      "scene_name": "शुरुआत",
      "segments": [
        {
          "text": "धीरे-धीरे अपनी आँखें बंद करें और एक गहरी सांस लें",
          "pause_after_seconds": 5.0
        }
      ],
      "processed_audio_path": "data:audio/mpeg;base64,..."
    }
  ],
  "final_audio_path": "data:audio/mpeg;base64,..."
}
```

**Features:**
- **Automatic Scene Parsing**: Identifies scene headers vs. narration content
- **Silence Detection**: Measures trailing silence in synthesized audio for precise pause control
- **Splice Validation**: Optional agent review of pause accuracy with adjustment recommendations
- **Trim & Pad**: Adjusts silence to match target pause durations (±60ms tolerance)
- **Master Stitching**: Combines all scene audio into a single normalized track

**Processing Time:** 30-90 seconds per scene (includes synthesis, analysis, validation, and stitching)

**Status Codes:**
- `200 OK`: Multipart stream with metadata and audio
- `422 Unprocessable Entity`: Invalid script format or missing scene content
- `502 Bad Gateway`: ElevenLabs synthesis or agent failures

---

### 5. Upload Audio Assets

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

### 6. Freepik Image-to-Video (Kling v2.1)

**Endpoints:**
- `POST /api/v1/freepik/image-to-video/kling-v2-1-std`
- `GET /api/v1/freepik/image-to-video/kling-v2-1/{task_id}`

Use Freepik's Kling v2.1 standard model to transform static imagery into motion video clips. Prompt bundles are generated server-side so downstream requests always include validated prompt text, duration, and CFG scale values.

#### Submission Request

```json
{
  "image": "base64-encoded image bytes or remote URL",
  "duration": 5,
  "webhook_url": "https://example.com/webhooks/freepik",
  "cfg_scale": 7.5,
  "static_mask": null,
  "dynamic_masks": null
}
```

`duration`, `cfg_scale`, `static_mask`, and `dynamic_masks` are optional; when omitted the controller applies values returned by the prompt bundle generator. A successful submission returns the Freepik task id together with the prompt bundle that was applied.

#### Status & Downloads

`GET /api/v1/freepik/image-to-video/kling-v2-1/{task_id}` accepts optional query parameters:
- `wait_for_completion` (bool) — Poll until the task finishes before responding
- `poll_interval` (float) — Seconds between poll attempts (defaults to controller constants)
- `timeout` (float) — Maximum seconds to poll before timing out
- `download` (bool) — Stream the rendered asset back to the client when the task is complete
- `asset_index` (int) — Select a specific asset when multiple results are returned

When `download=true`, the endpoint validates completion status and returns a streaming response for the requested asset.

---

## Architecture

### Project Structure

```
Luma/
├── content-gen/                      # Next.js operator console
│   ├── app/
│   │   ├── page.tsx                  # Main dashboard with tabbed interface
│   │   ├── layout.tsx                # Root layout with theme provider
│   │   ├── globals.css               # Tailwind base + custom animations
│   │   └── favicon.ico
│   ├── components/
│   │   ├── audio-generation.tsx      # Audio workflow UI with persistence
│   │   ├── video-generation.tsx      # HeyGen orchestration dashboard
│   │   ├── audio-library.tsx         # Local asset management table
│   │   ├── longform-scenes.tsx       # Meditation scene audio generator
│   │   ├── image-to-video.tsx        # Freepik image-to-video interface
│   │   ├── api-config.tsx            # Backend health monitoring widget
│   │   └── ui/                       # shadcn/ui primitives (button, card, etc.)
│   ├── lib/
│   │   └── utils.ts                  # Tailwind merge helpers
│   ├── public/                       # Static assets and icons
│   ├── styles/                       # Additional CSS modules
│   ├── package.json                  # Frontend scripts & dependencies
│   ├── pnpm-lock.yaml                # Locked dependency graph
│   ├── tsconfig.json                 # TypeScript configuration
│   ├── next.config.mjs               # Next.js settings
│   ├── tailwind.config.ts            # Tailwind theme customization
│   └── components.json               # shadcn/ui configuration
├── src/
│   ├── api/v1/
│   │   ├── api.py                    # Main API aggregator
│   │   └── routers/
│   │       ├── creatomate_route.py   # Creatomate render endpoints
│   │       ├── elevenlabs_route.py   # ElevenLabs audio endpoints
│   │       ├── freepik_route.py      # Freepik image-to-video endpoints
│   │       ├── heygen_route.py       # HeyGen video and avatar endpoints
│   │       └── longform_route.py     # Longform scene audio endpoint
│   ├── config/
│   │   └── config.py                 # Settings management (Pydantic)
│   ├── controllers/
│   │   ├── creatomate.py             # Creatomate orchestration helpers
│   │   ├── elevenlabs.py             # ElevenLabs workflow helpers
│   │   ├── longform_scenes.py        # Longform meditation audio orchestration
│   │   ├── freepik.py                # Freepik image-to-video orchestration
│   │   ├── generate_video.py         # Shared upload helpers for HeyGen assets
│   │   └── heygen.py                 # HeyGen avatar + batch video controller
│   ├── models/
│   │   ├── elevenlabs_model.py       # Audio request/response schemas
│   │   ├── longform.py               # Longform scene audio schemas
│   │   └── heygen.py                 # Video request/response schemas
│   ├── prompts/
│   │   ├── elevenlabs_prompt.md      # Audio agent instructions
│   │   ├── elevenlabs_longform_prompt.md  # Longform audio plan agent
│   │   ├── longform_sanitizer_prompt.md   # Script sanitation agent
│   │   ├── longform_splice_prompt.md      # Pause validation agent
│   │   ├── longform_segmentation_prompt.md # Scene segmentation agent
│   │   └── heygen_prompt.md          # Video agent instructions
│   ├── utils/
│   │   └── agents.py                 # Pydantic AI agent configurations
│   └── main.py                       # FastAPI app entry point
├── generated_audio/                  # Audio/manifest storage
│   ├── scene_audio_map.json         # Scene → filename manifest
│   └── heygen_assets.json            # Asset upload cache
├── .env                              # Environment variables (gitignored)
├── .env.example                      # Template for credentials
├── pyproject.toml                    # Project metadata & dependencies
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

## Development Guide

### Backend Code Quality

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

### Frontend Development

#### Component Structure
```
content-gen/components/
├── ui/              # Reusable primitives from shadcn/ui
├── *-generation.tsx # Feature-specific workflow components
└── api-config.tsx   # Shared backend integration
```

#### Adding New UI Components
```bash
cd content-gen
npx shadcn@latest add <component-name>  # Install shadcn/ui component
```

#### Styling Guidelines
- Use Tailwind utility classes for layout and spacing
- Custom animations defined in `app/globals.css`
- Responsive breakpoints: `sm:`, `md:`, `lg:` prefixes
- Dark mode ready via `next-themes` provider

#### Frontend Build Commands
```bash
cd content-gen

# Development server with hot reload
pnpm dev

# Type checking
pnpm build  # Next.js build includes TypeScript validation

# Production build
pnpm build && pnpm start

# Lint
pnpm lint
```

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

## Security & Best Practices

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

## Monitoring & Debugging

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

## Production Deployment

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
docker build -t luma-video-gen .
docker run -d \
  -p 8002:8002 \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e ELEVENLABS_API_KEY=$ELEVENLABS_API_KEY \
  -e HEYGEN_API_KEY=$HEYGEN_API_KEY \
  -v $(pwd)/generated_audio:/app/generated_audio \
  luma-video-gen
```

### Health Check Endpoint
Add to `src/main.py`:
```python
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}
```

---

## Contributing

This project is developed for Luma internal use. For feature requests or bug reports:

1. Open an issue with detailed reproduction steps
2. Follow existing code style (Ruff-compliant)
3. Add tests for new endpoints
4. Update this README with new features

---

## License

Proprietary - Internal use only for Luma

---

## Resources

- **[FastAPI Documentation](https://fastapi.tiangolo.com/)** - Modern Python web framework
- **[Pydantic AI](https://ai.pydantic.dev/)** - Type-safe AI agent framework
- **[ElevenLabs API Docs](https://elevenlabs.io/docs)** - Text-to-speech platform
- **[HeyGen API](https://docs.heygen.com/)** - Video generation service
- **[pydub Documentation](https://github.com/jiaaro/pydub)** - Audio manipulation library
- **[FFmpeg](https://ffmpeg.org/documentation.html)** - Audio/video processing toolkit
- **[uv Package Manager](https://github.com/astral-sh/uv)** - Fast Python tooling

---

## Support

For technical support or questions about this platform:
- **Internal Team**: Contact the backend development team
- **API Issues**: Check `/docs` endpoint for live API schema
- **Production Incidents**: Review logs and consult error handling section above

---

**Developed for Luma | Version 0.1.0**
