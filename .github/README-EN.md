# AutoClip

AI-powered long-form video clipping: import from **Bilibili / YouTube links** or **local files**, analyze transcripts with an LLM, auto-cut clips and themed collections, refine by subtitle lines, and publish to Bilibili or YouTube.

[![Python](https://img.shields.io/badge/Python-3.10+-green?style=flat&logo=python)](https://python.org)
[![React](https://img.shields.io/badge/React-18-blue?style=flat&logo=react)](https://reactjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-red?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat)](../LICENSE)

**Repo**: [https://github.com/123mlly/autoclip](https://github.com/123mlly/autoclip)  
**Language**: [English](../README-EN.md) | [中文](../README.md)

---

## Features

| Feature | Description |
|---------|-------------|
| Link import | Paste a Bilibili or YouTube URL; download and create a project |
| File import | Upload a local video (optional SRT); local **Whisper** if no subtitles |
| AI pipeline | Outline → timestamps → scoring → titles → clustering → FFmpeg cuts |
| Clips & collections | Preview/download clips; AI collections; manual create & drag reorder |
| Subtitle editing | Delete lines from the transcript and re-export the clip |
| Publishing | Upload to Bilibili (cookie / password / QR) or YouTube (Google OAuth) |
| Multi-LLM | Qwen (DashScope), OpenAI, Gemini, SiliconFlow via Settings |
| Progress | HTTP polling (not WebSocket); Redis for Celery queues and progress cache |

---

## Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Celery, Redis, SQLite
- **Frontend**: React 18, TypeScript, Vite, Ant Design, Zustand
- **Media**: FFmpeg, yt-dlp, **openai-whisper** (local speech-to-text when no SRT)
- **AI**: DashScope / Qwen by default; other providers in Settings
- **Deploy**: Docker Compose (prod serves UI + API on one origin; dev splits ports)

---

## Quick start

### Requirements

**Option A (Docker) only needs:**

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running (includes Compose)

**Option B (local) needs:**

- Python 3.10+, Node.js 18+, Redis, FFmpeg
- `pip install -r requirements.txt` installs `openai-whisper` (includes PyTorch; large download)

### Hardware recommendations

Local Whisper (when no SRT is provided) needs more CPU/RAM than API-only usage:

| Scenario | CPU | RAM | Disk | Notes |
|----------|-----|-----|------|--------|
| Minimum | 4 cores | 8 GB | 20 GB+ | Short videos + Whisper `tiny`/`base`; first Docker build/model download is slow |
| **Recommended** | 8+ cores | **16 GB** | 40 GB+ | Day-to-day clipping; smoother with `base`/`small` |
| Comfortable | 8+ cores / Apple Silicon | 32 GB | 60 GB+ | Long videos, `small`/`medium`; NVIDIA GPU speeds Whisper a lot |

Notes:

- **Disk**: Docker image includes PyTorch; also reserve space for Whisper model cache and videos under `data/`  
- **GPU (optional)**: Not required; CPU works, but long videos are slower  
- **SRT provided (no speech recognition)**: 8 GB RAM is often enough for import + AI pipeline  

---

### Option A: Docker (recommended)

Best for most users: one command starts Redis, the **frontend**, API, and Celery workers.

**1. Clone**

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip
```

**2. Set API key (required for AI)**

```bash
cp env.example .env
```

Edit `.env` and set your DashScope / Qwen key:

```bash
API_DASHSCOPE_API_KEY=sk-your-key
```

> The UI can start without a key, but AI clipping will not work. You can also set the key later in Settings.

**3. Start**

```bash
./docker-start.sh
```

The first run builds images (including the frontend bundle) and may take a while (Whisper / PyTorch make the image large). Then open:

| URL | What |
|-----|------|
| http://localhost:8000 | **Frontend UI** (served by the API on the same origin; no separate :3000) |
| http://localhost:8000/api/v1 | Backend API |
| http://localhost:8000/docs | API docs |

> Note: `./docker-start.sh` already includes the frontend. The image runs `npm run build`, then serves the web UI and API together on port **8000**. Only `./docker-start.sh dev` starts a separate Vite server on **3000**.  
> Inside Docker, `REDIS_URL` is set to `redis://redis:6379/0` (Compose service name); you do not need to change the localhost default in `.env` for local runs.

**4. Useful commands**

```bash
./docker-status.sh          # status
./docker-stop.sh            # stop everything
docker compose logs -f      # logs
```

**Dev mode (hot reload)**

For day-to-day use, prefer the production start above. To edit source with hot reload:

```bash
./docker-start.sh dev
```

- Frontend: http://localhost:3000  
- Backend: http://localhost:8000  

---

### Option B: Local

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip

cp env.example .env
# Set API_DASHSCOPE_API_KEY

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # includes openai-whisper; first install is slow

cd frontend && npm install && cd ..

# Redis and FFmpeg must be available
./start_autoclip.sh
# or: ./quick_start.sh
```

- Frontend: http://localhost:3000  
- Backend: http://localhost:8000  

---

## Configuration

Copy `env.example` to `.env`:

| Variable | Notes |
|----------|--------|
| `API_DASHSCOPE_API_KEY` | **Required for AI** (or configure in Settings UI) |
| `API_MODEL_NAME` | Default `qwen3.7-plus` |
| `DASHSCOPE_BASE_URL` | Optional; see comments in `env.example` for intl |
| `DATABASE_URL` | Default SQLite `sqlite:///./data/autoclip.db` |
| `REDIS_URL` | Local default `redis://localhost:6379/0`; Compose overrides to `redis://redis:6379/0` |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | Optional, for YouTube upload OAuth |
| `YOUTUBE_REDIRECT_URI` | Default `http://localhost:8000/api/v1/youtube-upload/oauth/callback` |

See `env.example` for processing tunables (chunk size, score threshold, etc.).

**Redis** is used for Celery task queues (import, Whisper, pipeline, …) and progress caching. Project data lives in SQLite under `data/`, not in Redis.

---

## Typical workflow

1. On the home page, use **Link import** or **File import** and pick a category  
2. Processing starts in the background (Celery); watch progress on the project page  
3. Review **clips** and **collections**; edit titles and reorder as needed  
4. Use **subtitle editing** to refine a clip  
5. **Publish** to Bilibili or YouTube after linking accounts in Settings  

---

## Layout

```
autoclip/
├── backend/                 # FastAPI, pipeline, Celery, models
│   ├── api/v1/              # REST API
│   ├── pipeline/            # Six-step processing pipeline
│   ├── tasks/               # Async jobs
│   └── core/                # Config, DB, Celery
├── frontend/                # React SPA
├── data/                    # DB and project data (runtime)
├── docker-compose.yml
├── docker-compose.dev.yml
├── docker-start.sh
├── start_autoclip.sh
└── env.example
```

---

## API overview

Base path: `/api/v1` (interactive docs at `/docs`)

| Area | Prefix | Purpose |
|------|--------|---------|
| Projects | `/projects` | CRUD, status, download, retry |
| Clips / collections | `/clips`, `/collections` | CRUD, titles, reorder |
| Import | `/bilibili`, `/youtube` | Parse & download |
| Subtitles | `/subtitle-editor` | Preview & apply line edits |
| Publish | `/upload`, `/youtube-upload` | Bilibili / YouTube upload |
| Progress | `/progress`, `/simple-progress` | Polling |
| Settings | `/settings` | LLM and related config |

---

## FAQ

**AI does nothing?**  
Check the API key in `.env` or Settings. Docker loads `.env` via `env_file`.

**No subtitles / speech recognition?**  
Without an SRT, local **Whisper** (`openai-whisper`) generates subtitles. The Docker image includes it. On CPU, the first run downloads a model (`base` / `small`, etc.) and can take a while.

**Docker build is slow or apt fails?**  
First builds pull PyTorch and other large deps. If apt returns `502` or cannot reach the mirror, retry later or change `DEBIAN_MIRROR` in the Dockerfile (e.g. `mirrors.tuna.tsinghua.edu.cn`).

**Backend code changes not applied in Docker?**  
Prod images bake in the code—rebuild: `docker compose build autoclip && docker compose up -d`. For hot reload use `./docker-start.sh dev`.

**YouTube download fails?**  
yt-dlp often needs browser cookies; see yt-dlp docs.

**YouTube upload?**  
Create a Google Cloud OAuth client, put ID/secret in `.env`, match `YOUTUBE_REDIRECT_URI`.

**Port conflicts?**  
Prod Docker uses `8000` and `6379`; dev also needs `3000`. Stop local uvicorn/vite/redis first.

---

## Support

- [Issues](https://github.com/123mlly/autoclip/issues)
- [Discussions](https://github.com/123mlly/autoclip/discussions)
- Docs: [docs/](../docs/)

---

## License

[MIT](../LICENSE)
