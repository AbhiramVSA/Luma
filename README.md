# Luma

AI-powered video content production platform. Transforms scripts into production-ready video content with talking avatars, expressive audio, and intelligent scene management.

## What It Does

Luma automates the full video production pipeline:

1. **Script Analysis** — GPT agents parse scripts, extract dialogue, and map assets to scenes
2. **Audio Synthesis** — ElevenLabs generates natural voice audio with emotion tags and multi-character support
3. **Video Rendering** — HeyGen produces synchronized talking-photo videos with customizable avatars
4. **Pipeline Orchestration** — Creatomate assembles final renders from audio, video, and image assets

Additional capabilities:
- **Longform Meditation Audio** — Multi-scene narration with clause-level synthesis, silence analysis, and intelligent pause insertion
- **Image-to-Video** — Freepik Kling v2.1 transforms static images into motion video clips
- **Operator Console** — Next.js frontend for managing workflows with real-time status tracking

## Architecture

```
Luma/
├── src/                          # FastAPI backend (Python 3.11+)
│   ├── api/v1/routers/           # Endpoint definitions
│   ├── controllers/              # Business logic
│   ├── models/                   # Pydantic request/response schemas
│   ├── services/                 # Auth, JWT management
│   ├── db/                       # SQLAlchemy ORM (PostgreSQL)
│   ├── utils/                    # AI agents, audio analysis
│   ├── prompts/                  # LLM system prompts
│   ├── config/                   # Pydantic settings
│   └── main.py                   # FastAPI entry point
├── content-gen/                  # Next.js 14 operator console
│   ├── app/                      # Pages (dashboard, login, signup)
│   ├── components/               # React components + shadcn/ui
│   ├── lib/                      # API client, utilities
│   └── hooks/                    # Custom React hooks
├── pyproject.toml                # Python dependencies & tooling config
└── .env.example                  # Environment variable template
```

### Tech Stack

**Backend:** FastAPI, Pydantic AI (GPT-5), SQLAlchemy (async), ElevenLabs, HeyGen, Freepik, Creatomate
**Frontend:** Next.js 14, React 19, Tailwind CSS, shadcn/ui, Radix UI
**Infrastructure:** PostgreSQL (Neon), JWT auth, Vercel deployment

## Getting Started

### Prerequisites

- Python 3.11+ with [uv](https://github.com/astral-sh/uv)
- Node.js 18+ with pnpm
- API keys: OpenAI, ElevenLabs, HeyGen (see `.env.example`)

### Setup

```bash
# Clone and install backend
git clone https://github.com/AbhiramVSA/Luma.git
cd Luma
cp .env.example .env  # Fill in your API keys
uv sync

# Install frontend
cd content-gen
pnpm install
cd ..
```

### Run Locally

```bash
# Backend (terminal 1)
uv run fastapi dev src/main.py

# Frontend (terminal 2)
cd content-gen
pnpm dev
```

- Backend API: http://127.0.0.1:8002 (Swagger docs at `/docs`)
- Frontend: http://127.0.0.1:3000

## API Endpoints

### Authentication
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/login` | Login with email/password, returns JWT |

### Audio
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/elevenlabs/generate-audio` | Generate per-scene audio from script |
| POST | `/api/v1/elevenlabs/generate-audio/longform` | Generate longform narration with pauses |
| GET | `/api/v1/elevenlabs/audio-files` | List generated audio files |
| DELETE | `/api/v1/elevenlabs/audio-files` | Clear cached audio |

### Video
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/heygen/generate-video` | Generate talking-photo videos from script |
| POST | `/api/v1/heygen/upload-audio-assets` | Upload audio to HeyGen |
| POST | `/api/v1/heygen/avatar-iv/generate` | Generate Avatar IV video |

### Image-to-Video
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/freepik/image-to-video/kling-v2-1-std` | Submit Kling video task |
| GET | `/api/v1/freepik/image-to-video/kling-v2-1/{task_id}` | Poll task status |

### Creatomate
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/creatomate/render` | Full pipeline: audio → video → render |
| POST | `/api/v1/creatomate/upload-image` | Upload scene image |

### Longform Scenes
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/longform_scenes` | Multi-scene meditation audio generation |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check |
| GET | `/` | Root status |

## Script Format

```
[Scene 1 – Introduction]
Visual: Professional setting
Dialogue (VO): "Welcome to our platform"
Talking photo: Monica_inSleeveless_20220819

[Scene 2 – Main Content]
Dialogue (VO): "Here's what we offer"
```

Scene identifiers follow `[Scene X ...]` format. `Talking photo:` sets the avatar. Audio assets are matched automatically.

## Deployment

### Vercel (Two Projects)

**Backend** (`src/`):
- Root directory: `src`
- Entry point: `src/api/index.py`
- Runtime: Python 3.11 (pinned in `src/runtime.txt`)
- Dependencies: `src/requirements.txt`

**Frontend** (`content-gen/`):
- Root directory: `content-gen`
- Build: `pnpm install && pnpm build`
- Env: `NEXT_PUBLIC_API_BASE_URL=https://<backend>.vercel.app/api/v1`

### Docker

```bash
docker build -t luma .
docker run -d -p 8002:8002 --env-file .env -v $(pwd)/generated_audio:/app/generated_audio luma
```

## Development

```bash
# Lint and format
uv run ruff check src
uv run ruff format src

# Frontend
cd content-gen
pnpm lint
pnpm build
```

### Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | GPT agent orchestration |
| `ELEVENLABS_API_KEY` | Yes | Text-to-speech synthesis |
| `HEYGEN_API_KEY` | Yes (video) | Video generation |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Yes | Token signing secret |
| `FREEPIK_API_KEY` | Optional | Image-to-video |
| `CREATOMATE_API_KEY` | Optional | Video rendering |

## License

Proprietary — Internal use only.
