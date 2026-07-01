"""学習者・セッションの永続化エンドポイント (Phase 4)。

ターン採点の保存は `/api/turn/{id}/evaluate` 側 (turns.py) で行う。ここは学習者と
セッションの作成・参照、プロファイルと履歴の取得を担う (教師ダッシュボードの土台)。
"""

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from app import persistence, session_summary
from app.persistence import UnknownLearnerError, UnknownSessionError
from app.schemas import (
    LearnerCreate,
    LearnerOut,
    SessionCreate,
    SessionEndResult,
    SessionOut,
    TurnOut,
)

router = APIRouter(prefix="/api", tags=["learners"])


@router.post("/learners", status_code=201)
async def create_learner(body: LearnerCreate) -> LearnerOut:
    return await run_in_threadpool(persistence.create_learner, body)


@router.get("/learners")
async def list_learners() -> list[LearnerOut]:
    return await run_in_threadpool(persistence.list_learners)


@router.get("/learners/{learner_id}")
async def get_learner(learner_id: int) -> LearnerOut:
    learner = await run_in_threadpool(persistence.get_learner, learner_id)
    if learner is None:
        raise HTTPException(status_code=404, detail="学習者が見つかりません")
    return learner


@router.get("/learners/{learner_id}/turns")
async def get_learner_turns(learner_id: int) -> list[TurnOut]:
    try:
        return await run_in_threadpool(persistence.get_learner_turns, learner_id)
    except UnknownLearnerError as e:
        raise HTTPException(status_code=404, detail="学習者が見つかりません") from e


@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate) -> SessionOut:
    try:
        return await run_in_threadpool(persistence.create_session, body)
    except UnknownLearnerError as e:
        raise HTTPException(status_code=404, detail="学習者が見つかりません") from e


@router.get("/sessions/{session_id}")
async def get_session(session_id: int) -> SessionOut:
    sess = await run_in_threadpool(persistence.get_session, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="セッションが見つかりません")
    return sess


@router.post("/sessions/{session_id}/end")
async def end_session(session_id: int, resend: bool = False) -> SessionEndResult:
    """セッションを終了し、結果メール (学習者まとめ + 教師レポート) を送る (Phase 6)。

    `summary_sent_at` を打刻。SES 未設定や送信済み (resend=false) の場合はメールを
    スキップしてセッション終了だけ行う。送信ログは emails フィールドで返す。
    """
    try:
        return await run_in_threadpool(session_summary.finalize_session, session_id, resend=resend)
    except UnknownSessionError as e:
        raise HTTPException(status_code=404, detail="セッションが見つかりません") from e
