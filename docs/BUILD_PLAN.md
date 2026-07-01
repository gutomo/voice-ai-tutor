# BUILD_PLAN.md — フェーズ別ビルド計画

進め方：各 Phase の先頭にゴールと受け入れ基準を置く。タスクは `- [ ]` で管理し、完了したら `- [x]` に更新すること。1 Phase = 1コミット以上。設計の背景は `docs/DESIGN.md` を参照。

着手時のおすすめ：Phase 0 はプランモードで計画を出してから実行する。各 Phase の終わりに、このファイルのチェックを更新し、`CLAUDE.md` の「開発コマンド」も実態に合わせて直す。

---

## Phase 0 — スキャフォールド
**ゴール:** 空のアプリが起動し、health が通る。
- [x] リポジトリ構成を作成（backend/ frontend/ docs/ infra/）
- [x] backend: FastAPI 雛形 ＋ `GET /healthz`（＋ `/api/health`）
- [x] frontend: Vite + React + TS 雛形（モバイル幅で表示確認、`/api` をプロキシ）
- [x] docker-compose.yml に Postgres
- [x] `.env.example` を作成（CLAUDE.md の変数一覧に対応）
- [x] ffmpeg がコンテナ/ローカルに存在することを確認
- [x] 追加: 単一コンテナ Dockerfile、GitHub Actions CI、README
- **受け入れ:** `uvicorn` と `npm run dev` が両方起動し、`/healthz` が 200 を返す。

## Phase 1 — Web録音ページ（デモの入口）
**ゴール:** スマホのブラウザでタップ録音 → サーバへアップロード → 再生できる。
- [x] モバイルファーストの録音UI（大きな録音ボタン、録音中インジケータ、再生ボタン）
- [x] MediaRecorder で録音（`audio/webm;codecs=opus`、非対応端末は既定にフォールバック）
- [x] `POST /api/turn`（multipart）で音声を送信し、サーバに保存（＋ `GET /api/turn/{id}/audio` で再生）
- [ ] Android Chrome の実機で確認（マイク許可 → 録音 → アップロード）← cloudflared 経由でテスト可能（README 参照）。手動確認待ち
- **受け入れ:** 実機で録音 → アップロード成功 → サーバに保存される。

## Phase 2 — 音声パイプライン ＋ Azure発音採点
**ゴール:** アップロードされた音声から発音スコアが返る。
- [x] 受信音声を ffmpeg で WAV(16k / mono / 16bit) に変換（`app/audio.py`）
- [x] Azure Speech STT（ja-JP）で文字起こし（scripted では認識結果 transcript を併せて返す）
- [x] Azure Pronunciation Assessment（ja-JP, scripted, 参照テキスト＝モデル文）（`app/speech.py`）
- [x] Accuracy / Fluency / Completeness ＋ 要練習リストを返す（ja-JP は音素名が無いため**単語**単位。`app/parsing.py`）
- [x] サンプルWAVでユニットテスト（Azureはスタブ化。実呼び出しは `test_e2e_azure.py` を 1 本だけゲート）
- [x] 追加: `POST /api/turn/{id}/score`、フロントに発音スコア表示（ScoreCard）、Dockerfile にランタイムlibs
- [x] 実 Azure (F0) で 1 回確認（鍵を `backend/.env` に格納）。TTS で参照文を合成→`score_turn_sync` で採点する自動往復で疎通確認。結果: transcript 一致, accuracy 95 / fluency 80 / completeness 100 / pron 87
- **受け入れ:** 既知のモデル文に対し、復唱音声のスコアと要練習の単語が取得できる。

## Phase 3 — 会話ループ ＋ ルーブリック採点（Bedrock Claude）
**ゴール:** 介護シナリオの1レッスンが会話として成立し、採点される。
- [x] シナリオ定義：介護「朝の声かけ＋バイタルチェック」。モデル文5つ ＋ 利用者役ペルソナ(田中さん) ＋ ロールプレイ1ターン（`app/scenarios.py`）
- [x] 利用者役の発話を Bedrock Claude で生成（`app/bedrock.py` の `generate_patient_line`、Converse API、JSON失敗時リトライ）。`POST /api/conversation/reply`
- [x] ルーブリック採点を Claude で実行（**出力は下記JSONのみ**、`score_rubric` ＋ 0-5クランプ）
- [x] スコア合成：発音(A) ＋ 会話(B×20) ＋ タスク達成(C) → 学習者スコア＋合格ライン到達度（`app/combine.py`）
- [x] 返信音声を Azure TTS（ja-JP NanamiNeural）で生成（`app/tts.py`）。`POST /api/tts`、フロントで再生
- [x] 追加: `POST /api/turn/{id}/evaluate`（scripted=発音 / roleplay=STT二段＋ルーブリック＋合成）、フロントに会話タブ＋RubricCard、ユニットテスト（外部APIはスタブ）、実呼び出しは `test_e2e_bedrock.py` を 1 本だけゲート
- [x] 実 Bedrock で 1 回確認。`RUN_BEDROCK_E2E=1 uv run pytest tests/test_e2e_bedrock.py` → 2 passed（会話生成・ルーブリック採点の往復OK）。**注意: 基盤モデルID `anthropic.claude-sonnet-4-6` は on-demand 不可（ValidationException）。推論プロファイルID `us.anthropic.claude-sonnet-4-6` を `BEDROCK_MODEL_ID` に設定する**
- **受け入れ:** 5から6ターンを完走でき、各ターンで構造化スコアが返る（発音ドリル5フレーズ＋ロールプレイ1ターン。実 Bedrock で往復検証済み）。

ルーブリック採点の出力スキーマ（Claude にこの形式のJSONだけを返させる）:
```json
{
  "task_completed": true,
  "task_reason": "声かけから測定までの流れを最後まで成立させた",
  "grammar": 4,
  "vocabulary": 4,
  "politeness": 4,
  "cefr_estimate": "A2",
  "feedback_ja": "自然な応答です。次は『毛布をお持ちしますね』まで言えると満点です",
  "feedback_id": "Jawaban Anda natural. Lain kali coba sampai 'mouhu wo omochi shimasu ne'.",
  "model_answer_ja": "毛布をもう1枚お持ちしますね"
}
```
grammar / vocabulary / politeness は 0 から 5。feedback_ja は日本語、feedback_id は Bahasa Indonesia。

## Phase 4 — 永続化 ＋ 合格ライン推定
**ゴール:** 学習者の履歴が貯まり、合格ライン到達度が出る。
- [x] Postgres スキーマ作成（SQLAlchemy 2.0 ORM `app/models.py`：learners / sessions / turns / learner_profile。同期エンジン `app/db.py` は本番 Postgres・テスト SQLite。weak_phonemes と rubric は jsonb／SQLite では JSON にフォールバック。`init_db()` の create_all で用意し Alembic は後回し）
- [x] 各ターンのスコアを保存し、学習者プロファイルを更新（サービス層 `app/persistence.py` の `record_turn`：turn_id を主キーに upsert → 学習者の全ターンからプロファイル再計算。`/api/turn/{id}/evaluate` に `session_id` を渡すと保存し更新後プロファイルを返す＝money shot）
- [x] 介護日本語評価試験 の合格ライン到達度(%) を推定して保存（純関数 `app/profile.py`：combined_score 平均 − オフセットで passline、CEFR は直近ルーブリック優先。係数は `app/combine.py` に集約）
- [x] 追加: 学習者・セッションのエンドポイント（`app/learners.py`：`/api/learners`・`/api/sessions`・`/api/learners/{id}/turns`）、`main.py` の lifespan で起動時 `init_db`（DB 未接続でも起動は継続）、ユニットテスト（`test_persistence.py`／`test_profile.py`／`test_learners_endpoint.py`、DB は in-memory SQLite・外部 API はスタブ）
- [x] 実 Postgres（docker compose の postgres:16）で 1 回確認。永続化層を通した往復スモークで autoincrement・timezone・JSONB ラウンドトリップ・upsert・到達度更新を検証（69→72→上書きで 55）
- **受け入れ:** 同一学習者の複数ターンが蓄積し、到達度が更新される（SQLite ユニットテスト ＋ 実 Postgres スモークで検証済み）。

データモデル（最小）:
```
learners(id, name, native_lang, target_sector, created_at)
sessions(id, learner_id, scenario, started_at, ended_at, summary_sent_at)
turns(id, session_id, turn_no, audio_path, transcript,
      pron_accuracy, pron_fluency, pron_completeness, weak_phonemes jsonb,
      rubric jsonb, combined_score, created_at)
learner_profile(learner_id, cefr_estimate, jlpt_estimate,
      kaigo_passline_pct, updated_at)
```

## Phase 5 — 教師ダッシュボード（まずモック → 実データ）
**ゴール:** 教師が学習者とクラスの状態を見られる。
- [x] 学習者ビュー：推定レベル(CEFR/JLPT)、発音ヒートマップ（要練習語を accuracy で色分け）、合格ライン到達度の推移（ターン累積）、会話ログ ＋ 音声再生（`frontend/src/dashboard/LearnerView.tsx`）
- [x] コホートビュー：合格見込み分布（到達度の20点刻みヒストグラム）、要フォロー学習者の自動フラグ（到達度 < 50%）（`frontend/src/dashboard/CohortView.tsx`）
- [x] Phase 4 の API にそのまま接続（`/api/learners`＝プロファイル付き・`/api/learners/{id}/turns`・`/api/turn/{id}/audio`。新規エンドポイントは不要だった）。集計ロジックは `frontend/src/dashboard/metrics.ts` に集約（合格ライン計算は combine.py と整合）
- [x] 追加: デモコホートのシード `app/seed.py`（6名・うち2名要フォロー。スコアは combine.py 経由なので実計算と整合。各ターンに無音WAVを置き会話ログの再生UIを成立させる）＋テスト `tests/test_seed.py`、画面上部に学習者アプリ↔教師ダッシュボードのロール切替（`App.tsx`）、チャートは依存を増やさず CSS バー＋SVG スパークライン（`dashboard/charts.tsx`）
- [x] 検証: frontend ビルド＋oxlint、backend 全テスト、シードを通した実 API スモーク（`/api/learners` 6名・要フォロー2名・Dewi 64.8%・ターン5件・音声 audio/wav）
- **受け入れ:** デモ用学習者のスコアが、学習者ビューとコホートビューの両方に反映される（シード＋実 API スモークで検証済み。実ブラウザでの目視は手動確認）。

## Phase 6 — 結果メール
**ゴール:** セッション終了でメールが届く。
- [x] Amazon SES 連携（`app/emailer.py` の `send_email`：boto3 は遅延 import、認証情報は引数、一時エラーは retriable。テストではスタブ）
- [x] 学習者向けまとめメール（`build_learner_email`：発音/会話/合格ライン到達度 ＋ 要練習語 ＋ 次回リンク。説明は Bahasa 主・練習内容は日本語で混ぜない）
- [x] 教師向けレポート（`build_teacher_email`：当日サマリ＋到達度ランキング＋要フォロー<50%を自動フラグ。閾値は `combine.FOLLOWUP_PASSLINE_PCT` に集約）
- [x] セッション終了をトリガーに送信し、`summary_sent_at` を記録（`app/session_summary.py` の `finalize_session`：`/api/sessions/{id}/end` が呼ぶ。2通送って1通以上成功なら打刻。送信済みは skip、`?resend=true` で再送）
- [x] 追加: `Learner.email` 追加（未設定なら EMAIL_SENDER にフォールバック＝SES サンドボックスでも届く）、`teacher_email`/`app_base_url` 設定、`SessionEndResult`（送信ログ＝emails フィールド）、ユニットテスト（`test_emailer.py`＝本文の純関数、`test_session_end_email.py`＝送信・冪等・skip・404 を SES スタブで検証）
- [x] 実 SES で 1 回確認（us-east-1 サンドボックス。`gutomo999@gmail.com` を identity 検証し送信元/宛先に使用。Dewi のセッションを finalize → 学習者まとめ＋教師レポートの 2 通が MessageId 付きで送信され、`summary_sent_at` 打刻を確認）
- **受け入れ:** 終了時に2種類のメールが送られる（送信ログ＝`emails` で確認。SES スタブのユニットテスト ＋ 実 SES 往復で検証済み）。

## Phase 7 — デモ仕上げ
**ゴール:** 10から12分のライブデモが滞りなく回る（`docs/DESIGN.md` の §6 の台本）。
- [x] レッスン終了 → まとめメール送信を**学習者アプリの UI から**起こす（`frontend/src/SessionBar.tsx` の終了ボタン → `POST /api/sessions/{id}/end`。スクリプト/curl 不要）。セッションは `SessionProvider` が保持し（`session-context.ts`）、固定のデモ学習者「Live Demo (Siswa)」を再利用。ドリル・ロールプレイの各ターンは `session_id` 付き `evaluate` でそのセッションに保存され、録音のたびに合格ライン到達度が動く（＝money shot）。送信ログ（宛先・status）は押下後に画面表示。ロール切替をまたいでもセッションは維持する
- [x] 実ブラウザで通し確認（Chrome で 📱Siswa → ドリル1ターンを録音 → Azure 発音採点 Accuracy 95 → 合格ライン到達度 81.8%／CEFR B1・JLPT N3 に更新 → 「Akhiri sesi & kirim ringkasan」で `finalize_session` を起動 → 学習者まとめ＋教師レポートの 2 通が実 SES（us-east-1 サンドボックス、宛先は EMAIL_SENDER フォールバック）で送信され、`summary_sent_at` 打刻と受信を確認。2026-07-01）
- [ ] デモ用の学習者1名 ＋ クラス（要フォロー2名）をシード
- [ ] 「わざと少し外す」発音の見せ場を再現確認
- [ ] 台本どおりに通しリハーサル
- **受け入れ:** money shot（録音 → 画面スコア → ダッシュボード反映）が安定して再現できる。
