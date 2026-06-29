"""採点エンドポイントのテスト。ffmpeg と Azure は完全にスタブ (CLAUDE.md)。"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import audio, speech
from app.config import settings
from app.main import app
from app.speech import NoSpeechError

client = TestClient(app)

DATA = Path(__file__).parent / "data"
SAMPLE_WAV = DATA / "sample_16k_mono.wav"
RAW = json.loads((DATA / "sample_pa_result.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def _isolate_and_configure(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    monkeypatch.setattr(settings, "azure_speech_key", "dummy-key")
    monkeypatch.setattr(settings, "azure_speech_region", "japaneast")

    # ffmpeg の代わりにサンプル WAV をコピー
    def fake_convert(src, dst, **_k):
        Path(dst).write_bytes(SAMPLE_WAV.read_bytes())
        return Path(dst)

    monkeypatch.setattr(audio, "to_wav_16k_mono", fake_convert)

    # Azure の代わりに既知の結果を返す
    def fake_assess(wav_path, reference_text, key, region):
        nbest = RAW["NBest"][0]["PronunciationAssessment"]
        return {
            "transcript": RAW["DisplayText"],
            "accuracy": nbest["AccuracyScore"],
            "fluency": nbest["FluencyScore"],
            "completeness": nbest["CompletenessScore"],
            "pron_score": nbest["PronScore"],
            "raw": RAW,
        }

    monkeypatch.setattr(speech, "assess_scripted", fake_assess)


def _upload() -> str:
    res = client.post("/api/turn", files={"audio": ("clip.webm", b"webm-bytes", "audio/webm")})
    assert res.status_code == 200
    return res.json()["turn_id"]


def test_score_happy_path() -> None:
    turn_id = _upload()
    res = client.post(
        f"/api/turn/{turn_id}/score", json={"scenario": "kaigo_morning", "turn_no": 1}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["turn_id"] == turn_id
    assert body["reference_text"] == "おはようございます。よく眠れましたか"
    assert body["accuracy"] == 82.0
    assert body["pron_score"] == 84.0
    assert [w["word"] for w in body["weak_words"]] == ["体温"]
    assert body["weak_phonemes"][0]["accuracy"] == 38.0


def test_score_with_explicit_reference_text() -> None:
    turn_id = _upload()
    res = client.post(f"/api/turn/{turn_id}/score", json={"reference_text": "テスト"})
    assert res.status_code == 200
    assert res.json()["reference_text"] == "テスト"


def test_score_503_when_unconfigured(monkeypatch) -> None:
    turn_id = _upload()
    monkeypatch.setattr(settings, "azure_speech_key", None)
    res = client.post(
        f"/api/turn/{turn_id}/score", json={"scenario": "kaigo_morning", "turn_no": 1}
    )
    assert res.status_code == 503


def test_score_422_no_reference() -> None:
    turn_id = _upload()
    res = client.post(f"/api/turn/{turn_id}/score", json={})
    assert res.status_code == 422


def test_score_404_bad_id() -> None:
    res = client.post("/api/turn/not-a-valid-id/score", json={"reference_text": "テスト"})
    assert res.status_code == 404


def test_score_422_no_speech(monkeypatch) -> None:
    turn_id = _upload()

    def raise_no_speech(*_a, **_k):
        raise NoSpeechError()

    monkeypatch.setattr(speech, "assess_scripted", raise_no_speech)
    res = client.post(f"/api/turn/{turn_id}/score", json={"reference_text": "テスト"})
    assert res.status_code == 422
    assert "もう一度" in res.json()["detail"]


def test_scenario_turns() -> None:
    res = client.get("/api/scenario/kaigo_morning/turns")
    assert res.status_code == 200
    assert res.json()["turns"][0]["reference_text"] == "おはようございます。よく眠れましたか"
    assert client.get("/api/scenario/unknown/turns").status_code == 404
