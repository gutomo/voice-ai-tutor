"""セッション終了 → 結果メール送信のオーケストレーション (Phase 6)。

`/api/sessions/{id}/end` から (run_in_threadpool 経由で) 呼ばれる同期関数。
DB は persistence、メール本文と送信は emailer、宛先解決は config に委譲する。

流れ:
1. セッションを打刻 (ended_at)。
2. まとめの素材 (学習者 + プロファイル + ターン) とコホートを集める。
3. SES 未設定 / 送信済み (resend=False) はスキップ。
4. 学習者まとめ + 教師レポートの 2 通を送る (片方が失敗しても継続)。
5. 1 通以上送れたら summary_sent_at を打刻する。
"""

from __future__ import annotations

from typing import Literal

from app import emailer, persistence
from app.config import settings
from app.emailer import EmailContent, EmailError
from app.models import _utcnow
from app.schemas import EmailResult, LearnerOut, SessionEndResult, SessionReport


def _learner_recipient(report: SessionReport) -> str | None:
    """学習者メールの宛先。未設定なら送信元にフォールバック (SES サンドボックスでも届く)。"""
    return report.learner.email or settings.email_sender


def _teacher_recipient() -> str | None:
    return settings.teacher_email or settings.email_sender


def _skip(report: SessionReport, reason: str) -> list[EmailResult]:
    return [
        EmailResult(
            kind="learner",
            recipient=_learner_recipient(report) or "—",
            status="skipped",
            detail=reason,
        ),
        EmailResult(
            kind="teacher", recipient=_teacher_recipient() or "—", status="skipped", detail=reason
        ),
    ]


def _send_one(
    kind: Literal["learner", "teacher"], recipient: str, content: EmailContent
) -> EmailResult:
    # 呼び出し前に ses_ready() を確認済みなので認証情報 / 送信元は None ではない。
    assert settings.email_sender and settings.aws_access_key_id and settings.aws_secret_access_key
    try:
        message_id = emailer.send_email(
            content,
            sender=settings.email_sender,
            recipient=recipient,
            region=settings.aws_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
        )
    except EmailError as e:
        return EmailResult(kind=kind, recipient=recipient, status="error", detail=str(e))
    return EmailResult(kind=kind, recipient=recipient, status="sent", message_id=message_id)


def finalize_session(session_id: int, *, resend: bool = False) -> SessionEndResult:
    """セッションを終了し、結果メールを送る。UnknownSessionError は呼び出し側で 404 に変換。"""
    sess = persistence.end_session(session_id)  # 打刻 (ended_at)
    report = persistence.get_session_report(session_id)  # ended_at 反映後

    if sess.summary_sent_at is not None and not resend:
        return SessionEndResult(
            session=sess,
            emails_sent=False,
            emails=_skip(report, "既に送信済み (resend=true で再送)"),
        )

    if not settings.ses_ready():
        return SessionEndResult(
            session=sess,
            emails_sent=False,
            emails=_skip(report, "SES 未設定 (AWS 認証情報 / EMAIL_SENDER)"),
        )

    cohort = persistence.list_learners()
    focus: LearnerOut = next((le for le in cohort if le.id == report.learner.id), report.learner)
    as_of = report.session.ended_at or _utcnow()

    # ses_ready() 済みなので email_sender は非 None → 宛先は必ず解決する。
    learner_to = _learner_recipient(report) or settings.email_sender
    teacher_to = _teacher_recipient() or settings.email_sender
    assert learner_to and teacher_to

    learner_content = emailer.build_learner_email(report, settings.app_base_url)
    teacher_content = emailer.build_teacher_email(
        cohort, scenario=report.session.scenario, as_of=as_of, focus_learner=focus
    )

    results = [
        _send_one("learner", learner_to, learner_content),
        _send_one("teacher", teacher_to, teacher_content),
    ]

    any_sent = any(r.status == "sent" for r in results)
    if any_sent:
        sess = persistence.mark_summary_sent(session_id)

    return SessionEndResult(session=sess, emails_sent=any_sent, emails=results)
