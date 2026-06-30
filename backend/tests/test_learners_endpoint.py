"""Phase 4 エンドポイントのテスト。

学習者・セッションの API と、`/evaluate` に session_id を渡したときの永続化
(ターン蓄積 → プロファイル更新 = money shot) を検証する。
外部 API (Azure / Bedrock / TTS) は完全にスタブ、DB は in-memory SQLite。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audio, bedrock, scoring, speech, tts
from app.config import settings
from app.main import app

client = TestClient(app)

DATA = Path(__file__).parent / "data"
SAMPLE_WAV = DATA / "sample_16k_mono.wav"
RAW = json.loads((DATA / "sample_pa_result.json").read_text("utf-8"))

STT_TEXT = "寒いですね、窓を閉めましょうか"

RUBRIC = {
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
    # `db` フィクスチャ (引数) が in-memory SQLite を構成する。
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "azure_speech_key", "k")
    monkeypatch.setattr(settings, "azure_speech_region", "japaneast")
    monkeypatch.setattr(settings, "aws_access_key_id", "ak")
    monkeypatch.setattr(settings, "aws_secret_access_key", "sk")
    monkeypatch.setattr(settings, "bedrock_model_id", "m")

    def fake_convert(src, dst, **_k):
        Path(dst).write_bytes(SAMPLE_WAV.read_bytes())
        return Path(dst)

    monkeypatch.setattr(audio, "to_wav_16k_mono", fake_convert)
    monkeypatch.setattr(speech, "assess_scripted", _fake_assess)
    monkeypatch.setattr(speech, "transcribe", lambda *a, **k: STT_TEXT)
    monkeypatch.setattr(scoring.speech, "assess_scripted", _fake_assess)
    monkeypatch.setattr(scoring.speech, "transcribe", lambda *a, **k: STT_TEXT)
    monkeypatch.setattr(bedrock, "score_rubric", lambda *a, **k: dict(RUBRIC))
    monkeypatch.setattr(tts, "synthesize_ja", lambda *a, **k: b"RIFFfake")


def _upload() -> str:
    res = client.post("/api/turn", files={"audio": ("c.webm", b"webm-bytes", "audio/webm")})
    assert res.status_code == 200
    return res.json()["turn_id"]


def _new_learner_session() -> tuple[int, int]:
    le = client.post("/api/learners", json={"name": "Budi"})
    assert le.status_code == 201, le.text
    learner_id = le.json()["id"]
    se = client.post("/api/sessions", json={"learner_id": learner_id, "scenario": "kaigo_morning"})
    assert se.status_code == 201, se.text
    return learner_id, se.json()["id"]


def test_learner_session_lifecycle() -> None:
    le = client.post("/api/learners", json={"name": "Budi"})
    assert le.status_code == 201, le.text
    learner_id = le.json()["id"]
    assert le.json()["profile"] is None

    assert client.get(f"/api/learners/{learner_id}").status_code == 200
    assert client.get("/api/learners/999").status_code == 404
    assert any(x["id"] == learner_id for x in client.get("/api/learners").json())

    se = client.post("/api/sessions", json={"learner_id": learner_id})
    assert se.status_code == 201, se.text
    session_id = se.json()["id"]
    assert se.json()["ended_at"] is None

    ended = client.post(f"/api/sessions/{session_id}/end")
    assert ended.status_code == 200
    assert ended.json()["ended_at"] is not None
    assert client.get(f"/api/sessions/{session_id}").status_code == 200


def test_create_session_unknown_learner_404() -> None:
    res = client.post("/api/sessions", json={"learner_id": 999})
    assert res.status_code == 404


def test_evaluate_persists_and_updates_profile() -> None:
    """money shot: 同一学習者の複数ターンが蓄積し、合格ライン到達度が動く。"""
    learner_id, session_id = _new_learner_session()

    # ターン1: 復唱ドリル (scripted)。combined 84 → passline 69
    t1 = _upload()
    r1 = client.post(
        f"/api/turn/{t1}/evaluate",
        json={
            "mode": "scripted",
            "scenario": "kaigo_morning",
            "turn_no": 1,
            "session_id": session_id,
        },
    )
    assert r1.status_code == 200, r1.text
    prof1 = r1.json()["profile"]
    assert prof1 is not None
    assert prof1["learner_id"] == learner_id
    assert prof1["kaigo_passline_pct"] == 69.0

    # ターン2: ロールプレイ。A=84,B=80 → 平均82 +タスク達成5 = 87
    t2 = _upload()
    r2 = client.post(
        f"/api/turn/{t2}/evaluate",
        json={"mode": "roleplay", "scenario": "kaigo_morning", "session_id": session_id},
    )
    assert r2.status_code == 200, r2.text
    prof2 = r2.json()["profile"]
    # 平均 (84 + 87) / 2 = 85.5 → passline 70.5、CEFR はルーブリック優先で A2
    assert prof2["kaigo_passline_pct"] == 70.5
    assert prof2["kaigo_passline_pct"] != prof1["kaigo_passline_pct"]
    assert prof2["cefr_estimate"] == "A2"
    assert prof2["jlpt_estimate"] == "N4"

    # 2ターン蓄積し、学習者プロファイルに反映されている
    turns = client.get(f"/api/learners/{learner_id}/turns").json()
    assert len(turns) == 2
    learner = client.get(f"/api/learners/{learner_id}").json()
    assert learner["profile"]["kaigo_passline_pct"] == 70.5


def test_evaluate_without_session_id_does_not_persist() -> None:
    t1 = _upload()
    res = client.post(
        f"/api/turn/{t1}/evaluate",
        json={"mode": "scripted", "scenario": "kaigo_morning", "turn_no": 1},
    )
    assert res.status_code == 200, res.text
    assert res.json()["profile"] is None
    # 学習者を作っていないので DB にも何も無い
    assert client.get("/api/learners").json() == []


def test_evaluate_unknown_session_404() -> None:
    t1 = _upload()
    res = client.post(
        f"/api/turn/{t1}/evaluate",
        json={"mode": "scripted", "scenario": "kaigo_morning", "turn_no": 1, "session_id": 999},
    )
    assert res.status_code == 404
