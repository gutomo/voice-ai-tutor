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
- [ ] 実 Azure (F0) で 1 回確認（鍵を `backend/.env` に入れて録音→採点）← 手動確認待ち
- **受け入れ:** 既知のモデル文に対し、復唱音声のスコアと要練習の単語が取得できる。

## Phase 3 — 会話ループ ＋ ルーブリック採点（Bedrock Claude）
**ゴール:** 介護シナリオの1レッスンが会話として成立し、採点される。
- [ ] シナリオ定義：介護「朝の声かけ＋バイタルチェック」。モデル文3つ ＋ 利用者役ペルソナ ＋ ロールプレイ1ターン（`docs/DESIGN.md` の §1, §2）
- [ ] 利用者役の発話を Bedrock Claude で生成（日本語、初級向けにやさしく）
- [ ] ルーブリック採点を Claude で実行（**出力は下記JSONのみ**）
- [ ] スコア合成：発音(A) ＋ 会話(B) ＋ タスク達成(C) → 学習者スコア（`docs/DESIGN.md` の §3）
- [ ] 返信音声を Azure TTS（ja-JP）で生成し、画面で再生
- **受け入れ:** 5から6ターンを完走でき、各ターンで構造化スコアが返る。

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
- [ ] Postgres スキーマ作成（下記）
- [ ] 各ターンのスコアを保存し、学習者プロファイルを更新
- [ ] 介護日本語評価試験 / JFT-Basic の合格ライン到達度(%) を推定して保存（`docs/DESIGN.md` の §3 の簡易ロジック）
- **受け入れ:** 同一学習者の複数ターンが蓄積し、到達度が更新される。

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
- [ ] 学習者ビュー：推定レベル、発音ヒートマップ（弱点音素）、合格ライン到達度の推移、会話ログ ＋ 音声再生
- [ ] コホートビュー：合格見込み分布、要フォロー学習者の自動フラグ（到達度が閾値未満）
- [ ] まずダミーデータで描画 → Phase 4 のAPIに接続
- **受け入れ:** デモ用学習者のスコアが、学習者ビューとコホートビューの両方に反映される。

## Phase 6 — 結果メール
**ゴール:** セッション終了でメールが届く。
- [ ] SES（または SendGrid）連携
- [ ] 学習者向けまとめメール（スコア ＋ 次回リンク、Bahasa ＋ 日本語）
- [ ] 教師向けレポート（クラスの当日サマリ、要フォロー学習者）
- [ ] セッション終了をトリガーに送信し、`summary_sent_at` を記録
- **受け入れ:** 終了時に2種類のメールが送られる（送信ログで確認）。

## Phase 7 — デモ仕上げ
**ゴール:** 10から12分のライブデモが滞りなく回る（`docs/DESIGN.md` の §6 の台本）。
- [ ] デモ用の学習者1名 ＋ クラス（要フォロー2名）をシード
- [ ] 「わざと少し外す」発音の見せ場を再現確認
- [ ] 台本どおりに通しリハーサル
- **受け入れ:** money shot（録音 → 画面スコア → ダッシュボード反映）が安定して再現できる。
