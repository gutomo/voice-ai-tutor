"""録音ターンのアップロード・再生エンドポイントのテスト。

保存先は tmp_path に差し替え、実際の uploads/ を汚さない。
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_uploads(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


def test_upload_and_roundtrip() -> None:
    audio = b"FAKE-WEBM-BYTES-1234567890"
    res = client.post(
        "/api/turn",
        files={"audio": ("clip.webm", audio, "audio/webm")},
        data={"scenario": "kaigo_morning", "turn_no": "1"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["turn_id"]) == 32
    assert body["size_bytes"] == len(audio)
    assert body["scenario"] == "kaigo_morning"
    assert body["turn_no"] == 1
    assert body["audio_url"] == f"/api/turn/{body['turn_id']}/audio"

    # 保存した音声を取り戻すとバイト列が一致する
    got = client.get(body["audio_url"])
    assert got.status_code == 200
    assert got.content == audio
    assert got.headers["content-type"].startswith("audio/webm")


def test_reject_non_audio() -> None:
    res = client.post(
        "/api/turn",
        files={"audio": ("note.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 415


def test_reject_empty() -> None:
    res = client.post(
        "/api/turn",
        files={"audio": ("empty.webm", b"", "audio/webm")},
    )
    assert res.status_code == 400


def test_missing_turn_audio() -> None:
    # 形式は正しいが存在しない 32桁hex
    res = client.get("/api/turn/" + "0" * 32 + "/audio")
    assert res.status_code == 404


def test_invalid_turn_id() -> None:
    res = client.get("/api/turn/not-a-valid-id/audio")
    assert res.status_code == 404
