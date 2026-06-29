"""唯一の実 Azure 呼び出し (任意・課金注意)。

既定ではスキップ。実行するには:
  - RUN_AZURE_E2E=1
  - AZURE_SPEECH_KEY / AZURE_SPEECH_REGION (F0 無料枠を推奨)
  - AZURE_E2E_AUDIO=<モデル文を実際に録音した音声ファイルへのパス>
F0 無料枠なら課金は発生しない。CLAUDE.md: 有料呼び出し前に必ず確認すること。
"""

import os
from pathlib import Path

import pytest

from app import scoring
from app.config import settings

REFERENCE = "おはようございます。よく眠れましたか"

_audio = os.getenv("AZURE_E2E_AUDIO", "")

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AZURE_E2E") != "1"
    or not settings.azure_ready()
    or not (_audio and Path(_audio).exists()),
    reason="実 Azure E2E は RUN_AZURE_E2E=1 + 鍵 + AZURE_E2E_AUDIO が揃ったときだけ実行",
)


def test_real_scoring() -> None:
    result = scoring.score_turn_sync(
        Path(_audio),
        "0" * 32,
        REFERENCE,
        settings.azure_speech_key,
        settings.azure_speech_region,
    )
    for v in (result.accuracy, result.fluency, result.completeness, result.pron_score):
        assert 0.0 <= v <= 100.0
    assert result.pron_score > 0
