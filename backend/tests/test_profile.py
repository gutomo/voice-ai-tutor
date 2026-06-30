"""プロファイル推定 (純関数) のユニットテスト。DB も外部 API も使わない。"""

from app import combine, profile


def test_empty_scores() -> None:
    est = profile.estimate_profile([])
    assert est.turns_count == 0
    assert est.kaigo_passline_pct == 0.0
    assert est.cefr_estimate is None


def test_empty_scores_with_latest_cefr() -> None:
    # まだ採点ターンは無いが、過去の CEFR だけ分かっているケース
    est = profile.estimate_profile([], latest_cefr="A2")
    assert est.cefr_estimate == "A2"
    assert est.jlpt_estimate == "N4"
    assert est.kaigo_passline_pct == 0.0


def test_single_score_band_and_passline() -> None:
    est = profile.estimate_profile([84.0])
    assert est.combined_avg == 84.0
    assert est.kaigo_passline_pct == 84.0 - combine.PASSLINE_OFFSET  # 69.0
    assert est.cefr_estimate == "B1"  # 帯フォールバック (>=70)
    assert est.jlpt_estimate == "N3"


def test_average_moves_with_more_turns() -> None:
    one = profile.estimate_profile([84.0])
    two = profile.estimate_profile([84.0, 90.0])
    assert two.combined_avg == 87.0
    assert two.turns_count == 2
    assert two.kaigo_passline_pct != one.kaigo_passline_pct
    assert two.kaigo_passline_pct == round(87.0 - combine.PASSLINE_OFFSET, 1)  # 72.0


def test_rubric_cefr_overrides_band() -> None:
    # combined 平均は低くても、直近ルーブリックの CEFR を優先する
    est = profile.estimate_profile([60.0], latest_cefr="A2")
    assert est.cefr_estimate == "A2"
    assert est.jlpt_estimate == "N4"
    assert est.kaigo_passline_pct == 45.0


def test_cefr_from_combined_bands() -> None:
    assert profile.cefr_from_combined(95.0) == "B1"
    assert profile.cefr_from_combined(50.0) == "A2"
    assert profile.cefr_from_combined(10.0) == "A1"
