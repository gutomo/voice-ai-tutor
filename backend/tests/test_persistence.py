"""永続化サービス層のテスト (in-memory SQLite。`db` フィクスチャを使う)。"""

import pytest

from app import combine, persistence
from app.persistence import UnknownLearnerError, UnknownSessionError
from app.schemas import (
    LearnerCreate,
    PronunciationResult,
    RubricScore,
    SessionCreate,
)

RUBRIC = RubricScore(
    task_completed=True,
    task_reason="寒さに共感し対応を申し出た",
    grammar=4,
    vocabulary=4,
    politeness=4,
    cefr_estimate="A2",
    feedback_ja="自然な応答です",
    feedback_id="Jawaban natural",
    model_answer_ja="毛布をもう1枚お持ちしますね",
)


def _pron(turn_id: str, acc: float = 84.0) -> PronunciationResult:
    return PronunciationResult(
        turn_id=turn_id,
        reference_text="ref",
        transcript="てすと",
        accuracy=acc,
        fluency=acc,
        completeness=acc,
        pron_score=acc,
    )


def test_learner_crud(db) -> None:
    le = persistence.create_learner(LearnerCreate(name="Budi"))
    assert le.id is not None
    assert le.profile is None  # 採点前はプロファイルなし

    got = persistence.get_learner(le.id)
    assert got is not None
    assert got.name == "Budi"
    assert got.native_lang == "id"
    assert [x.id for x in persistence.list_learners()] == [le.id]
    assert persistence.get_learner(999) is None


def test_session_crud(db) -> None:
    le = persistence.create_learner(LearnerCreate(name="Budi"))
    sess = persistence.create_session(SessionCreate(learner_id=le.id, scenario="kaigo_morning"))
    assert sess.learner_id == le.id
    assert sess.ended_at is None

    ended = persistence.end_session(sess.id)
    assert ended.ended_at is not None

    with pytest.raises(UnknownLearnerError):
        persistence.create_session(SessionCreate(learner_id=999))
    with pytest.raises(UnknownSessionError):
        persistence.end_session(999)


def test_record_turn_accumulates_and_updates_passline(db) -> None:
    le = persistence.create_learner(LearnerCreate(name="Budi"))
    sess = persistence.create_session(SessionCreate(learner_id=le.id))

    # ターン1: 復唱ドリル (発音のみ)。combined=84 → passline 69
    p1 = _pron("a" * 32, 84.0)
    c1 = combine.combine_scores(p1.pron_score, None)
    prof1 = persistence.record_turn(
        sess.id,
        "a" * 32,
        turn_no=1,
        audio_path="a.webm",
        transcript=p1.transcript,
        pron=p1,
        rubric=None,
        combined=c1,
    )
    assert prof1.kaigo_passline_pct == 69.0

    # ターン2: ロールプレイ (発音 + ルーブリック)。CEFR はルーブリック優先
    p2 = _pron("b" * 32, 90.0)
    c2 = combine.combine_scores(p2.pron_score, RUBRIC)
    prof2 = persistence.record_turn(
        sess.id,
        "b" * 32,
        turn_no=1,
        audio_path="b.webm",
        transcript=p2.transcript,
        pron=p2,
        rubric=RUBRIC,
        combined=c2,
    )
    assert prof2.cefr_estimate == "A2"
    assert prof2.jlpt_estimate == "N4"

    # 2ターン蓄積し、合格ライン到達度が平均ベースで更新される (動いた)
    turns = persistence.get_learner_turns(le.id)
    assert len(turns) == 2
    avg = (c1.combined_score + c2.combined_score) / 2
    expected = round(max(0.0, avg - combine.PASSLINE_OFFSET), 1)
    assert prof2.kaigo_passline_pct == expected
    assert prof2.kaigo_passline_pct != prof1.kaigo_passline_pct

    # 取得したプロファイルも一致する
    learner = persistence.get_learner(le.id)
    assert learner is not None
    assert learner.profile is not None
    assert learner.profile.kaigo_passline_pct == expected


def test_record_turn_is_idempotent_upsert(db) -> None:
    le = persistence.create_learner(LearnerCreate(name="Budi"))
    sess = persistence.create_session(SessionCreate(learner_id=le.id))
    tid = "c" * 32

    p = _pron(tid, 84.0)
    persistence.record_turn(
        sess.id,
        tid,
        turn_no=1,
        audio_path="x",
        transcript="t1",
        pron=p,
        rubric=None,
        combined=combine.combine_scores(84.0, None),
    )
    # 同じ turn_id を採点し直す → 行は増えず上書きされる
    p2 = _pron(tid, 50.0)
    prof = persistence.record_turn(
        sess.id,
        tid,
        turn_no=1,
        audio_path="x",
        transcript="t2",
        pron=p2,
        rubric=None,
        combined=combine.combine_scores(50.0, None),
    )
    turns = persistence.get_learner_turns(le.id)
    assert len(turns) == 1
    assert turns[0].combined_score == 50.0
    assert turns[0].transcript == "t2"
    assert prof.kaigo_passline_pct == 35.0  # 50 - 15


def test_record_turn_unknown_session(db) -> None:
    p = _pron("d" * 32)
    with pytest.raises(UnknownSessionError):
        persistence.record_turn(
            999,
            "d" * 32,
            turn_no=1,
            audio_path="x",
            transcript="t",
            pron=p,
            rubric=None,
            combined=combine.combine_scores(84.0, None),
        )


def test_get_learner_turns_unknown_learner(db) -> None:
    with pytest.raises(UnknownLearnerError):
        persistence.get_learner_turns(999)
