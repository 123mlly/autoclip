# AutoClip

AI 长视频智能切片系统：从 **B站 / YouTube 链接** 或 **本地视频** 导入内容，基于字幕与大模型自动切片、生成主题合集，支持按台词精剪，并可投稿到 B站与 YouTube。

[![Python](https://img.shields.io/badge/Python-3.10+-green?style=flat&logo=python)](https://python.org)
[![React](https://img.shields.io/badge/React-18-blue?style=flat&logo=react)](https://reactjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-red?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE)

**仓库**: [https://github.com/123mlly/autoclip](https://github.com/123mlly/autoclip)  
**语言**: [中文](README.md) | [English](README-EN.md)

---

## 功能概览

| 能力 | 说明 |
|------|------|
| 链接导入 | 粘贴 B站 / YouTube 链接，自动下载并创建项目 |
| 文件导入 | 上传本地视频，可选附带 SRT；无字幕时用本地 ASR（默认 **faster-whisper**）自动识别 |
| AI 流水线 | 大纲 → 时间点 → 评分 → 标题 → 主题聚类 → FFmpeg 切片 |
| 切片与合集 | 预览 / 下载切片，AI 推荐合集，手动创建与拖拽排序 |
| 按台词剪辑 | 基于字幕文稿删句并重新导出切片 |
| 投稿 | 上传到 B站（Cookie / 密码 / 扫码）或 YouTube（Google OAuth） |
| 多模型 | 设置页支持通义千问、OpenAI、Gemini、硅基流动等 |
| 进度反馈 | HTTP 轮询展示处理进度（非 WebSocket）；Redis 作 Celery 队列与进度缓存 |

---

## 技术栈

- **后端**: Python 3.10+、FastAPI、SQLAlchemy、Celery、Redis、SQLite
- **前端**: React 18、TypeScript、Vite、Ant Design、Zustand
- **媒体**: FFmpeg、yt-dlp、**faster-whisper**（默认本地 ASR；可选 SenseVoice / openai-whisper）
- **AI**: DashScope / Qwen（默认），可在设置中切换其他提供商
- **部署**: Docker Compose（生产同源托管前端；开发模式前后端分离）

---

## 快速开始

### 环境要求

**方式一（Docker）只需：**

- 已安装并启动 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（含 Compose）

**方式二（本地）需要：**

- Python 3.10+、Node.js 18+、Redis、FFmpeg
- `pip install -r requirements.txt` 会安装 `faster-whisper`（默认）、`funasr`、`openai-whisper` 等（体积较大）

### 硬件推荐

无字幕时会跑本地 ASR（默认 faster-whisper），对 CPU / 内存要求明显高于「只跑 API」：

| 场景 | CPU | 内存 | 磁盘 | 说明 |
|------|-----|------|------|------|
| 最低可用 | 4 核 | 8 GB | 20 GB+ | 短视频 + `tiny`/`base`（`int8`）；Docker 首次构建与模型下载较慢 |
| **推荐** | 8 核+ | **16 GB** | 40 GB+ | 日常切片；默认 `faster_whisper` + `base` 更顺畅 |
| 更舒适 | 8 核+ / Apple Silicon | 32 GB | 60 GB+ | 长视频、`small`/`medium`；有 NVIDIA GPU 时明显更快 |

补充：

- **磁盘**：Docker 镜像含 PyTorch / CTranslate2，另加 ASR 模型缓存与 `data/` 视频文件，建议预留充足空间  
- **GPU（可选）**：非必须；无 GPU 时用 CPU 即可，长视频识别会慢一些  
  - **默认 Docker 为 CPU**，无显卡机器直接 `./docker-start.sh`  
  - 有 NVIDIA 时再用：`./docker-start.sh gpu`（叠加 `docker-compose.gpu.yml`，仅 worker 用 CUDA 镜像；需驱动 + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)）  
- **仅附带 SRT、不做语音识别**：8 GB 内存通常也能跑通导入与 AI 流水线  
- **切换 ASR**：在 `.env` 设置 `SPEECH_RECOGNITION_METHOD=faster_whisper|sensevoice|whisper_local`（见 `env.example`）  


---

### 方式一：Docker（推荐）

适合大多数人：一条命令拉起 Redis、**前端**、后端 API 和 Celery 任务队列。

**1. 克隆项目**

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip
```

**2. 配置 API Key（AI 功能必填）**

```bash
cp env.example .env
```

用编辑器打开 `.env`，把下面这一行改成你的通义千问 Key：

```bash
API_DASHSCOPE_API_KEY=sk-你的密钥
```

> 没有 Key 也能启动界面，但无法做 AI 切片。也可启动后再在「系统设置」里填写。

**3. 一键启动**

```bash
./docker-start.sh
```

首次会**重新构建镜像并打包前端**，可能需要较长时间（镜像含 ASR / PyTorch，首次下载依赖较大）。成功后浏览器打开：

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | **前端页面**（生产模式由后端同源托管，无需再开 :3000） |
| http://localhost:8000/api/v1 | 后端 API |
| http://localhost:8000/docs | API 文档 |

> 说明：`./docker-start.sh` 已包含前端。构建时会执行 `npm run build`，运行时在 **8000** 端口同时提供网页和接口。只有 `./docker-start.sh dev` 才会单独在 **3000** 跑 Vite 开发服务器。  
> Docker 内 `REDIS_URL` 自动指向服务名 `redis`（`redis://redis:6379/0`），无需改 `.env` 里的 localhost。

**4. 常用命令**

```bash
./docker-status.sh          # 查看状态
./docker-stop.sh            # 停止全部服务
docker compose logs -f      # 看日志

# 可选：NVIDIA GPU 加速 ASR / Whisper（无显卡勿用，会启动失败）
./docker-start.sh gpu
# 自检：docker compose -f docker-compose.yml -f docker-compose.gpu.yml exec celery-worker \
#   python3 -c "import torch; print(torch.cuda.is_available())"
```

**开发模式（改代码热更新）**

日常用上面的生产启动即可。若要改前端/后端源码并热重载：

```bash
./docker-start.sh dev
```

- 前端：http://localhost:3000  
- 后端：http://localhost:8000  

---

### 方式二：本地运行

```bash
git clone https://github.com/123mlly/autoclip.git
cd autoclip

cp env.example .env
# 填写 API_DASHSCOPE_API_KEY

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # 含 faster-whisper 等，首次较慢

cd frontend && npm install && cd ..

# 确保 Redis、FFmpeg 已安装并可用
./start_autoclip.sh
# 或快速启动：./quick_start.sh
```

- 前端：http://localhost:3000  
- 后端：http://localhost:8000  

---

## 配置说明

复制 `env.example` 为 `.env`：

| 变量 | 说明 |
|------|------|
| `API_DASHSCOPE_API_KEY` | **AI 功能必填**（也可在「系统设置」中配置） |
| `API_MODEL_NAME` | 默认 `qwen3.7-plus` |
| `DASHSCOPE_BASE_URL` | 可选；国际站见 `env.example` 注释 |
| `DATABASE_URL` | 默认 SQLite：`sqlite:///./data/autoclip.db` |
| `REDIS_URL` | 本地默认 `redis://localhost:6379/0`；Docker Compose 内覆盖为 `redis://redis:6379/0` |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` | YouTube 投稿 OAuth（可选） |
| `YOUTUBE_REDIRECT_URI` | 默认 `http://localhost:8000/api/v1/youtube-upload/oauth/callback` |

更多处理参数（分块大小、评分阈值等）见 `env.example`。

**Redis 用途**：Celery 任务队列（导入、ASR、切片流水线等）与处理进度缓存。业务数据在 SQLite（`data/`），不在 Redis。

---

## 使用流程

1. 打开首页，选择 **链接导入** 或 **文件导入**，并选择视频分类  
2. 导入后自动进入后台处理（Celery）；在项目页查看进度  
3. 完成后浏览 **视频片段** 与 **AI 推荐合集**，可编辑标题、拖拽排序  
4. 需要时使用 **按台词剪辑** 精修切片  
5. 通过 **投稿** 上传到 B站或 YouTube（需先在设置中绑定账号）  

系统设置页可配置 AI 模型、B站账号与 YouTube OAuth。

---

## 项目结构

```
autoclip/
├── backend/                 # FastAPI、流水线、Celery 任务、模型
│   ├── api/v1/              # REST API
│   ├── pipeline/            # 六步处理流水线
│   ├── tasks/               # 异步任务（处理 / 上传 / 维护等）
│   └── core/                # 配置、数据库、Celery
├── frontend/                # React SPA
├── data/                    # 数据库与项目数据（运行时）
├── docker-compose.yml       # 生产编排（CPU 默认）
├── docker-compose.gpu.yml   # 可选：NVIDIA GPU 叠加（仅 celery-worker）
├── docker-compose.dev.yml   # 开发编排
├── Dockerfile               # CPU 生产镜像
├── Dockerfile.gpu           # CUDA / ASR worker 镜像
├── docker-start.sh          # Docker 一键启动
├── start_autoclip.sh        # 本地一键启动
└── env.example              # 环境变量模板
```

---

## API 概览

基础路径：`/api/v1`（交互文档：`/docs`）

| 模块 | 路径前缀 | 用途 |
|------|----------|------|
| 项目 | `/projects` | 创建、状态、下载、重试 |
| 切片 / 合集 | `/clips`、`/collections` | CRUD、标题生成、排序 |
| 导入 | `/bilibili`、`/youtube` | 解析与下载 |
| 字幕编辑 | `/subtitle-editor` | 按台词预览与应用 |
| 投稿 | `/upload`、`/youtube-upload` | B站 / YouTube 上传 |
| 进度 | `/progress`、`/simple-progress` | 轮询进度 |
| 设置 | `/settings` | LLM 等配置 |

---

## 常见问题

**AI 不工作？**  
检查 `.env` 或设置页中的 API Key；Docker 需保证 `env_file: .env` 已加载（`./docker-start.sh` 会提示）。

**无字幕 / 语音识别？**  
未附带 SRT 时默认用 **faster-whisper** 生成字幕（段级时间戳更稳、通常比原版 Whisper 更省内存）。也可在 `.env` 切换：

```bash
SPEECH_RECOGNITION_METHOD=faster_whisper   # 默认推荐
SPEECH_RECOGNITION_MODEL=base              # tiny/base/small/...
# SPEECH_RECOGNITION_METHOD=sensevoice     # FunASR SenseVoice（多语）
# SPEECH_RECOGNITION_METHOD=whisper_local  # 原版 openai-whisper
```

Docker 默认镜像为 CPU；首次运行会下载模型。有 NVIDIA 时用 `./docker-start.sh gpu`；可用 `WHISPER_DEVICE` / `FASTER_WHISPER_DEVICE` 强制 `cpu`/`cuda`，CPU 上可用 `FASTER_WHISPER_COMPUTE_TYPE=int8`。

**Docker 构建很慢或 apt 失败？**  
首次构建需下载 PyTorch 等大依赖，属正常。若 `apt` 报 `502` / 连不上镜像源，稍后重试，或更换 Dockerfile 中的 `DEBIAN_MIRROR`（如清华 `mirrors.tuna.tsinghua.edu.cn`）。

**修改后端代码后 Docker 不生效？**  
生产镜像把代码打进镜像，需重新构建：`docker compose build autoclip && docker compose up -d`。开发热更新请用 `./docker-start.sh dev`。

**YouTube 下载失败？**  
yt-dlp 常需登录 Cookie。**Docker 内无法读取本机 Chrome**：在链接导入页上传从已登录 youtube.com 导出的 `cookies.txt`（扩展如 Get cookies.txt LOCALLY），文件保存在 `data/cookies/youtube.txt`。本机模式可选浏览器 Cookie。Cookie 过期后需重新导出上传。

若日志出现 `n challenge solving failed` / `Only images are available`：生产镜像需带 **Node.js ≥ 20**（当前 Dockerfile 已从 `node:22` 拷入）。请重建镜像：`docker compose build autoclip && docker compose up -d`，并确认容器内 `node -v`。

**YouTube 投稿？**  
在 Google Cloud 创建 OAuth 客户端，将 Client ID/Secret 写入 `.env`，回调地址与 `YOUTUBE_REDIRECT_URI` 一致。

**端口占用？**  
生产 Docker 使用 `8000`、`6379`；开发另需 `3000`。先停掉本机已占用的 uvicorn / vite / redis。

---

## 支持

- [Issues](https://github.com/123mlly/autoclip/issues)
- [Discussions](https://github.com/123mlly/autoclip/discussions)
- 文档目录：[docs/](docs/)

---

## License

[MIT](LICENSE)
