"""Bedrock ラッパのユニットテスト。boto3 client は完全にスタブ (CLAUDE.md)。"""

import pytest

from app import bedrock
from app.scenarios import SCENARIOS

SC = SCENARIOS["kaigo_morning"]


class FakeClient:
    """Converse API のモック。texts を順に返し、呼び出し引数を記録する。"""

    def __init__(self, texts: list[str]) -> None:
        self._texts = list(texts)
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        text = self._texts.pop(0)
        return {"output": {"message": {"content": [{"text": text}]}}}


@pytest.fixture
def fake_client(monkeypatch):
    holder: dict[str, FakeClient] = {}

    def _install(texts: list[str]) -> FakeClient:
        client = FakeClient(texts)
        monkeypatch.setattr(bedrock, "_client", lambda *a, **k: client)
        holder["client"] = client
        return client

    return _install


def _gen(**creds):
    base = dict(region="us-east-1", access_key="ak", secret_key="sk", model_id="m")
    base.update(creds)
    return base


def test_extract_json_plain() -> None:
    assert bedrock._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced() -> None:
    assert bedrock._extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_with_surrounding_text() -> None:
    assert bedrock._extract_json('はい、こちらです: {"a": 1} 以上です') == {"a": 1}


def test_extract_json_raises_when_absent() -> None:
    with pytest.raises(ValueError):
        bedrock._extract_json("no json here")


def test_generate_patient_line(fake_client) -> None:
    fake_client(['{"utterance_ja": "おはよう", "gloss_id": "Selamat pagi"}'])
    out = bedrock.generate_patient_line(SC, [], **_gen())
    assert out["utterance_ja"] == "おはよう"
    assert out["gloss_id"] == "Selamat pagi"


def test_generate_patient_line_retries_on_bad_json(fake_client) -> None:
    client = fake_client(
        ["これは JSON ではありません", '{"utterance_ja": "はい", "gloss_id": "Ya"}']
    )
    out = bedrock.generate_patient_line(SC, [{"role": "assistant", "text": "寒いね"}], **_gen())
    assert out["utterance_ja"] == "はい"
    assert len(client.calls) == 2  # 1 回失敗 → リトライで成功


def test_generate_patient_line_gives_up_after_max_attempts(fake_client) -> None:
    client = fake_client(["x", "y", "z"])  # 3 回とも不正
    with pytest.raises(bedrock.BedrockError):
        bedrock.generate_patient_line(SC, [], **_gen())
    assert len(client.calls) == 3


def test_score_rubric_coerces_and_clamps(fake_client) -> None:
    fake_client(
        [
            '{"task_completed": true, "task_reason": "ok", "grammar": 9, '
            '"vocabulary": 4, "politeness": "3", "cefr_estimate": "A2", '
            '"feedback_ja": "良い", "feedback_id": "Bagus", "model_answer_ja": "毛布を…"}'
        ]
    )
    out = bedrock.score_rubric(SC, "寒いですね、窓を閉めましょうか", "今日は寒いね", **_gen())
    assert out["grammar"] == 5  # 9 → 5 にクランプ
    assert out["politeness"] == 3  # "3" → 3 に変換
    assert out["task_completed"] is True


def test_converse_passes_model_and_system(fake_client) -> None:
    client = fake_client(['{"utterance_ja": "a", "gloss_id": "b"}'])
    bedrock.generate_patient_line(SC, [], **_gen(model_id="my-model"))
    assert client.calls[0]["modelId"] == "my-model"
    assert "system" in client.calls[0]
