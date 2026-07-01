"""DB 永続化のサービス層 (Phase 4)。

ORM を内側に隠し、ルート側へは Pydantic スキーマを返す。各関数は `session_scope`
でトランザクションを完結させ、`run_in_threadpool` から同期呼び出しされる前提。

`record_turn` がデモの山場: ターンの採点を保存し、学習者プロファイル
(合格ライン到達度) を作り直して返す。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import profile as profile_calc
from app.db import session_scope
from app.models import Learner as LearnerModel
from app.models import LearnerProfile, LessonSession, Turn, _utcnow
from app.schemas import (
    CombinedScore,
    LearnerCreate,
    LearnerOut,
    LearnerProfileOut,
    PronunciationResult,
    RubricScore,
    SessionCreate,
    SessionOut,
    SessionReport,
    TurnOut,
)


class UnknownLearnerError(Exception):
    """指定 learner_id が存在しない。"""


class UnknownSessionError(Exception):
    """指定 session_id が存在しない。"""


# --- 学習者 ---


def create_learner(data: LearnerCreate) -> LearnerOut:
    with session_scope() as db:
        learner = LearnerModel(
            name=data.name,
            email=data.email,
            native_lang=data.native_lang,
            target_sector=data.target_sector,
        )
        db.add(learner)
        db.flush()
        return LearnerOut.model_validate(learner)


def list_learners() -> list[LearnerOut]:
    with session_scope() as db:
        learners = db.execute(select(LearnerModel).order_by(LearnerModel.id)).scalars().all()
        return [LearnerOut.model_validate(le) for le in learners]


def get_learner(learner_id: int) -> LearnerOut | None:
    with session_scope() as db:
        learner = db.get(LearnerModel, learner_id)
        if learner is None:
            return None
        return LearnerOut.model_validate(learner)


def get_learner_turns(learner_id: int) -> list[TurnOut]:
    """学習者の全ターンを新しい順に返す (履歴・教師ダッシュボード用)。"""
    with session_scope() as db:
        if db.get(LearnerModel, learner_id) is None:
            raise UnknownLearnerError(str(learner_id))
        stmt = (
            select(Turn)
            .join(LessonSession, Turn.session_id == LessonSession.id)
            .where(LessonSession.learner_id == learner_id)
            .order_by(Turn.created_at.desc())
        )
        turns = db.execute(stmt).scalars().all()
        return [TurnOut.model_validate(t) for t in turns]


# --- セッション ---


def create_session(data: SessionCreate) -> SessionOut:
    with session_scope() as db:
        if db.get(LearnerModel, data.learner_id) is None:
            raise UnknownLearnerError(str(data.learner_id))
        sess = LessonSession(learner_id=data.learner_id, scenario=data.scenario)
        db.add(sess)
        db.flush()
        return SessionOut.model_validate(sess)


def get_session(session_id: int) -> SessionOut | None:
    with session_scope() as db:
        sess = db.get(LessonSession, session_id)
        if sess is None:
            return None
        return SessionOut.model_validate(sess)


def end_session(session_id: int) -> SessionOut:
    """セッションを終了する (ended_at を打刻)。Phase 6 のメール送信トリガー。"""
    with session_scope() as db:
        sess = db.get(LessonSession, session_id)
        if sess is None:
            raise UnknownSessionError(str(session_id))
        if sess.ended_at is None:
            sess.ended_at = _utcnow()
        db.flush()
        return SessionOut.model_validate(sess)


def get_session_report(session_id: int) -> SessionReport:
    """まとめメール用に、セッション + 学習者(プロファイル込み) + そのターン群を集める。"""
    with session_scope() as db:
        sess = db.get(LessonSession, session_id)
        if sess is None:
            raise UnknownSessionError(str(session_id))
        learner = db.get(LearnerModel, sess.learner_id)
        assert learner is not None  # FK 制約上ありえない
        turns = (
            db.execute(select(Turn).where(Turn.session_id == session_id).order_by(Turn.created_at))
            .scalars()
            .all()
        )
        return SessionReport(
            session=SessionOut.model_validate(sess),
            learner=LearnerOut.model_validate(learner),
            turns=[TurnOut.model_validate(t) for t in turns],
        )


def mark_summary_sent(session_id: int) -> SessionOut:
    """まとめメール送信済みを打刻する (summary_sent_at)。冪等に上書きする。"""
    with session_scope() as db:
        sess = db.get(LessonSession, session_id)
        if sess is None:
            raise UnknownSessionError(str(session_id))
        sess.summary_sent_at = _utcnow()
        db.flush()
        return SessionOut.model_validate(sess)


# --- ターン保存 + プロファイル更新 (山場) ---


def record_turn(
    session_id: int,
    turn_id: str,
    *,
    turn_no: int | None,
    audio_path: str | None,
    transcript: str | None,
    pron: PronunciationResult | None,
    rubric: RubricScore | None,
    combined: CombinedScore,
) -> LearnerProfileOut:
    """ターンの採点を保存し、学習者プロファイルを作り直して返す。

    同じ turn_id を再評価した場合は上書き (created_at は保持)。プロファイルは
    その学習者の全ターンの combined_score から `profile.estimate_profile` で算出する。
    """
    with session_scope() as db:
        sess = db.get(LessonSession, session_id)
        if sess is None:
            raise UnknownSessionError(str(session_id))
        learner_id = sess.learner_id

        turn = db.get(Turn, turn_id)
        if turn is None:
            turn = Turn(id=turn_id, created_at=_utcnow())
            db.add(turn)
        turn.session_id = session_id
        turn.turn_no = turn_no
        turn.audio_path = audio_path
        turn.transcript = transcript
        turn.pron_accuracy = pron.accuracy if pron else None
        turn.pron_fluency = pron.fluency if pron else None
        turn.pron_completeness = pron.completeness if pron else None
        turn.weak_phonemes = [w.model_dump() for w in pron.weak_words] if pron else None
        turn.rubric = rubric.model_dump() if rubric else None
        turn.combined_score = combined.combined_score
        db.flush()

        prof = _recompute_profile(db, learner_id)
        return LearnerProfileOut.model_validate(prof)


def _recompute_profile(db: Session, learner_id: int) -> LearnerProfile:
    """学習者の全ターンから推定し、learner_profile を upsert する。"""
    stmt = (
        select(Turn)
        .join(LessonSession, Turn.session_id == LessonSession.id)
        .where(LessonSession.learner_id == learner_id)
        .order_by(Turn.created_at.desc())
    )
    turns = db.execute(stmt).scalars().all()

    combined_scores = [t.combined_score for t in turns if t.combined_score is not None]
    latest_cefr: str | None = None
    for t in turns:  # 新しい順。最初に見つかったルーブリックの CEFR を採用する。
        if t.rubric and t.rubric.get("cefr_estimate"):
            latest_cefr = t.rubric["cefr_estimate"]
            break

    est = profile_calc.estimate_profile(combined_scores, latest_cefr)

    prof = db.get(LearnerProfile, learner_id)
    if prof is None:
        prof = LearnerProfile(learner_id=learner_id)
        db.add(prof)
    prof.cefr_estimate = est.cefr_estimate
    prof.jlpt_estimate = est.jlpt_estimate
    prof.kaigo_passline_pct = est.kaigo_passline_pct
    prof.updated_at = _utcnow()
    db.flush()
    return prof
