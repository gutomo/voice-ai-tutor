"""デモ用シナリオのモデル文 (scripted 発音採点の参照テキスト)。

DB ではなく静的テーブル (DB は Phase 4)。介護「朝の声かけ」の定型文をここに置く。
gloss_id は UI に出す Bahasa Indonesia の補助説明。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTurn:
    turn_no: int
    reference_text: str  # 日本語のモデル文 (発音採点の参照)
    gloss_id: str  # Bahasa の説明


SCENARIOS: dict[str, list[ModelTurn]] = {
    "kaigo_morning": [
        ModelTurn(1, "おはようございます。よく眠れましたか", "Salam pagi + tanya tidur"),
        ModelTurn(2, "体温を測りますね。腕を出してください", "Ukur suhu, minta ulurkan lengan"),
        ModelTurn(3, "血圧を測ります。少し締めますよ", "Ukur tekanan darah"),
        ModelTurn(4, "お変わりありませんか", "Tanya kabar/keadaan"),
        ModelTurn(5, "お水を飲みますか", "Tawarkan minum air"),
    ],
}


def list_turns(scenario: str) -> list[ModelTurn]:
    return SCENARIOS.get(scenario, [])


def get_reference_text(scenario: str | None, turn_no: int | None) -> str | None:
    """(scenario, turn_no) からモデル文を引く。無ければ None。"""
    if not scenario or turn_no is None:
        return None
    for t in SCENARIOS.get(scenario, []):
        if t.turn_no == turn_no:
            return t.reference_text
    return None
