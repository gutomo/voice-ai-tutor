# CLAUDE.md — 音声AI日本語チューター（LPK向けデモ）

> このファイルはClaude Codeがセッション開始時に自動で読み込みます。プロジェクトの「行動規範」です。
> フェーズ別の実行手順は `docs/BUILD_PLAN.md` を参照（着手前に必ず開く。CLAUDE.mdには重複させない）。
> 設計詳細（シナリオ・採点ロジック・ダッシュボード・デモ台本）は `docs/DESIGN.md` を参照。BUILD_PLAN.md が §1〜§6 で参照している。
> 文章スタイルは `.clauderules` に従う（em ダッシュを使わない。読点・セミコロン・句点で区切る）。

## プロジェクト概要
- LPK（インドネシアの職業訓練機関）向け、音声AI日本語チューターの**デモ**を作る。
- 候補者はモバイルブラウザで録音 → Azureで発音採点 → Claudeが会話＆ルーブリック採点 → **画面に即時フィードバック**。レッスンのまとめは**メール**。
- 教師ダッシュボードで「介護日本語評価試験の合格ライン到達度」を可視化するのが価値の核。
- **WhatsAppは使わない**（WABAの審査を避けるため）。Web録音＋メールで代替。WhatsApp連携はPhase 2（今回スコープ外）。
- デモシナリオは介護「朝の声かけ＋バイタルチェック」1本。ターゲットレベルはA2/N4。

## 技術スタック（確定）
- Backend: Python 3.12 + FastAPI（パッケージは uv で管理）
- Frontend: React + Vite + TypeScript（モバイルファースト）
- 音声認識・発音採点: Azure AI Speech（ja-JP、STT ＋ Pronunciation Assessment）
- 会話・採点: Amazon Bedrock の Claude（Sonnet）。利用者役の会話生成とルーブリック採点に使用
- 音声合成: Azure Neural TTS（ja-JP）
- DB: PostgreSQL
- 音声変換: ffmpeg
- メール: Amazon SES（または SendGrid）
- バイリンガル: 説明UIは Bahasa Indonesia、学習対象は日本語

## リポジトリ構成
> Phase 0（スキャフォールド）完了。下記はすべて実在する。
```
.
├── CLAUDE.md           # これ（行動規範）
├── README.md           # セットアップ・起動手順
├── .clauderules        # 文章スタイル（em ダッシュ禁止）
├── .env.example        # 環境変数の雛形（コピーして backend/.env を作る）
├── docker-compose.yml  # ローカルの Postgres（API は uv で直接起動）
├── Dockerfile          # 本番用の単一コンテナ（フロントをビルド → FastAPI が SPA 配信）
├── .dockerignore
├── backend/            # FastAPI（app/main.py に /healthz・/api/health、app/config.py、tests/）
├── frontend/           # React + Vite + TS（mobile-first、/api を :8000 へプロキシ）
├── docs/
│   ├── DESIGN.md       # 設計書（UX・採点ロジック・ダッシュボード・デモ台本）
│   └── BUILD_PLAN.md   # フェーズ別タスク（着手前に必ず読む）
├── infra/              # Terraform（Azure Container Apps へデプロイ）
└── .github/workflows/  # CI（ruff・black・pytest／npm build）
```

## 開発コマンド（Phase 0 で確定）
- `docker compose up -d` … Postgres 起動（ローカルは DB のみ compose、API は uv で直接起動）
- `cd backend && uv sync && uv run uvicorn app.main:app --reload` … API 起動（→ :8000）
- `cd frontend && npm install && npm run dev` … フロント起動（→ :5173、`/api` を :8000 へプロキシ）
- `cd backend && uv run pytest` … テスト（単体: `uv run pytest tests/test_health.py::test_healthz`）
- `cd backend && uv run ruff check . && uv run black .` … lint / format
- `cd frontend && npm run build` … フロントの型チェック＋本番ビルド（CI と同じ）
- ヘルス確認: `curl http://localhost:8000/healthz` → `{"status":"ok"}`

## 環境変数（.env.example を参照）
- `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION`
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`（Bedrock ＋ SES）
- `BEDROCK_MODEL_ID`（例: anthropic.claude-sonnet 系の推論プロファイルID）
- `DATABASE_URL`
- `EMAIL_SENDER`（SESで検証済みの送信元アドレス）
- 秘密情報は `.env` のみに置く。**コミット禁止**。`.env.example` だけをコミットする。

## 実装で必ず守る点（高シグナル）
- **ブラウザ音声は WebM/Opus → 必ず WAV へ変換してから Azure へ**。発音評価は WAV(16kHz, mono, 16bit PCM) が最も確実。
  変換: `ffmpeg -i input.webm -ar 16000 -ac 1 -c:a pcm_s16le output.wav`
- **発音採点は scripted assessment を基本に**。復唱ドリルは参照テキスト（モデル文）が既知なので音素レベルまで取れる。**ja-JP では prosody スコアは出ない**（prosody は en-US のみ）。Accuracy / Fluency / Completeness を主指標にする。自由発話は「先に STT → その文を参照に scripted」で精度を担保する。
- **会話・採点の Claude 出力は必ず構造化JSON**（自由記述させない）。スキーマは `docs/BUILD_PLAN.md` の Phase 3 を参照。パース失敗時はリトライする実装にする。
- **メールは「まとめ」と「次回リンク」だけ**。ターン毎の即時フィードバックは必ず画面側で完結させる（メール往復にしない）。
- **2言語を混ぜない**：学習者への説明・UIラベルは Bahasa、練習・モデル音声・採点対象は日本語。

## コーディング規約
- Python: 型ヒント必須、ruff ＋ black、テストは pytest。外部API（Azure / Bedrock / SES）はテストでスタブ化する。
- React: 関数コンポーネント ＋ Hooks、TypeScript。
- コンテナ化するなら ARM64 を優先。実インフラが必要になったら Terraform（ただしデモではローカル優先、IaCは後回し）。
- 小さくコミットする。各 Phase の受け入れ基準を満たしたらコミットする。

## デプロイ（Azure Container Apps、ハイブリッド構成）
- デモは **Azure Container Apps** にデプロイ（ゼロスケールで、商談時だけ起動）。会話・採点は **Bedrock Claude を維持**（ハイブリッド）。重い音声は Azure Speech に同居し、AWS へは軽いテキストだけ越境する。
- `infra/` に Terraform 一式。`terraform init && terraform plan && terraform apply` で構築。
- **手動の前提（一度だけ）**：(1) AWS SES で `EMAIL_SENDER` を検証、(2) AWS Bedrock で Claude モデルのアクセスを有効化、(3) Bedrock と SES を許可する IAM キーを発行。
- **ブートストラップ順**：(1) `terraform apply`（プレースホルダ image で起動）→ (2) `az acr build` で本番イメージを ACR へ push → (3) `az containerapp update --image <acr>/api:tag` で差し替え。Terraform は image を `ignore_changes` するので戻らない。
- **コスト注意**：PostgreSQL Flexible Server は常時稼働でゼロスケールしない。デモ間は停止するか、`DATABASE_URL` を外部（Neon 無料枠など）に向けると idle コストがゼロになる。
- 秘密情報は Container App の secret に格納する。**Terraform state に含まれる**ので state は安全に保管する（本番は Key Vault 参照へ切替）。

## 着手前に確認すること（escalation）
- 課金が発生するクラウドリソースの新規作成、または有料API呼び出しは、実行前に必ず確認を取る。
- 既存ファイルを変更・削除する前に確認する。
- 重い依存を追加する前に確認する。
- Azure Speech SDK の使い方に迷ったら、Microsoft Learn MCP（接続済み）または docs.microsoft.com で最新仕様を確認する。

## デモの完了条件（Definition of Done）
- 録音ページで音声を1本録ると、数秒で画面に発音スコア（Accuracy 等）が出る。
- そのターンが学習者プロファイルに反映され、教師ダッシュボードの「合格ライン到達度」が動く（＝ money shot）。
- 介護シナリオ1本を5から6ターン完走でき、終了時に学習者と教師へまとめメールが届く。
- すべてローカルで再現でき、README の手順で別環境でも起動できる。
