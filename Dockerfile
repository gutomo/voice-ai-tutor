# 単一コンテナ構成: フロントを静的ビルドし、FastAPI が同梱 SPA を配信する。
# Azure Container Apps はこのイメージを 8000 番で起動する (infra/ 参照)。
# ARM64 を優先する場合は: docker build --platform linux/arm64 -t api .

# --- Stage 1: フロントをビルド ---
FROM node:22-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: バックエンド + ビルド済み SPA ---
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# ffmpeg: 音声を WAV へ変換 (必須)。
# ca-certificates/libssl3/libasound2: Azure Speech SDK のネイティブ .so が実行時に必要
# (これらが無いと import 時に 'cannot load libssl.so.3' で落ちる)。
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        libssl3 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /srv/backend

# 依存だけ先に入れてレイヤキャッシュを効かせる (本番なので dev 群は除外)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

# アプリ本体
COPY backend/ ./
RUN uv sync --no-dev --frozen

# main.py は repo_root/frontend/dist を探すので /srv/frontend/dist に置く
COPY --from=frontend-build /build/frontend/dist /srv/frontend/dist

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
