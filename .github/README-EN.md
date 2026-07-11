# AutoClip

AI-powered long-form video clipping: import from **Bilibili / YouTube links** or **local files**, analyze transcripts with an LLM, auto-cut clips and themed collections, refine by subtitle lines, and publish to Bilibili or YouTube.

[![Python](https://img.shields.io/badge/Python-3.9+-green?style=flat&logo=python)](https://python.org)
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
| File import | Upload a local video (optional SRT); Whisper/ASR if no subtitles |
| AI pipeline | Outline → timestamps → scoring → titles → clustering → FFmpeg cuts |
| Clips & collections | Preview/download clips; AI collections; manual create & drag reorder |
| Subtitle editing | Delete lines from the transcript and re-export the clip |
| Publishing | Upload to Bilibili (cookie / password / QR) or YouTube (Google OAuth) |
| Multi-LLM | Qwen (DashScope), OpenAI, Gemini, SiliconFlow via Settings |
| Progress | HTTP polling (WebSocket is not used) |

---

## Stack

- **Backend**: Python 3.9+, FastAPI, SQLAlchemy, Celery, Redis, SQLite
- **Frontend**: React 18, TypeScript, Vite, Ant Design, Zustand
- **Media**: FFmpeg, yt-dlp
- **AI**: DashScope / Qwen by default; other providers in Settings
- **Deploy**: Docker Compose (prod serves UI + API on one origin; dev splits ports)

---

## Quick start

### Requirements

- Docker 20.10+ and Docker Compose 2.0+ (recommended), **or**
- Local: Python 3.9+, Node.js 18+, Redis, FFmpeg

### Option A: Docker (recommended)

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip

cp env.example .env
# Set at least API_DASHSCOPE_API_KEY

./docker-start.sh
```

- App / API: http://localhost:8000  
- API docs: http://localhost:8000/docs  

Dev mode (hot reload, frontend on :3000):

```bash
./docker-start.sh dev
```

Optional Flower:

```bash
docker compose --profile monitoring up -d
# http://localhost:5555
```

Stop:

```bash
./docker-stop.sh
```

### Option B: Local

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip

cp env.example .env
# Set API_DASHSCOPE_API_KEY

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

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
| `REDIS_URL` | Local default `redis://localhost:6379/0`; overridden in Docker |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | Optional, for YouTube upload OAuth |
| `YOUTUBE_REDIRECT_URI` | Default `http://localhost:8000/api/v1/youtube-upload/oauth/callback` |

See `env.example` for processing tunables (chunk size, score threshold, etc.).

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
