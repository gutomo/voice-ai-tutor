"""結果メール本文の生成テスト (Phase 6)。

`build_learner_email` / `build_teacher_email` は外部 I/O を持たない純関数なので、
スキーマを直接組み立てて本文を検証する (SES もDBも不要)。
"""

from datetime import UTC, datetime

from app import emailer
from app.schemas import (
    LearnerOut,
    LearnerProfileOut,
    SessionOut,
    SessionReport,
    TurnOut,
)

_NOW = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)


def _learner(id_: int, name: str, passline: float, cefr: str = "A2", email: str | None = None):
    return LearnerOut(
        id=id_,
        name=name,
        email=email,
        native_lang="id",
        target_sector="kaigo",
        created_at=_NOW,
        profile=LearnerProfileOut(
            learner_id=id_,
            cefr_estimate=cefr,
            jlpt_estimate="N4" if cefr == "A2" else "N5",
            kaigo_passline_pct=passline,
            updated_at=_NOW,
        ),
    )


def _scripted_turn(acc: float, weak_word: str | None) -> TurnOut:
    weak = (
        [{"word": weak_word, "accuracy": 55.0, "error_type": "Mispronunciation"}]
        if weak_word
        else None
    )
    return TurnOut(
        id="a" * 32,
        session_id=1,
        turn_no=1,
        transcript="おはようございます",
        pron_accuracy=acc,
        pron_fluency=acc,
        pron_completeness=acc,
        weak_phonemes=weak,
        rubric=None,
        combined_score=acc,
        created_at=_NOW,
    )


def _roleplay_turn(grade: int) -> TurnOut:
    # 転写を直接渡したロールプレイは発音採点なし (pron_* は None)。
    return TurnOut(
        id="b" * 32,
        session_id=1,
        turn_no=4,
        transcript="寒いですね、窓を閉めましょうか",
        pron_accuracy=None,
        pron_fluency=None,
        pron_completeness=None,
        weak_phonemes=None,
        rubric={
            "task_completed": True,
            "grammar": grade,
            "vocabulary": grade,
            "politeness": grade,
            "cefr_estimate": "A2",
        },
        combined_score=82.0,
        created_at=_NOW,
    )


def _report(passline: float = 62.0, email: str | None = None) -> SessionReport:
    return SessionReport(
        session=SessionOut(
            id=1,
            learner_id=7,
            scenario="kaigo_morning",
            started_at=_NOW,
            ended_at=_NOW,
            summary_sent_at=None,
        ),
        learner=_learner(7, "Dewi", passline, email=email),
        turns=[_scripted_turn(78.0, "測ります"), _roleplay_turn(4)],
    )


def test_learner_email_has_scores_next_link_and_both_languages() -> None:
    content = emailer.build_learner_email(_report(), "https://demo.example/lesson")

    assert "Dewi" in content.text_body
    # 発音 78 / 会話 4.0 / 到達度 62% が本文に出る
    assert "78" in content.text_body
    assert "4.0/5" in content.text_body
    assert "62.0%" in content.text_body or "62%" in content.text_body
    # レッスン名 (日本語) と Bahasa の説明の両方
    assert "朝の声かけ" in content.text_body
    assert "Skor hari ini" in content.text_body
    # 弱い単語と次回リンク
    assert "測ります" in content.text_body
    assert "https://demo.example/lesson" in content.text_body
    # HTML にもリンクとスコアが入る
    assert "https://demo.example/lesson" in content.html_body
    assert "<ul>" in content.html_body


def test_learner_email_without_weak_words_omits_practice_section() -> None:
    report = SessionReport(
        session=_report().session,
        learner=_report().learner,
        turns=[_scripted_turn(92.0, None)],
    )
    content = emailer.build_learner_email(report, "https://x")
    assert "次に練習する音" not in content.text_body


def test_teacher_email_lists_cohort_and_flags_followups() -> None:
    cohort = [
        _learner(1, "Siti", 80.0, "B1"),
        _learner(2, "Dewi", 45.0),
        _learner(3, "Putra", 30.0, "A1"),
    ]
    content = emailer.build_teacher_email(
        cohort, scenario="kaigo_morning", as_of=_NOW, focus_learner=cohort[1]
    )

    assert "2026-07-01" in content.text_body
    for name in ("Siti", "Dewi", "Putra"):
        assert name in content.text_body
    # 45% と 30% が要フォロー (< 50%) → 2 名
    assert "要フォロー / Perlu perhatian (2名)" in content.text_body
    # 直近で終了した学習者 (focus) が出る
    assert "Baru saja selesai: Dewi" in content.text_body
    # 合格圏 (Siti 80%) はフラグされない
    assert "Siti: 80.0% (B1)" in content.text_body
    assert "<table" in content.html_body


def test_teacher_email_no_followups() -> None:
    cohort = [_learner(1, "Siti", 80.0, "B1"), _learner(2, "Budi", 70.0)]
    content = emailer.build_teacher_email(cohort, scenario="kaigo_morning", as_of=_NOW)
    assert "要フォロー / Perlu perhatian (0名)" in content.text_body
    assert "該当なし" in content.text_body
