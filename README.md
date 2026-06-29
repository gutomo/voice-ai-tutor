# 音声AI日本語チューター (LPK向けデモ)

LPK (インドネシアの職業訓練機関) 向けの、音声AI日本語チューターのデモ。
候補者はモバイルブラウザで録音 → Azure で発音採点 → Bedrock Claude が会話・採点 → 画面に即時フィードバック。
レッスンのまとめはメールで届く。教師ダッシュボードで「介護日本語評価試験の合格ライン到達度」を可視化するのが価値の核。

- 設計: [docs/DESIGN.md](docs/DESIGN.md)
- フェーズ別の実行手順: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md)
- 行動規範 (Claude Code 用): [CLAUDE.md](CLAUDE.md)

現在のステータス: **Phase 0 (スキャフォールド) 完了**。空のアプリが起動し、`/healthz` が通る。

## 構成

| パス | 役割 |
|---|---|
| `backend/` | FastAPI (API, 音声処理, 採点, メール)。uv で管理。 |
| `frontend/` | React + Vite + TypeScript (モバイルファースト)。 |
| `infra/` | Terraform (Azure Container Apps + AWS Bedrock/SES のハイブリッド)。 |
| `docs/` | 設計書とビルド計画。 |

開発時はフロント (:5173) からの `/api/*` を Vite が FastAPI (:8000) へプロキシする。
本番は単一コンテナで FastAPI がビルド済み SPA を同一オリジンで配信する ([Dockerfile](Dockerfile))。

## 必要なもの

- [uv](https://docs.astral.sh/uv/) (Python 3.12 は uv が自動取得)
- Node.js 22 / npm
- Docker + Docker Compose (ローカル Postgres 用)
- ffmpeg (Phase 2 の音声変換で使用。Windows: `winget install Gyan.FFmpeg`)

## ローカル起動

```bash
# 1) Postgres を起動
docker compose up -d

# 2) バックエンド (→ http://localhost:8000)
cd backend
uv sync
uv run uvicorn app.main:app --reload

# 3) フロントエンド (→ http://localhost:5173)
cd frontend
npm install
npm run dev
```

ブラウザで http://localhost:5173 を開き、画面に「Status backend: terhubung ✓」が出れば疎通OK。
直接の確認は `curl http://localhost:8000/healthz` → `{"status":"ok"}`。

## テスト・lint

```bash
cd backend
uv run pytest                                  # 全テスト
uv run pytest tests/test_health.py::test_healthz  # 単体
uv run ruff check . && uv run black .          # lint / format
```

## 環境変数

`.env.example` をコピーして `backend/.env` を作る (秘密情報はコミット禁止)。
Phase 0 ではどれも未設定でアプリは起動する。各 Phase で必要になったら埋める。

## デプロイ

Azure Container Apps へのデプロイは [infra/](infra/) の Terraform を参照 (デモはゼロスケールで、商談時だけ起動)。
ブートストラップ順などの詳細は [CLAUDE.md](CLAUDE.md) の「デプロイ」節にある。
