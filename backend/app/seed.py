"""デモ用コホートのシード (Phase 5 教師ダッシュボードの土台 / Phase 7 でも流用)。

教師ダッシュボードを実データで見せるため、6 名の学習者 (うち 2 名は要フォロー) と
各自のセッション・ターンを作る。スコアは `combine.py` の本番ロジックを通すので、
合格ライン到達度・CEFR は実際の計算と整合する (ダミー値を直書きしない)。

各ターンには短い無音 WAV を upload_dir に置くので、ダッシュボードの会話ログから
`/api/turn/{id}/audio` で再生 UI が成立する (中身は無音のプレースホルダ)。

再実行しても重複しないよう、同名のデモ学習者を消してから作り直す。実データ
(デモ以外の学習者) には触れない。

使い方:
    cd backend && uv run python -m app.seed     # 既定の DATABASE_URL に投入
"""

from __future__ import annotations

import hashlib
import wave
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app import combine, persistence
from app.config import settings
from app.db import init_db, session_scope
from app.models import Learner as LearnerModel
from app.schemas import (
    LearnerCreate,
    LearnerProfileOut,
    PronunciationResult,
    RubricScore,
    SessionCreate,
    WordScore,
)

SCENARIO = "kaigo_morning"
MODEL_ANSWER = "毛布をもう1枚お持ちしますね"

# 復唱ドリルのモデル文と、外しやすい語 (発音ヒートマップ用)。
_DRILLS: list[tuple[str, str]] = [
    ("おはようございます。よく眠れましたか", "眠れましたか"),
    ("体温を測りますね。腕を出してください", "測りますね"),
    ("血圧を測ります。少し締めますよ", "血圧"),
]
_ROLEPLAY_GOOD = "そうですね、寒いですね。窓を閉めましょうか"
_ROLEPLAY_WEAK = "さむいですね"
_ROLEPLAY_HARD_WORD = "閉めましょうか"


@dataclass(frozen=True)
class _Spec:
    name: str
    level: int  # おおよその発音/会話レベル (0-100)。ここから全ターンを生成する。


# 2 strong, 2 mid, 2 要フォロー。Dewi がデモの主役 (推定 ~60%)。
_COHORT: list[_Spec] = [
    _Spec("Siti Rahayu", 86),
    _Spec("Dewi Lestari", 74),
    _Spec("Budi Santoso", 70),
    _Spec("Rina Marlina", 66),
    _Spec("Andi Pratama", 50),
    _Spec("Putra Wijaya", 44),
]


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _cefr_for(level: int) -> str:
    if level >= 82:
        return "B1"
    if level >= 55:
        return "A2"
    return "A1"


def _turn_id(name: str, turn_no: int) -> str:
    """決定的な 32hex (再実行で同じターンに upsert され、無音 WAV も上書きされる)。"""
    return hashlib.md5(f"seed::{name}::{turn_no}".encode()).hexdigest()


def _upload_dir() -> Path:
    configured = Path(settings.upload_dir)
    if not configured.is_absolute():
        # このファイルは backend/app/seed.py なので parent.parent = backend/
        configured = Path(__file__).resolve().parent.parent / configured
    configured.mkdir(parents=True, exist_ok=True)
    return configured


def _write_silent_wav(turn_id: str) -> str:
    """会話ログの再生 UI 用に 0.1 秒の無音 WAV を置く。パスを返す。"""
    path = _upload_dir() / f"{turn_id}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 1600)
    return str(path)


def _pron(
    turn_id: str, ref: str, transcript: str, acc: float, weak: list[WordScore]
) -> PronunciationResult:
    flu = _clamp(acc + 4)
    comp = _clamp(acc + 8)
    return PronunciationResult(
        turn_id=turn_id,
        reference_text=ref,
        transcript=transcript,
        accuracy=round(_clamp(acc), 1),
        fluency=round(flu, 1),
        completeness=round(comp, 1),
        pron_score=round(_clamp(0.6 * acc + 0.2 * flu + 0.2 * comp), 1),
        words=[],
        weak_words=weak,
        weak_phonemes=[],
        raw={},
    )


def _rubric_for(level: int) -> RubricScore:
    grade = int(_clamp(round(level / 20), 1, 5))
    task = level >= 55
    if level >= 78:
        fb_ja = "とても自然な応答です。敬語も丁寧でよくできています"
        fb_id = "Respons sangat natural. Bahasa sopan sudah baik."
    elif level >= 55:
        fb_ja = "よい応答です。次の一言まで言えると満点です"
        fb_id = "Respons bagus. Tambahkan satu kalimat lagi agar sempurna."
    else:
        fb_ja = "言いたいことは伝わります。もう少し丁寧に、文を最後まで言いましょう"
        fb_id = "Maksud tersampaikan. Coba lebih sopan dan kalimat lengkap."
    return RubricScore(
        task_completed=task,
        task_reason=(
            "声かけから対応の申し出まで成立" if task else "応答が短く対応の提案まで届かなかった"
        ),
        grammar=grade,
        vocabulary=grade,
        politeness=grade,
        cefr_estimate=_cefr_for(level),
        feedback_ja=fb_ja,
        feedback_id=fb_id,
        model_answer_ja=MODEL_ANSWER,
    )


def _seed_learner(spec: _Spec) -> LearnerProfileOut:
    learner = persistence.create_learner(LearnerCreate(name=spec.name))
    session = persistence.create_session(SessionCreate(learner_id=learner.id, scenario=SCENARIO))
    lvl = spec.level
    profile: LearnerProfileOut | None = None

    # 復唱ドリル 3 ターン (わずかに右肩上がりにして推移を見せる)。
    for i, (ref, hard) in enumerate(_DRILLS):
        acc = lvl + (i - 1) * 3  # -3, 0, +3
        weak: list[WordScore] = []
        if acc < 80:
            weak = [
                WordScore(
                    word=hard, accuracy=round(_clamp(acc - 18), 1), error_type="Mispronunciation"
                )
            ]
        tid = _turn_id(spec.name, i + 1)
        pron = _pron(tid, ref, ref, acc, weak)
        combined = combine.combine_scores(pron.pron_score, None)
        profile = persistence.record_turn(
            session.id,
            tid,
            turn_no=i + 1,
            audio_path=_write_silent_wav(tid),
            transcript=ref,
            pron=pron,
            rubric=None,
            combined=combined,
        )

    # ロールプレイ 2 ターン (発音 + ルーブリック)。
    for j in range(2):
        acc = lvl + 2 + j * 3
        transcript = _ROLEPLAY_GOOD if lvl >= 55 else _ROLEPLAY_WEAK
        weak = []
        if acc < 80:
            weak = [
                WordScore(
                    word=_ROLEPLAY_HARD_WORD,
                    accuracy=round(_clamp(acc - 15), 1),
                    error_type="Mispronunciation",
                )
            ]
        tid = _turn_id(spec.name, 4 + j)
        pron = _pron(tid, _ROLEPLAY_GOOD, transcript, acc, weak)
        rubric = _rubric_for(lvl)
        combined = combine.combine_scores(pron.pron_score, rubric)
        profile = persistence.record_turn(
            session.id,
            tid,
            turn_no=4 + j,
            audio_path=_write_silent_wav(tid),
            transcript=transcript,
            pron=pron,
            rubric=rubric,
            combined=combined,
        )

    assert profile is not None
    return profile


def _clear(names: list[str]) -> None:
    """同名のデモ学習者を削除する (cascade でセッション・ターン・プロファイルも消える)。"""
    with session_scope() as db:
        rows = db.execute(select(LearnerModel).where(LearnerModel.name.in_(names))).scalars().all()
        for row in rows:
            db.delete(row)


def seed_demo(reset: bool = True) -> list[tuple[str, LearnerProfileOut]]:
    """デモコホートを投入し、各学習者の最終プロファイルを返す。"""
    init_db()
    if reset:
        _clear([s.name for s in _COHORT])
    return [(spec.name, _seed_learner(spec)) for spec in _COHORT]


if __name__ == "__main__":
    for name, prof in seed_demo():
        print(
            f"{name:16} passline={prof.kaigo_passline_pct:5.1f}%  "
            f"cefr={prof.cefr_estimate} jlpt={prof.jlpt_estimate}"
        )
