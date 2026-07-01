# 音声AI日本語チューター (LPK向けデモ)

LPK (インドネシアの職業訓練機関) 向けの、音声AI日本語チューターのデモ。
候補者はモバイルブラウザで録音 → Azure で発音採点 → Bedrock Claude が会話・採点 → 画面に即時フィードバック。
レッスンのまとめはメールで届く。教師ダッシュボードで「介護日本語評価試験の合格ライン到達度」を可視化するのが価値の核。

- 設計: [docs/DESIGN.md](docs/DESIGN.md)
- フェーズ別の実行手順: [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md)
- 行動規範 (Claude Code 用): [CLAUDE.md](CLAUDE.md)

現在のステータス: **Phase 5 (教師ダッシュボード) 実装完了**。発音ドリル＋介護ロールプレイ (Phase 2/3) の採点を Postgres に蓄積し (Phase 4)、教師ダッシュボードで学習者ビュー (推定レベル・発音ヒートマップ・合格ライン到達度の推移・会話ログ＋再生) とコホートビュー (合格見込み分布・要フォロー自動フラグ) を表示する。会話・採点は Bedrock Claude、発音採点・TTS は Azure ja-JP。

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

## 録音ページ (Phase 1)

トップページが録音UIになっている。フロー:

1. 大きな録音ボタンをタップ → マイク許可 → 録音 (WebM/Opus)。
2. もう一度タップで停止 → その場で再生して確認。
3. 「Kirim」で `POST /api/turn` にアップロード → サーバに保存され、サーバ側の音声も再生できる。

保存先は `backend/uploads/`（`.gitignore` 済み）。Phase 2 でこの音声を ffmpeg → Azure 発音評価へ渡す。

### 実機 (Android Chrome) で試す

マイク API (`getUserMedia`) は**セキュアコンテキスト限定**。`localhost` では動くが、スマホから LAN の
`http://192.168.x.x:5173` を開くとマイクがブロックされる。そこで cloudflared で https URL を作る。

```bash
# 一度だけ: インストール (Windows)
winget install Cloudflare.cloudflared

# バックエンド・フロントを起動した状態で、別ターミナルで:
cloudflared tunnel --url http://localhost:5173
# -> https://<ランダム>.trycloudflare.com が出る。これをスマホの Chrome で開く。
```

スマホでマイクを許可 → 録音 → 「Kirim」→ 「Berhasil terkirim ✓」と表示されればOK。

代替: オフラインで済ませたい場合は `@vitejs/plugin-basic-ssl` を入れて `npm run dev` を https 化する
（スマホで証明書の警告をタップで通す必要がある）。

## 発音採点 (Phase 2)

アップロード後、フロントが自動で `POST /api/turn/{id}/score` を呼び、画面にスコアを出す。

- 変換: 受信音声を ffmpeg で WAV(16k/mono/16bit) に変換 (`backend/app/audio.py`)。
- 採点: Azure ja-JP の **scripted** Pronunciation Assessment (`backend/app/speech.py`)。参照テキストは
  `backend/app/scenarios.py` の介護モデル文。Accuracy / Fluency / Completeness / 総合スコアを返す。
- ja-JP は **Prosody を返さない**。また音素名が意味を持たないため、要練習リストは**単語**単位
  (AccuracyScore < 60 = Azure の Mispronunciation 判定) で出す。

### 必要なもの

- **ffmpeg**（[必要なもの](#必要なもの)参照）が PATH にあること。
- **Azure Speech の鍵**: `backend/.env` に `AZURE_SPEECH_KEY` / `AZURE_SPEECH_REGION=japaneast`。
  デモ全体が **F0 無料枠 ($0)** に収まる。未設定だと採点APIは 503、画面は「未設定」と表示する。

Azure リソース作成 (一度だけ、CLI 例):

```bash
az cognitiveservices account create \
  --name speech-tutor-dev --resource-group rg-voice-tutor \
  --kind SpeechServices --sku F0 --location japaneast --yes
```

ポータルなら「リソースの作成 → Speech → リージョン Japan East → 価格レベル F0」。
作成後「キーとエンドポイント」から KEY 1 と Location をコピーして `backend/.env` に入れる。

### 実 Azure を使うテスト (任意)

ユニットテストは Azure/ffmpeg をスタブする。実呼び出しは 1 本だけ、明示フラグで:

```bash
cd backend
RUN_AZURE_E2E=1 AZURE_E2E_AUDIO=/path/to/recording.webm uv run pytest tests/test_e2e_azure.py
```

## 会話ループ・ルーブリック採点 (Phase 3)

画面上部の2タブで切り替える。説明は Bahasa、練習・採点対象は日本語。

- **Latihan pengucapan** (発音ドリル): 介護モデル文5フレーズを順に復唱 → `POST /api/turn/{id}/score` で発音スコア。
- **Percakapan** (ロールプレイ): 利用者役「田中さん」の口火 (Azure TTS で再生) に音声で応答 → `POST /api/turn/{id}/evaluate` (mode=roleplay)。

`evaluate` (roleplay) の内部処理:

1. STT で学習者の発話を文字起こし → その文を参照に scripted 発音採点 (DESIGN §3 の二段採点、`app/scoring.py`)。
2. Bedrock Claude でルーブリック採点 (`app/bedrock.py`、文法/語彙/敬語 0-5＋タスク達成＋CEFR、**JSONのみ**・失敗時リトライ)。
3. 発音(A)＋会話(B×20)＋タスク達成(C) を合成し、合格ライン到達度(%)・推定CEFR/JLPT を返す (`app/combine.py`)。

利用者役の発話生成は `POST /api/conversation/reply`、TTS 単体は `POST /api/tts` (WAV を返す)。

### 必要なもの

- **AWS の鍵 ＋ `BEDROCK_MODEL_ID`**: `backend/.env` に設定。未設定だと会話・採点APIは 503、画面は「未設定」と表示する。
- Bedrock コンソールで対象 Claude モデルの**アクセス有効化**が事前に必要 (一度だけ)。
- 会話の即時フィードバックは画面で完結する。Bedrock へ越境するのは軽いテキストだけ (音声は Azure に同居)。

### 実 Bedrock を使うテスト (任意・課金注意)

ユニットテストは Bedrock/Azure をスタブする。実呼び出しは 1 本だけ、明示フラグで (Bedrock は従量課金):

```bash
cd backend
RUN_BEDROCK_E2E=1 uv run pytest tests/test_e2e_bedrock.py
```

## 永続化・合格ライン推定 (Phase 4)

`POST /api/turn/{id}/evaluate` に `session_id` を渡すと、採点結果を Postgres に保存し、学習者の全ターンから
合格ライン到達度 (%)・推定 CEFR/JLPT を作り直して返す (= デモの山場)。学習者・セッションの API は
`/api/learners`・`/api/sessions`・`/api/learners/{id}/turns` (`app/learners.py`)。スキーマは ORM の `create_all`
で用意し、Alembic は後回し (`app/models.py` / `app/db.py`)。`DATABASE_URL` 未設定でも起動は継続する
(DB を使うエンドポイントだけ実行時にエラー)。

## 教師ダッシュボード (Phase 5)

画面上部のロール切替で **📱 Siswa (学習者アプリ)** ↔ **🎓 Guru (教師ダッシュボード)** を行き来する
(デモ台本で画面を切り替える操作)。ダッシュボードは Phase 4 の API をそのまま読む (新規エンドポイントなし)。

- **コホートビュー**: クラスの集計 (人数・平均到達度・要フォロー数)、合格見込み分布 (20点刻み)、
  **要フォロー学習者の自動フラグ** (合格ライン到達度 < 50%)、学習者一覧 (行クリックで詳細へ)。
- **学習者ビュー**: 推定レベル (CEFR/JLPT)、合格ライン到達度の**推移** (ターン累積)、
  **発音ヒートマップ** (要練習語を accuracy で色分け)、**会話ログ** (各ターンの転写・スコア・ルーブリック＋音声再生)。
- 集計ロジックは `frontend/src/dashboard/metrics.ts` に集約 (合格ライン計算は `app/combine.py` と整合)。
  チャートは依存を増やさず CSS バー＋SVG スパークライン (`frontend/src/dashboard/charts.tsx`)。

### デモデータの投入 (シード)

ダッシュボードを実データで見せるためのデモコホート (6名・うち2名は要フォロー) を投入する。スコアは
`app/combine.py` の本番ロジックを通すのでダミー直書きではない。各ターンに無音 WAV を置くので会話ログの
再生 UI も成立する。再実行しても同名のデモ学習者を作り直すだけ (他の学習者には触れない)。

```bash
cd backend
uv run python -m app.seed     # 既定の DATABASE_URL (docker compose の Postgres) に投入
```

投入後、フロントの 🎓 Guru タブを開くと 6名のクラスが表示され、Andi・Putra が要フォローにフラグされる。

## デプロイ

Azure Container Apps へのデプロイは [infra/](infra/) の Terraform を参照 (デモはゼロスケールで、商談時だけ起動)。
ブートストラップ順などの詳細は [CLAUDE.md](CLAUDE.md) の「デプロイ」節にある。
本番イメージには ffmpeg と Azure SDK のランタイムlibs (libssl3/libasound2) を同梱済み ([Dockerfile](Dockerfile))。
