"""発音採点の Pydantic スキーマ (Phase 2)。

ja-JP は Prosody を返さないので prosody フィールドは持たない。
学習者向けの主役は weak_words (音素名は ja-JP では不透明なため)。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ScoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str | None = None
    turn_no: int | None = None
    # 自由発話の二段採点など、参照テキストを明示指定したいとき
    reference_text: str | None = None
    mode: Literal["scripted", "free"] = "scripted"


class WordScore(BaseModel):
    word: str
    accuracy: float | None = None
    error_type: str = "None"


class WeakPhoneme(BaseModel):
    word: str
    phoneme: str
    accuracy: float | None = None


class PronunciationResult(BaseModel):
    turn_id: str
    reference_text: str
    transcript: str
    # 0-100 (HundredMark)。ja-JP は prosody なし。
    accuracy: float
    fluency: float
    completeness: float
    pron_score: float
    words: list[WordScore] = Field(default_factory=list)
    weak_words: list[WordScore] = Field(default_factory=list)
    weak_phonemes: list[WeakPhoneme] = Field(default_factory=list)
    # デバッグ/ダッシュボード用の Azure 生 JSON (学習者UIには使わない)
    raw: dict[str, Any] = Field(default_factory=dict)
