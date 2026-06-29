"""FastAPI エントリポイント。

Phase 0 の役割は最小限:
- `/healthz`        … コンテナの liveness / readiness プローブ用 (infra が参照)
- `/api/health`     … フロントが Vite プロキシ経由で叩く疎通確認用

本番 (コンテナ) では frontend/dist が同梱されるので、存在すれば SPA として配信する。
ローカル開発では dist が無いので配信はスキップし、フロントは Vite dev server が出す。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="音声AI日本語チューター API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """インフラのヘルスチェック用。常に 200 を返す。"""
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    """フロントの疎通確認用 (Vite プロキシ /api 経由)。"""
    return {"status": "ok", "service": "backend"}


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
