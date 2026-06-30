"""発音(A) + 会話(B) + タスク達成(C) を学習者スコアへ合成する純関数 (DESIGN §3)。

外部 API を呼ばないのでユニットテストが容易。デモ用の簡易ロジックであり、
本番では過去問データに基づくマッピングへ差し替える前提 (係数はここに集約)。
"""

from app.schemas import CombinedScore, RubricScore

# 重み: 発音と会話を半々で合成する (デモの初期値)。
PRON_WEIGHT = 0.5
# タスク達成のボーナス / 未達のペナルティ (combined_score への加点)。
TASK_BONUS = 5.0
TASK_PENALTY = 10.0
# 合格ライン到達度の推定オフセット: combined_score からこの値を引く (デモ用ヒューリスティック)。
# 例: combined 78 → 約 63% (DESIGN §2 の "推定 62%" に整合)。
PASSLINE_OFFSET = 15.0

# CEFR → JLPT のざっくり対応 (デモ表示用)。
_CEFR_TO_JLPT = {"A1": "N5", "A2": "N4", "B1": "N3", "B2": "N2", "C1": "N1"}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def rubric_to_100(rubric: RubricScore) -> float:
    """grammar / vocabulary / politeness の平均 (0-5) を 100 点換算する。"""
    avg = (rubric.grammar + rubric.vocabulary + rubric.politeness) / 3
    return round(avg * 20, 1)


def jlpt_from_cefr(cefr: str | None) -> str | None:
    if not cefr:
        return None
    return _CEFR_TO_JLPT.get(cefr.upper().strip())


def combine_scores(
    pron_score: float | None = None,
    rubric: RubricScore | None = None,
    *,
    pron_weight: float = PRON_WEIGHT,
) -> CombinedScore:
    """利用可能な信号 (A / B / C) を合成する。

    - A と B が両方ある: 重み付き平均にタスク達成のボーナス/ペナルティ。
    - 片方だけ: その点をベースにタスク達成を加味。
    - どちらも無い: 0 点。
    """
    rubric_100 = rubric_to_100(rubric) if rubric is not None else None
    task_completed = rubric.task_completed if rubric is not None else None

    if pron_score is not None and rubric_100 is not None:
        base = pron_weight * pron_score + (1 - pron_weight) * rubric_100
    elif pron_score is not None:
        base = pron_score
    elif rubric_100 is not None:
        base = rubric_100
    else:
        base = 0.0

    if task_completed is True:
        base += TASK_BONUS
    elif task_completed is False:
        base -= TASK_PENALTY

    combined = round(_clamp(base), 1)
    cefr = rubric.cefr_estimate if rubric is not None else None
    return CombinedScore(
        pron_score=pron_score,
        rubric_score=rubric_100,
        task_completed=task_completed,
        combined_score=combined,
        cefr_estimate=cefr,
        jlpt_estimate=jlpt_from_cefr(cefr),
        kaigo_passline_pct=round(_clamp(combined - PASSLINE_OFFSET), 1),
    )
