"""デモの通しリハーサルを自動化するスモーク (Phase 7)。

実ブラウザ + 実 Azure/Bedrock/SES を使うライブデモ (docs/DEMO_RUNBOOK.md) は手動でしか
通せないが、その台本の各ビートをバックエンド API で再現し、順番に成立することを検証する。
外部 API はすべてスタブ、DB は in-memory SQLite。台本 (docs/DESIGN.md §6) との対応:

- Step 3 復唱ドリル → `/evaluate` (scripted): 発音スコア + 「わざと外した」要練習語。
- Step 4 ロールプレイ → `/evaluate` (roleplay): ルーブリック採点 + タスク達成。
- 山場       → 保存済みターンが学習者プロファイルに反映 (合格ライン到達度が動く)。
- Step 5 まとめ → `/sessions/{id}/end`: 学習者まとめ + 教師レポートの 2 通。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audio, bedrock, combine, emailer, persistence, seed, speech, tts
from app.config import settings
from app.main import app

client = TestClient(app)

DATA = Path(__file__).parent / "data"
SAMPLE_WAV = DATA / "sample_16k_mono.wav"
RAW = json.loads((DATA / "sample_pa_result.json").read_text("utf-8"))

# ロールプレイの二段採点 (STT → scripted) 用のダミー転写。利用者役の口火への良い応答。
_ROLEPLAY_TRANSCRIPT = "そうですね、寒いですね。窓を閉めましょうか"

_RUBRIC = {
    "task_completed": True,
    "task_reason": "寒さに共感し対応を申し出た",
    "grammar": 4,
    "vocabulary": 4,
    "politeness": 4,
    "cefr_estimate": "A2",
    "feedback_ja": "自然な応答です",
    "feedback_id": "Jawaban natural",
    "model_answer_ja": "毛布をもう1枚お持ちしますね",
}


def _fake_assess(wav_path, reference_text, key, region):
    nbest = RAW["NBest"][0]["PronunciationAssessment"]
    return {
        "transcript": RAW["DisplayText"],
        "accuracy": nbest["AccuracyScore"],
        "fluency": nbest["FluencyScore"],
        "completeness": nbest["CompletenessScore"],
        "pron_score": nbest["PronScore"],
        "raw": RAW,
    }


@pytest.fixture(autouse=True)
def _setup(db, tmp_path, monkeypatch):
    # `db` フィクスチャが in-memory SQLite を構成する。以降は外部 API を全てスタブ。
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "azure_speech_key", "k")
    monkeypatch.setattr(settings, "azure_speech_region", "japaneast")
    monkeypatch.setattr(settings, "aws_access_key_id", "ak")
    monkeypatch.setattr(settings, "aws_secret_access_key", "sk")
    monkeypatch.setattr(settings, "bedrock_model_id", "m")
    monkeypatch.setattr(settings, "email_sender", "tutor@example.com")
    monkeypatch.setattr(settings, "teacher_email", "teacher@example.com")

    def fake_convert(src, dst, **_k):
        Path(dst).write_bytes(SAMPLE_WAV.read_bytes())
        return Path(dst)

    monkeypatch.setattr(audio, "to_wav_16k_mono", fake_convert)
    monkeypatch.setattr(speech, "assess_scripted", _fake_assess)
    monkeypatch.setattr(speech, "transcribe", lambda *a, **k: _ROLEPLAY_TRANSCRIPT)
    monkeypatch.setattr(bedrock, "score_rubric", lambda *a, **k: dict(_RUBRIC))
    monkeypatch.setattr(tts, "synthesize_ja", lambda *a, **k: b"RIFFfake")

    # SES 送信をスタブ: 宛先を記録し擬似 MessageId を返す (実送信しない)。
    calls: list[dict] = []

    def fake_send(content, *, sender, recipient, region, access_key, secret_key):
        calls.append({"recipient": recipient, "kind_subject": content.subject})
        return f"ses-{len(calls)}"

    monkeypatch.setattr(emailer, "send_email", fake_send)
    return calls


def _upload() -> str:
    res = client.post("/api/turn", files={"audio": ("c.webm", b"webm-bytes", "audio/webm")})
    assert res.status_code == 200, res.text
    return res.json()["turn_id"]


def _new_learner(name: str) -> int:
    res = client.post("/api/learners", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _new_session(learner_id: int) -> int:
    res = client.post("/api/sessions", json={"learner_id": learner_id, "scenario": "kaigo_morning"})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def test_full_rehearsal_smoke(_setup) -> None:
    """台本 (DESIGN §6) を頭から終わりまで API で通す (money shot 含む)。"""
    calls = _setup
    # frontend の ensureSession 相当: 固定のデモ学習者を作りセッションを開く。
    learner_id = _new_learner(seed.LIVE_DEMO_NAME)
    session_id = _new_session(learner_id)

    # Step 3 復唱ドリル (scripted): 発音スコアと「わざと外した」要練習語が返る。
    drill = client.post(
        f"/api/turn/{_upload()}/evaluate",
        json={
            "mode": "scripted",
            "scenario": "kaigo_morning",
            "turn_no": 1,
            "session_id": session_id,
        },
    )
    assert drill.status_code == 200, drill.text
    d = drill.json()
    assert d["pronunciation"]["weak_words"], "ScoreCard に要練習語が出ない"
    assert d["profile"] is not None, "money shot: 更新後プロファイルが返らない"

    # Step 4 ロールプレイ (roleplay): ルーブリック採点 + タスク達成。
    role = client.post(
        f"/api/turn/{_upload()}/evaluate",
        json={"mode": "roleplay", "scenario": "kaigo_morning", "session_id": session_id},
    )
    assert role.status_code == 200, role.text
    r = role.json()
    assert r["rubric"]["task_completed"] is True
    assert r["combined"]["cefr_estimate"], "合成スコアに CEFR が乗らない"
    assert r["profile"] is not None

    # 山場: 教師ダッシュボードに同じ 1 名がプロファイル付きで現れる。
    learners = client.get("/api/learners").json()
    live = next(le for le in learners if le["name"] == seed.LIVE_DEMO_NAME)
    assert live["profile"] is not None
    assert live["profile"]["kaigo_passline_pct"] >= 0

    # 会話ログ / ヒートマップ: 保存済みターンに要練習語が残る。
    turns = client.get(f"/api/learners/{learner_id}/turns").json()
    assert any(t["weak_phonemes"] for t in turns), "ダッシュボードのヒートマップ素材が無い"

    # Step 5 まとめ: 学習者まとめ + 教師レポートの 2 通を送り打刻する。
    end = client.post(f"/api/sessions/{session_id}/end").json()
    assert end["emails_sent"] is True
    assert {e["kind"] for e in end["emails"]} == {"learner", "teacher"}
    assert all(e["status"] == "sent" for e in end["emails"])
    assert end["session"]["summary_sent_at"] is not None
    assert len(calls) == 2


def test_deliberate_miss_surfaces_in_scorecard_and_heatmap(_setup) -> None:
    """「わざと少し外す」見せ場: 弱い音が (1) ScoreCard と (2) 教師ヒートマップの両方に出る。"""
    learner_id = _new_learner("Miss Demo")
    session_id = _new_session(learner_id)

    resp = client.post(
        f"/api/turn/{_upload()}/evaluate",
        json={
            "mode": "scripted",
            "scenario": "kaigo_morning",
            "turn_no": 2,
            "session_id": session_id,
        },
    ).json()

    # (1) 即時フィードバック: ScoreCard に出る weak_words。
    scorecard_words = [w["word"] for w in resp["pronunciation"]["weak_words"]]
    assert "体温" in scorecard_words

    # (2) 教師ダッシュボード: 永続化された weak_phonemes (ja-JP では弱い単語)。
    turns = client.get(f"/api/learners/{learner_id}/turns").json()
    heatmap_words = [w["word"] for t in turns for w in (t["weak_phonemes"] or [])]
    assert "体温" in heatmap_words


def test_seeded_baseline_then_live_turn_raises_passline(_setup) -> None:
    """ライブ用ベースラインの学習者に 1 ターン録ると、合格ライン到達度が上へ動く (money shot)。"""
    name, baseline = seed.seed_live_demo()
    # ライブ前は要フォロー閾値のすぐ上 (コホートの「要フォロー 2 名」を崩さない)。
    assert baseline.kaigo_passline_pct >= combine.FOLLOWUP_PASSLINE_PCT
    assert baseline.kaigo_passline_pct < 60.0

    learner = next(le for le in persistence.list_learners() if le.name == name)
    # frontend と同じく、同名学習者を再利用して新しいセッションでライブ録音を足す。
    session_id = _new_session(learner.id)
    live = client.post(
        f"/api/turn/{_upload()}/evaluate",
        json={
            "mode": "scripted",
            "scenario": "kaigo_morning",
            "turn_no": 1,
            "session_id": session_id,
        },
    )
    assert live.status_code == 200, live.text
    after = live.json()["profile"]["kaigo_passline_pct"]
    assert after > baseline.kaigo_passline_pct, (baseline.kaigo_passline_pct, after)
