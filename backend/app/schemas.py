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


# --- Phase 3: 会話ループ + ルーブリック採点 (Bedrock Claude) ---


class ConversationMessage(BaseModel):
    """ロールプレイの1発話。assistant=利用者役(田中さん)、user=学習者(職員)。"""

    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "user"]
    text: str


class ConversationReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    history: list[ConversationMessage] = Field(default_factory=list)


class PatientLine(BaseModel):
    """利用者役の生成発話。utterance_ja を TTS で読み上げる。"""

    utterance_ja: str
    gloss_id: str  # Bahasa の補足説明


class RubricScore(BaseModel):
    """Claude のルーブリック採点 (BUILD_PLAN.md Phase 3 のスキーマ)。

    grammar / vocabulary / politeness は 0-5。feedback_ja=日本語、feedback_id=Bahasa。
    """

    task_completed: bool
    task_reason: str
    grammar: int = Field(ge=0, le=5)
    vocabulary: int = Field(ge=0, le=5)
    politeness: int = Field(ge=0, le=5)
    cefr_estimate: str
    feedback_ja: str
    feedback_id: str
    model_answer_ja: str


class CombinedScore(BaseModel):
    """発音(A) + 会話(B) + タスク達成(C) を合成した学習者スコア。"""

    pron_score: float | None = None  # (A) 0-100
    rubric_score: float | None = None  # (B) ルーブリック平均×20 = 0-100
    task_completed: bool | None = None  # (C)
    combined_score: float  # 0-100
    cefr_estimate: str | None = None
    jlpt_estimate: str | None = None
    kaigo_passline_pct: float  # 介護日本語評価試験 合格ライン到達度の推定 (%)


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str | None = None
    turn_no: int | None = None
    mode: Literal["scripted", "roleplay"] = "scripted"
    # scripted の参照テキスト上書き / roleplay で学習者の転写を直接渡したいとき
    reference_text: str | None = None
    transcript: str | None = None
    # roleplay の文脈: 直前の利用者役の発話 (省略時はシナリオの口火を使う)
    patient_text: str | None = None


class TurnEvaluation(BaseModel):
    """1ターンの統合評価。scripted は pronunciation、roleplay は rubric が主役。"""

    turn_id: str
    mode: Literal["scripted", "roleplay"]
    pronunciation: PronunciationResult | None = None
    rubric: RubricScore | None = None
    combined: CombinedScore


class TtsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    voice: str | None = None
