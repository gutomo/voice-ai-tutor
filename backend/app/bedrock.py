"""Amazon Bedrock の Claude ラッパ (利用者役の会話生成 + ルーブリック採点)。

設計上の要点 (speech.py と同じ思想):
- boto3 は関数内で遅延 import。スタブするユニットテスト / CI では boto3 不要。
- Claude の出力は必ず構造化 JSON。パース失敗時はリトライ (CLAUDE.md)。
- 認証情報は引数で受け取り、絶対にログに出さない。
- Bedrock の Converse API を使う (プロバイダ差異を吸収する標準 I/F)。
"""

import json
import re
from typing import Any

from app.scenarios import Scenario

_MAX_ATTEMPTS = 3
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class BedrockError(RuntimeError):
    """Bedrock 呼び出しが失敗した。retriable=True は一時的エラー (リトライ可)。"""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


class BedrockNotConfigured(RuntimeError):
    """AWS 認証情報 / BEDROCK_MODEL_ID が未設定。"""


def _client(region: str, access_key: str, secret_key: str) -> Any:
    # 遅延 import: スタブ時 / CI ではここに到達しないので boto3 不要。
    import boto3

    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def _extract_json(text: str) -> dict[str, Any]:
    """Claude のテキストから JSON オブジェクトを取り出す。失敗したら ValueError。"""
    candidate = text.strip()
    fenced = _FENCE_RE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    # 前後に説明文が混ざっても拾えるよう、最外の {...} を切り出す。
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        return json.loads(candidate[start : end + 1])
    raise ValueError("JSON を取り出せませんでした")


def _converse(
    client: Any,
    model_id: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    temperature: float,
) -> str:
    """Converse API を1回呼び、最初のテキストブロックを返す。"""
    # ClientError は boto3 依存なので文字列で一時エラーを判定する (import を増やさない)。
    try:
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
    except Exception as e:  # noqa: BLE001 - boto3 例外を import せず横断的に扱う
        name = type(e).__name__
        retriable = any(k in name for k in ("Throttling", "Timeout", "ServiceUnavailable"))
        raise BedrockError(f"Bedrock 呼び出しに失敗しました: {name}", retriable=retriable) from e

    try:
        return resp["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        raise BedrockError("Bedrock 応答の形式が想定外です") from e


def _converse_json(
    client: Any,
    model_id: str,
    system: str,
    user: str,
    *,
    max_tokens: int,
    temperature: float,
) -> dict[str, Any]:
    """JSON が返るまで最大 _MAX_ATTEMPTS 回リトライする。"""
    last_err: Exception | None = None
    prompt = user
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        text = _converse(
            client, model_id, system, prompt, max_tokens=max_tokens, temperature=temperature
        )
        try:
            return _extract_json(text)
        except ValueError as e:
            last_err = e
            # 次の試行では JSON のみを返すよう明示的に促す。
            prompt = f"{user}\n\n(注意: 有効な JSON オブジェクトだけを返してください)"
    raise BedrockError(f"JSON 応答を得られませんでした: {last_err}")


def generate_patient_line(
    scenario: Scenario,
    history: list[dict[str, str]],
    *,
    region: str,
    access_key: str,
    secret_key: str,
    model_id: str,
) -> dict[str, Any]:
    """利用者役 (例: 田中さん) の次の発話を生成する。

    返り値: {"utterance_ja": str, "gloss_id": str}
    history は [{"role": "assistant"|"user", "text": str}, ...]。
    """
    persona = scenario.persona
    if persona is None:
        raise BedrockError("このシナリオには利用者役が定義されていません")

    system = (
        f"{persona.profile_ja}\n{persona.speaking_style}\n"
        "あなたの発話は日本語のみ。学習者(職員)を演じてはいけません。\n"
        "出力は次の JSON オブジェクトだけにしてください (前後に文章を付けない): "
        '{"utterance_ja": "<利用者の日本語の発話>", '
        '"gloss_id": "<その発話の Bahasa Indonesia による短い説明>"}'
    )
    if history:
        lines = "\n".join(
            f"{'利用者' if m['role'] == 'assistant' else '職員(学習者)'}: {m['text']}"
            for m in history
        )
        user = f"これまでの会話:\n{lines}\n\n利用者役として、次のひとことを返してください。"
    else:
        user = "ロールプレイの口火として、利用者役の最初のひとことを返してください。"

    return _converse_json(
        client=_client(region, access_key, secret_key),
        model_id=model_id,
        system=system,
        user=user,
        max_tokens=300,
        temperature=0.6,
    )


def score_rubric(
    scenario: Scenario,
    learner_text: str,
    patient_text: str,
    *,
    region: str,
    access_key: str,
    secret_key: str,
    model_id: str,
) -> dict[str, Any]:
    """学習者の応答をルーブリック採点する。返り値は RubricScore のフィールドを満たす dict。

    learner_text=学習者の発話 (転写)、patient_text=直前の利用者役の発話 (文脈)。
    """
    goal = scenario.roleplay.goal_ja if scenario.roleplay else "場面に合った丁寧な応答ができたか。"
    system = (
        "あなたは日本語(介護現場)の評価者です。初級(A2/N4)の学習者にやさしく、"
        "ただし基準は明確に採点します。\n"
        f"タスクのゴール: {goal}\n"
        "grammar / vocabulary / politeness は 0〜5 の整数。cefr_estimate は A1/A2/B1 のいずれか。\n"
        "feedback_ja は日本語、feedback_id は Bahasa Indonesia。"
        "model_answer_ja は模範応答(日本語)。\n"
        "出力は次のキーを持つ JSON オブジェクトだけにしてください (前後に文章を付けない):\n"
        '{"task_completed": true, "task_reason": "", "grammar": 0, "vocabulary": 0, '
        '"politeness": 0, "cefr_estimate": "A2", "feedback_ja": "", "feedback_id": "", '
        '"model_answer_ja": ""}'
    )
    user = (
        f"利用者(田中さん)の発話: {patient_text or '(なし)'}\n"
        f"学習者(職員)の応答: {learner_text}\n\n"
        "上記の応答を採点してください。"
    )
    raw = _converse_json(
        client=_client(region, access_key, secret_key),
        model_id=model_id,
        system=system,
        user=user,
        max_tokens=600,
        temperature=0.2,
    )
    return _coerce_rubric(raw)


def _coerce_rubric(raw: dict[str, Any]) -> dict[str, Any]:
    """Claude の出力を RubricScore に通る形へ寄せる (0-5 クランプ、欠損補完)。"""

    def _clamp_int(value: Any) -> int:
        try:
            n = int(round(float(value)))
        except (TypeError, ValueError):
            n = 0
        return max(0, min(5, n))

    return {
        "task_completed": bool(raw.get("task_completed", False)),
        "task_reason": str(raw.get("task_reason", "")),
        "grammar": _clamp_int(raw.get("grammar")),
        "vocabulary": _clamp_int(raw.get("vocabulary")),
        "politeness": _clamp_int(raw.get("politeness")),
        "cefr_estimate": str(raw.get("cefr_estimate", "A2")),
        "feedback_ja": str(raw.get("feedback_ja", "")),
        "feedback_id": str(raw.get("feedback_id", "")),
        "model_answer_ja": str(raw.get("model_answer_ja", "")),
    }
