"""FastAPI エントリポイント。

Phase 0 の役割は最小限:
- `/healthz`        … コンテナの liveness / readiness プローブ用 (infra が参照)
- `/api/health`     … フロントが Vite プロキシ経由で叩く疎通確認用

本番 (コンテナ) では frontend/dist が同梱されるので、存在すれば SPA として配信する。
ローカル開発では dist が無いので配信はスキップし、フロントは Vite dev server が出す。
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.learners import router as learners_router
from app.turns import router as turns_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """起動時に DB テーブルを用意する。

    Phase 0-3 の「外部サービスが無くても起動する」方針を保つため、DB に繋がらなくても
    警告ログだけ出して起動は続ける (DB を使うエンドポイントは呼び出し時にエラーになる)。
    """
    from app.db import init_db

    try:
        init_db()
    except Exception as e:  # noqa: BLE001 - 起動はブロックしない (DB 未起動でも音声機能は動く)
        logger.warning("DB の初期化に失敗しました (DB エンドポイントは利用不可): %s", e)
    yield


app = FastAPI(title="音声AI日本語チューター API", version="0.1.0", lifespan=lifespan)

app.include_router(turns_router)
app.include_router(learners_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """インフラのヘルスチェック用。常に 200 を返す。"""
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, object]:
    """フロントの疎通確認用 (Vite プロキシ /api 経由)。"""
    from app.config import settings

    return {
        "status": "ok",
        "service": "backend",
        "scoring_ready": settings.azure_ready(),
        "conversation_ready": settings.bedrock_ready(),
    }


# --- ビルド済み SPA の配信 (存在する場合のみ) ---
# backend/ から見た frontend/dist を探す。コンテナでは同梱される。
_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if _DIST_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=_DIST_DIR / "assets"),
        name="assets",
    )

    @app.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(_DIST_DIR / "index.html")
