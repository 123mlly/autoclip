# AutoClip

AI-powered long-form video clipping: import from **Bilibili / YouTube / Douyin links** or **local files**, analyze transcripts with an LLM, auto-cut clips and themed collections; supports **AI storyboard montage** (shots + narration + export), in-project **manual montage**, subtitle-based editing, and publishing to Bilibili or YouTube.

[![Python](https://img.shields.io/badge/Python-3.10+-green?style=flat&logo=python)](https://python.org)
[![React](https://img.shields.io/badge/React-18-blue?style=flat&logo=react)](https://reactjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-red?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE)

**Repo**: [https://github.com/123mlly/autoclip](https://github.com/123mlly/autoclip)  
**Language**: [English](README-EN.md) | [中文](README.md)

---

## Features

| Feature | Description |
|---------|-------------|
| Link import | Paste a Bilibili / YouTube / Douyin URL; download and create a project |
| File import | Upload a local video (optional SRT); local ASR (default **faster-whisper**) if no subtitles |
| AI pipeline | Outline → timestamps → scoring → titles → clustering → FFmpeg cuts |
| Clips & collections | Preview/download clips; AI collections; manual create & drag reorder |
| **AI montage** | Upload source video → AI storyboard (shots + narration + timeline) → edit → export (with/without burned-in narration) → publish |
| Project montage | Drag clips on a timeline inside a project; transitions, BGM, 9:16 / 16:9 output |
| Subtitle editing | Delete lines from the transcript and re-export the clip |
| Publishing | Upload to Bilibili (cookie / password / QR) or YouTube (Google OAuth) |
| Multi-LLM | Qwen (DashScope), OpenAI, Gemini, SiliconFlow via Settings |
| Progress | HTTP polling (not WebSocket); Redis for Celery queues and progress cache |

---

## Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Celery, Redis, SQLite
- **Frontend**: React 18, TypeScript, Vite, Ant Design, Zustand
- **Media**: FFmpeg, yt-dlp, **faster-whisper** (default local ASR; openai-whisper optional)
- **AI**: DashScope / Qwen by default; other providers in Settings
- **Deploy**: Docker Compose (prod serves UI + API on one origin; dev splits ports)

---

## Quick start

### Requirements

**Option A (Docker) only needs:**

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running (includes Compose)

**Option B (local) needs:**

- Python 3.10+, Node.js 18+, Redis, FFmpeg
- `pip install -r requirements.txt` installs `faster-whisper` (default) and `openai-whisper` (large download)

### Hardware recommendations

Local ASR (default faster-whisper, when no SRT is provided) needs more CPU/RAM than API-only usage:

| Scenario | CPU | RAM | Disk | Notes |
|----------|-----|-----|------|--------|
| Minimum | 4 cores | 8 GB | 20 GB+ | Short videos + `tiny`/`base` (`int8`); first Docker build/model download is slow |
| **Recommended** | 8+ cores | **16 GB** | 40 GB+ | Day-to-day clipping; smoother with `faster_whisper` + `base` |
| Comfortable | 8+ cores / Apple Silicon | 32 GB | 60 GB+ | Long videos, `small`/`medium`; NVIDIA GPU helps a lot |

Notes:

- **Disk**: Docker image includes PyTorch / CTranslate2; also reserve space for ASR model cache and videos under `data/`  
- **GPU (optional)**: Not required; CPU works, but long videos are slower  
  - **Default Docker is CPU**: `./docker-start.sh` (Windows: `docker-start.bat`)  
  - With NVIDIA: `./docker-start.sh gpu` / `docker-start.bat gpu` (overlay `docker-compose.gpu.yml`; needs driver + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html))  
- **SRT provided (no speech recognition)**: 8 GB RAM is often enough for import + AI pipeline  
- **Switch ASR**: set `SPEECH_RECOGNITION_METHOD=faster_whisper|whisper_local` in `.env` (see `env.example`)  

---

### Option A: Docker (recommended)

Best for most users: one command starts Redis, the **frontend**, API, and Celery workers.

| OS | Start script |
|----|--------------|
| macOS / Linux / WSL | `./docker-start.sh` |
| Windows (CMD) | `docker-start.bat` (requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) running) |

**1. Clone**

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip
```

**2. Set API key (required for AI)**

```bash
# macOS / Linux / WSL
cp env.example .env

# Windows CMD
copy env.example .env
```

Edit `.env` and set your DashScope / Qwen key:

```bash
API_DASHSCOPE_API_KEY=sk-your-key
```

> The UI can start without a key, but AI clipping will not work. You can also set the key later in Settings.  
> If `.env` is missing, the start script copies it from `env.example`.

**3. Start**

```bash
# macOS / Linux / WSL
./docker-start.sh

# Windows CMD
docker-start.bat
```

The first run builds images (including the frontend bundle) and may take a while (ASR / PyTorch make the image large). Then open:

| URL | What |
|-----|------|
| http://localhost:8000 | **Frontend UI** (served by the API on the same origin; no separate :3000) |
| http://localhost:8000/api/v1 | Backend API |
| http://localhost:8000/docs | API docs |

> Note: The start script already includes the frontend. The image runs `npm run build`, then serves the web UI and API together on port **8000**. Only `dev` mode starts a separate Vite server on **3000**.  
> Inside Docker, `REDIS_URL` is set to `redis://redis:6379/0` (Compose service name); you do not need to change the localhost default in `.env` for local runs.

**4. Useful commands**

| Action | macOS / Linux / WSL | Windows CMD |
|--------|---------------------|-------------|
| Status | `./docker-status.sh` | `docker-status.bat` |
| Stop | `./docker-stop.sh` | `docker-stop.bat` |
| Logs | `docker compose logs -f` | same |
| GPU start | `./docker-start.sh gpu` | `docker-start.bat gpu` |
| Dev mode | `./docker-start.sh dev` | `docker-start.bat dev` |

Do not use `gpu` without an NVIDIA GPU—startup may fail.

**Dev mode (hot reload)**

For day-to-day use, prefer the production start above. To edit source with hot reload:

```bash
./docker-start.sh dev      # Windows: docker-start.bat dev
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
pip install -r requirements.txt   # includes faster-whisper, etc.; first install is slow

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

**Redis** is used for Celery task queues (import, ASR, pipeline, …) and progress caching. Project data lives in SQLite under `data/`, not in Redis.

---

## Typical workflow

### Long-form clipping (default)

1. On the home page, use **Link import** or **File import** and pick a category  
2. Processing starts in the background (Celery); watch progress on the project page  
3. Review **clips** and **collections**; edit titles and reorder as needed  
4. Use **subtitle editing** to refine a clip  
5. **Publish** to Bilibili or YouTube after linking accounts in Settings  

### AI montage

1. Open **AI montage** from the home page (or visit `/storyboard`)  
2. Upload MP4 (SRT recommended; ASR runs automatically if missing)  
3. Configure model, narration style, duration ratio, shot count, etc., then **Generate storyboard**  
4. Edit narration per shot; batch translate/replace or fill from source subtitles  
5. **Export video**: silent cut, or **with burned-in narration** (white text + black stroke, no background bar; Pillow + FFmpeg overlay, no libass required)  
6. After export, **Publish** to Bilibili / YouTube (same account setup as clip uploads)  

Configure AI models, Bilibili accounts, and YouTube OAuth in Settings.

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
├── docker-compose.gpu.yml   # optional NVIDIA overlay
├── docker-compose.dev.yml
├── Dockerfile
├── Dockerfile.gpu           # CUDA worker image
├── docker-start.sh / .bat
├── docker-stop.sh / .bat
├── docker-status.sh / .bat
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
| Import | `/bilibili`, `/youtube`, `/douyin` | Parse & download |
| Subtitles | `/subtitle-editor` | Preview & apply line edits |
| **AI montage** | `/storyboards` | Storyboard AI, edit, render, upload prep |
| **Project montage** | `/montages` | Timeline, BGM, render |
| Publish | `/upload`, `/youtube-upload` | Bilibili / YouTube (incl. AI montage exports) |
| Progress | `/progress`, `/simple-progress` | Polling |
| Settings | `/settings` | LLM and related config |

---

## FAQ

**AI does nothing?**  
Check the API key in `.env` or Settings. Docker loads `.env` via `env_file` (`./docker-start.sh` / `docker-start.bat` will warn if missing).

**Running Docker on Windows?**  
Install and start Docker Desktop, then run `docker-start.bat` from **CMD**. Stop / status: `docker-stop.bat`, `docker-status.bat`. Or use WSL2 with `./docker-start.sh`.

**No subtitles / speech recognition?**  
Without an SRT, **faster-whisper** generates subtitles by default (stable segment timestamps, usually lower memory than stock Whisper). You can switch in `.env`:

```bash
SPEECH_RECOGNITION_METHOD=faster_whisper   # default
SPEECH_RECOGNITION_MODEL=base              # tiny/base/small/...
# SPEECH_RECOGNITION_METHOD=whisper_local  # stock openai-whisper
```

The default Docker image is CPU-oriented; the first run downloads models. With NVIDIA, use `./docker-start.sh gpu` or `docker-start.bat gpu`. Force device with `WHISPER_DEVICE` / `FASTER_WHISPER_DEVICE` (`cpu`/`cuda`); on CPU, `FASTER_WHISPER_COMPUTE_TYPE=int8` is recommended.

**Docker build is slow or apt fails?**  
First builds pull PyTorch and other large deps. If apt returns `502` or cannot reach the mirror, retry later or change `DEBIAN_MIRROR` in the Dockerfile (e.g. `mirrors.tuna.tsinghua.edu.cn`).

**Backend code changes not applied in Docker?**  
Prod images bake in the code—rebuild: `docker compose up -d --build`. For hot reload use `./docker-start.sh dev` / `docker-start.bat dev`. Restart `celery-worker` after task code changes (pipeline, AI montage render, uploads).

**AI montage narration export?**  
This burns **subtitles**, not TTS voiceover. Narration is rendered with Pillow to a transparent PNG and overlaid via FFmpeg `overlay`, so builds without libass/drawtext (e.g. default Homebrew FFmpeg) still work. Use **Publish** in the storyboard toolbar after export.

**YouTube / Douyin download fails?**  
- **YouTube**: yt-dlp often needs login cookies. In Docker, upload a `cookies.txt` from youtube.com on the link-import page → `data/cookies/youtube.txt`.
- **Douyin**: public videos use the share-page direct link and **usually need no cookies**. Paste `www.douyin.com/video/...` or an App share short link (not a user profile). If it still fails, upload `data/cookies/douyin.txt`.

Locally you can also pick a logged-in browser (works better for YouTube). Re-export when cookies expire.

If logs show `n challenge solving failed` / `Only images are available`: production image needs **Node.js ≥ 20** (Dockerfile already copies from `node:22`). Rebuild: `docker compose build autoclip && docker compose up -d`, then check `node -v` in the container.

If logs show `n challenge solving failed` / `Only images are available`, the image needs **Node.js ≥ 20** (Dockerfile copies from `node:22`). Rebuild: `docker compose build autoclip && docker compose up -d`, then check `node -v` inside the container.

**YouTube upload?**  
Create a Google Cloud OAuth client, put ID/secret in `.env`, match `YOUTUBE_REDIRECT_URI`.

**Port conflicts?**  
Prod Docker uses `8000` and `6379`; dev also needs `3000`. Stop local uvicorn/vite/redis first.

---

## Support

- [Issues](https://github.com/123mlly/autoclip/issues)
- [Discussions](https://github.com/123mlly/autoclip/discussions)
- Docs: [docs/](docs/)

---

## License

[MIT](LICENSE)
