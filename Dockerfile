# AutoClip Dockerfile
# 多阶段构建：前端静态资源 + 后端 API（同源 :8000）

ARG DEBIAN_MIRROR=mirrors.aliyun.com

# 第一阶段：构建前端
FROM node:18-slim AS frontend-builder

ARG DEBIAN_MIRROR=mirrors.aliyun.com
WORKDIR /app/frontend

RUN sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s/security.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list 2>/dev/null || true \
    && sed -i "s/security.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# 第二阶段：安装 Python 依赖（不装 ffmpeg，减小构建体积与耗时）
FROM python:3.10-slim AS backend-builder

ARG DEBIAN_MIRROR=mirrors.aliyun.com
# 镜像源超时可换：--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=mirrors.aliyun.com
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
ENV PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}
ENV PIP_DEFAULT_TIMEOUT=180
ENV PIP_RETRIES=10

WORKDIR /app

RUN sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s/security.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list 2>/dev/null || true \
    && sed -i "s/security.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# 业务依赖与 ASR 重依赖分层：超时更少、缓存更稳
RUN grep -vE '^(openai-whisper|faster-whisper)$' requirements.txt > /tmp/requirements.base.txt \
    && pip install --no-cache-dir --default-timeout=180 --retries=10 -r /tmp/requirements.base.txt \
    && pip install --no-cache-dir --default-timeout=300 --retries=10 faster-whisper openai-whisper \
    && rm -rf /tmp/requirements.base.txt

# 第三阶段：运行镜像（仅运行时需要的系统包）
FROM python:3.10-slim

ARG DEBIAN_MIRROR=mirrors.aliyun.com
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# ffmpeg 只装一次；--no-install-recommends 避免拉 mesa/gtk 等可选依赖
RUN sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s/security.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list 2>/dev/null || true \
    && sed -i "s/security.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list 2>/dev/null || true \
    && apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# yt-dlp EJS 求解 YouTube n challenge 需要 Node ≥ 20（前端构建阶段的 Node 不会进入本镜像）
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
RUN node -v

WORKDIR /app

COPY --from=backend-builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY *.sh ./
COPY env.example .env

RUN mkdir -p data/projects data/uploads data/temp data/output logs uploads \
    && chmod +x *.sh docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/ || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
