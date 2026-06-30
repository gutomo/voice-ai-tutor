"""スコア合成 (combine.py) の純関数テスト。外部呼び出しなし。"""

from app import combine
from app.schemas import RubricScore


def _rubric(**kw) -> RubricScore:
    base = dict(
        task_completed=True,
        task_reason="ok",
        grammar=4,
        vocabulary=4,
        politeness=4,
        cefr_estimate="A2",
        feedback_ja="良いです",
        feedback_id="Bagus",
        model_answer_ja="毛布をお持ちしますね",
    )
    base.update(kw)
    return RubricScore(**base)


def test_rubric_to_100() -> None:
    assert combine.rubric_to_100(_rubric(grammar=4, vocabulary=4, politeness=4)) == 80.0
    assert combine.rubric_to_100(_rubric(grammar=5, vocabulary=5, politeness=5)) == 100.0


def test_scripted_only_uses_pron() -> None:
    c = combine.combine_scores(pron_score=78.0, rubric=None)
    assert c.pron_score == 78.0
    assert c.rubric_score is None
    assert c.combined_score == 78.0
    assert c.task_completed is None
    assert c.cefr_estimate is None


def test_combined_weighted_average_with_task_bonus() -> None:
    # A=80, B=80 → 平均 80、タスク達成 +5 = 85
    c = combine.combine_scores(pron_score=80.0, rubric=_rubric(task_completed=True))
    assert c.rubric_score == 80.0
    assert c.combined_score == 85.0
    assert c.task_completed is True
    assert c.jlpt_estimate == "N4"  # A2 → N4


def test_task_failure_penalty() -> None:
    c = combine.combine_scores(pron_score=80.0, rubric=_rubric(task_completed=False))
    # 平均 80 - 10 ペナルティ = 70
    assert c.combined_score == 70.0


def test_passline_offset_and_clamp() -> None:
    c = combine.combine_scores(pron_score=78.0, rubric=None)
    # combined 78 - 15 オフセット = 63
    assert c.kaigo_passline_pct == 63.0
    # 下限クランプ: 低スコアでも 0 未満にならない (5 - 15 = -10 → 0)
    low = combine.combine_scores(pron_score=5.0, rubric=None)
    assert low.combined_score == 5.0
    assert low.kaigo_passline_pct == 0.0


def test_rubric_only() -> None:
    c = combine.combine_scores(pron_score=None, rubric=_rubric(task_completed=True))
    assert c.pron_score is None
    assert c.combined_score == 85.0  # 80 + 5


def test_no_signals_is_zero() -> None:
    c = combine.combine_scores(pron_score=None, rubric=None)
    assert c.combined_score == 0.0
    assert c.kaigo_passline_pct == 0.0
