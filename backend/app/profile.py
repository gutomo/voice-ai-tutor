"""学習者プロファイルの推定 (DESIGN §3 の簡易ロジック)。

複数ターンの combined_score を集約して合格ライン到達度 (%) を出す。CEFR は直近の
ルーブリック判定 (Claude) を優先し、無ければ combined の平均から帯で代替する。
外部 API も DB も触らない純関数なのでユニットテストが容易 (係数は combine.py に集約)。
"""

from dataclasses import dataclass

from app import combine

# combined_score の平均 → CEFR のざっくり対応 (ルーブリック cefr が無いときの代替)。
# 高い順に評価し、最初に閾値を満たした帯を採用する。
_CEFR_BANDS: list[tuple[float, str]] = [(70.0, "B1"), (45.0, "A2"), (0.0, "A1")]


@dataclass(frozen=True)
class ProfileEstimate:
    cefr_estimate: str | None
    jlpt_estimate: str | None
    kaigo_passline_pct: float
    combined_avg: float
    turns_count: int


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def cefr_from_combined(avg: float) -> str:
    for threshold, label in _CEFR_BANDS:
        if avg >= threshold:
            return label
    return "A1"


def estimate_profile(
    combined_scores: list[float],
    latest_cefr: str | None = None,
) -> ProfileEstimate:
    """採点済みターンの combined_score 群から現在のプロファイルを推定する。

    - combined_scores: そのターンの合成点 (0-100)。空ならまだ未採点。
    - latest_cefr: 直近のロールプレイで Claude が出した CEFR (あれば優先)。
    """
    if not combined_scores:
        return ProfileEstimate(
            cefr_estimate=latest_cefr,
            jlpt_estimate=combine.jlpt_from_cefr(latest_cefr),
            kaigo_passline_pct=0.0,
            combined_avg=0.0,
            turns_count=0,
        )

    avg = sum(combined_scores) / len(combined_scores)
    cefr = latest_cefr or cefr_from_combined(avg)
    # 合格ライン到達度は combine.py と同じオフセットで per-turn と整合させる。
    passline = round(_clamp(avg - combine.PASSLINE_OFFSET), 1)
    return ProfileEstimate(
        cefr_estimate=cefr,
        jlpt_estimate=combine.jlpt_from_cefr(cefr),
        kaigo_passline_pct=passline,
        combined_avg=round(avg, 1),
        turns_count=len(combined_scores),
    )
