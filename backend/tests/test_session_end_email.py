"""セッション終了 → 結果メール送信のエンドポイントテスト (Phase 6)。

`/api/sessions/{id}/end` が学習者まとめ + 教師レポートの 2 通を送り、
summary_sent_at を打刻することを検証する。SES はスタブ (実送信しない)、
DB は in-memory SQLite、Azure/Bedrock/TTS も完全スタブ。
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audio, bedrock, emailer, scoring, speech, tts
from app.config import settings
from app.main import app

client = TestClient(app)

DATA = Path(__file__).parent / "data"
SAMPLE_WAV = DATA / "sample_16k_mono.wav"
RAW = json.loads((DATA / "sample_pa_result.json").read_text("utf-8"))


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
    monkeypatch.setattr(scoring.speech, "assess_scripted", _fake_assess)
    monkeypatch.setattr(bedrock, "score_rubric", lambda *a, **k: dict(_RUBRIC))
    monkeypatch.setattr(tts, "synthesize_ja", lambda *a, **k: b"RIFFfake")

    # SES 送信をスタブ: 呼び出しを記録し、擬似 MessageId を返す。
    calls: list[dict] = []

    def fake_send(content, *, sender, recipient, region, access_key, secret_key):
        calls.append({"recipient": recipient, "sender": sender, "subject": content.subject})
        return f"ses-{len(calls)}"

    monkeypatch.setattr(emailer, "send_email", fake_send)
    return calls


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


def _upload() -> str:
    res = client.post("/api/turn", files={"audio": ("c.webm", b"webm-bytes", "audio/webm")})
    assert res.status_code == 200
    return res.json()["turn_id"]


def _learner_with_turn(email: str | None = "budi@example.com") -> tuple[int, int]:
    body = {"name": "Budi"}
    if email is not None:
        body["email"] = email
    le = client.post("/api/learners", json=body)
    assert le.status_code == 201, le.text
    learner_id = le.json()["id"]
    se = client.post("/api/sessions", json={"learner_id": learner_id, "scenario": "kaigo_morning"})
    session_id = se.json()["id"]
    # 採点済みターンを 1 つ永続化する (まとめメールの素材)。
    t = _upload()
    r = client.post(
        f"/api/turn/{t}/evaluate",
        json={
            "mode": "scripted",
            "scenario": "kaigo_morning",
            "turn_no": 1,
            "session_id": session_id,
        },
    )
    assert r.status_code == 200, r.text
    return learner_id, session_id


def test_end_session_sends_both_emails_and_marks_sent(_setup) -> None:
    calls = _setup
    _, session_id = _learner_with_turn()

    res = client.post(f"/api/sessions/{session_id}/end")
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["emails_sent"] is True
    assert body["session"]["summary_sent_at"] is not None
    assert body["session"]["ended_at"] is not None

    kinds = {e["kind"]: e for e in body["emails"]}
    assert kinds["learner"]["status"] == "sent"
    assert kinds["learner"]["recipient"] == "budi@example.com"
    assert kinds["learner"]["message_id"] == "ses-1"
    assert kinds["teacher"]["status"] == "sent"
    assert kinds["teacher"]["recipient"] == "teacher@example.com"

    # SES は学習者・教師の 2 通ぶん呼ばれた
    assert len(calls) == 2
    assert {c["recipient"] for c in calls} == {"budi@example.com", "teacher@example.com"}


def test_end_session_is_idempotent_without_resend(_setup) -> None:
    calls = _setup
    _, session_id = _learner_with_turn()

    first = client.post(f"/api/sessions/{session_id}/end").json()
    assert first["emails_sent"] is True
    sent_at = first["session"]["summary_sent_at"]
    assert len(calls) == 2

    # 2 回目 (resend なし) は再送しない
    second = client.post(f"/api/sessions/{session_id}/end").json()
    assert second["emails_sent"] is False
    assert all(e["status"] == "skipped" for e in second["emails"])
    assert "送信済み" in second["emails"][0]["detail"]
    assert len(calls) == 2  # 増えていない
    # 再スタンプされていない (SQLite は tz を保持しないので 'Z'/'+00:00' の差は無視して比較)。
    norm = lambda ts: ts.replace("Z", "").replace("+00:00", "")  # noqa: E731
    assert norm(second["session"]["summary_sent_at"]) == norm(sent_at)

    # resend=true なら再送する
    third = client.post(f"/api/sessions/{session_id}/end?resend=true").json()
    assert third["emails_sent"] is True
    assert len(calls) == 4


def test_end_session_falls_back_to_sender_when_learner_has_no_email(_setup) -> None:
    _, session_id = _learner_with_turn(email=None)

    body = client.post(f"/api/sessions/{session_id}/end").json()
    learner_email = next(e for e in body["emails"] if e["kind"] == "learner")
    assert learner_email["status"] == "sent"
    assert learner_email["recipient"] == "tutor@example.com"  # EMAIL_SENDER へフォールバック


def test_end_session_skips_when_ses_not_configured(_setup, monkeypatch) -> None:
    calls = _setup
    monkeypatch.setattr(settings, "email_sender", None)
    _, session_id = _learner_with_turn()

    res = client.post(f"/api/sessions/{session_id}/end")
    assert res.status_code == 200
    body = res.json()
    assert body["emails_sent"] is False
    assert all(e["status"] == "skipped" for e in body["emails"])
    assert "SES 未設定" in body["emails"][0]["detail"]
    # メールは送られず、summary_sent_at も打刻されない (セッション終了だけ行う)
    assert body["session"]["summary_sent_at"] is None
    assert body["session"]["ended_at"] is not None
    assert len(calls) == 0


def test_end_unknown_session_404(_setup) -> None:
    assert client.post("/api/sessions/999/end").status_code == 404
