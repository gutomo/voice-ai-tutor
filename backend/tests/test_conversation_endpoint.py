"""Phase 3 エンドポイントのテスト。Azure / Bedrock / TTS は完全にスタブ (CLAUDE.md)。"""

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
def _isolate_and_configure(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "azure_speech_key", "dummy-key")
    monkeypatch.setattr(settings, "azure_speech_region", "japaneast")
    monkeypatch.setattr(settings, "aws_access_key_id", "ak")
    monkeypatch.setattr(settings, "aws_secret_access_key", "sk")
    monkeypatch.setattr(settings, "bedrock_model_id", "model-x")

    def fake_convert(src, dst, **_k):
        Path(dst).write_bytes(SAMPLE_WAV.read_bytes())
        return Path(dst)

    monkeypatch.setattr(audio, "to_wav_16k_mono", fake_convert)
    monkeypatch.setattr(speech, "assess_scripted", _fake_assess)
    monkeypatch.setattr(speech, "transcribe", lambda *a, **k: "寒いですね、窓を閉めましょうか")
    monkeypatch.setattr(scoring.speech, "assess_scripted", _fake_assess)
    monkeypatch.setattr(
        scoring.speech, "transcribe", lambda *a, **k: "寒いですね、窓を閉めましょうか"
    )

    monkeypatch.setattr(
        bedrock,
        "generate_patient_line",
        lambda scenario, history, **k: {"utterance_ja": "ああ、寒いねえ", "gloss_id": "dingin"},
    )
    monkeypatch.setattr(
        bedrock, "score_rubric", lambda scenario, learner, patient, **k: dict(RUBRIC)
    )
    monkeypatch.setattr(tts, "synthesize_ja", lambda *a, **k: b"RIFFfake-wav-bytes")


def _upload() -> str:
    res = client.post("/api/turn", files={"audio": ("clip.webm", b"webm-bytes", "audio/webm")})
    assert res.status_code == 200
    return res.json()["turn_id"]


def test_scenario_full_meta() -> None:
    res = client.get("/api/scenario/kaigo_morning")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title_ja"] == "朝の声かけ＋バイタルチェック"
    assert body["persona"]["name"] == "田中さん"
    assert body["roleplay"]["opening_ja"].startswith("ああ、おはよう")
    assert len(body["turns"]) == 5
    assert client.get("/api/scenario/unknown").status_code == 404


def test_conversation_reply() -> None:
    res = client.post(
        "/api/conversation/reply",
        json={
            "scenario": "kaigo_morning",
            "history": [{"role": "user", "text": "おはようございます"}],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["utterance_ja"] == "ああ、寒いねえ"


def test_conversation_reply_503_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "bedrock_model_id", None)
    res = client.post("/api/conversation/reply", json={"scenario": "kaigo_morning"})
    assert res.status_code == 503


def test_conversation_reply_404_unknown_scenario() -> None:
    res = client.post("/api/conversation/reply", json={"scenario": "nope"})
    assert res.status_code == 404


def test_evaluate_scripted() -> None:
    turn_id = _upload()
    res = client.post(
        f"/api/turn/{turn_id}/evaluate",
        json={"mode": "scripted", "scenario": "kaigo_morning", "turn_no": 1},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "scripted"
    assert body["pronunciation"]["pron_score"] == 84.0
    assert body["rubric"] is None
    assert body["combined"]["combined_score"] == 84.0
    assert body["combined"]["kaigo_passline_pct"] == 69.0  # 84 - 15


def test_evaluate_roleplay_two_stage() -> None:
    turn_id = _upload()
    res = client.post(
        f"/api/turn/{turn_id}/evaluate",
        json={"mode": "roleplay", "scenario": "kaigo_morning"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "roleplay"
    # 二段採点: STT 結果が参照テキストになる
    assert body["pronunciation"]["reference_text"] == "寒いですね、窓を閉めましょうか"
    assert body["rubric"]["task_completed"] is True
    # A=84, B=80 → 平均 82 + タスク達成 5 = 87
    assert body["combined"]["combined_score"] == 87.0
    assert body["combined"]["jlpt_estimate"] == "N4"


def test_evaluate_roleplay_with_transcript_skips_stt() -> None:
    turn_id = _upload()
    res = client.post(
        f"/api/turn/{turn_id}/evaluate",
        json={
            "mode": "roleplay",
            "scenario": "kaigo_morning",
            "transcript": "そうですね、寒いですね",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pronunciation"] is None  # STT を省略したので発音なし
    assert body["rubric"]["grammar"] == 4
    assert body["combined"]["pron_score"] is None
    assert body["combined"]["combined_score"] == 85.0  # B=80 + タスク達成 5


def test_evaluate_roleplay_503_without_bedrock(monkeypatch) -> None:
    turn_id = _upload()
    monkeypatch.setattr(settings, "aws_secret_access_key", None)
    res = client.post(
        f"/api/turn/{turn_id}/evaluate",
        json={"mode": "roleplay", "scenario": "kaigo_morning", "transcript": "はい"},
    )
    assert res.status_code == 503


def test_tts_returns_wav_bytes() -> None:
    res = client.post("/api/tts", json={"text": "おはようございます"})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "audio/wav"
    assert res.content == b"RIFFfake-wav-bytes"


def test_tts_503_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "azure_speech_key", None)
    res = client.post("/api/tts", json={"text": "テスト"})
    assert res.status_code == 503


def test_tts_422_empty_text() -> None:
    res = client.post("/api/tts", json={"text": "   "})
    assert res.status_code == 422
