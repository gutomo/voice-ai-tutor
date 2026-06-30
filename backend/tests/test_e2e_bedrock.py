"""唯一の実 Bedrock 呼び出し (任意・課金注意)。

既定ではスキップ。実行するには:
  - RUN_BEDROCK_E2E=1
  - AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_REGION
  - BEDROCK_MODEL_ID (Claude の推論プロファイルID)
Bedrock の従量課金が発生する。CLAUDE.md: 有料呼び出し前に必ず確認すること。
"""

import os

import pytest

from app import bedrock
from app.config import settings
from app.scenarios import SCENARIOS

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BEDROCK_E2E") != "1" or not settings.bedrock_ready(),
    reason="実 Bedrock E2E は RUN_BEDROCK_E2E=1 + AWS 認証情報 + モデルID が揃ったときだけ実行",
)

SC = SCENARIOS["kaigo_morning"]
_CREDS = dict(
    region=settings.aws_region,
    access_key=settings.aws_access_key_id,
    secret_key=settings.aws_secret_access_key,
    model_id=settings.bedrock_model_id,
)


def test_real_patient_line() -> None:
    out = bedrock.generate_patient_line(SC, [], **_CREDS)
    assert out["utterance_ja"].strip()
    assert out["gloss_id"].strip()


def test_real_rubric() -> None:
    out = bedrock.score_rubric(
        SC, "そうですね、寒いですね。窓を閉めましょうか", "今日は少し寒いねえ", **_CREDS
    )
    assert out["task_completed"] in (True, False)
    for k in ("grammar", "vocabulary", "politeness"):
        assert 0 <= out[k] <= 5
    assert out["cefr_estimate"]
