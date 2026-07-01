"""デモコホートのシード (Phase 5) のテスト。

`/api/learners` がプロファイル付きで返ること、要フォロー (合格ライン < 50%) が
ちょうど 2 名いること、会話ログ用の音声ファイルが置かれることを検証する。
DB は in-memory SQLite。
"""

from pathlib import Path

import pytest

from app import seed
from app.config import settings

FOLLOWUP_THRESHOLD = 50.0  # frontend の要フォロー閾値と揃える。


@pytest.fixture(autouse=True)
def _uploads(db, tmp_path, monkeypatch):
    # `db` フィクスチャ (引数) が in-memory SQLite を構成する。
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


def test_seed_populates_cohort() -> None:
    rows = seed.seed_demo()
    assert len(rows) == len(seed._COHORT)
    # 全員にプロファイル (合格ライン到達度) が付いている。
    for _name, prof in rows:
        assert prof.kaigo_passline_pct >= 0.0
        assert prof.cefr_estimate is not None
        assert prof.jlpt_estimate is not None


def test_seed_flags_two_followups() -> None:
    rows = seed.seed_demo()
    followups = [name for name, prof in rows if prof.kaigo_passline_pct < FOLLOWUP_THRESHOLD]
    assert len(followups) == 2, {name: prof.kaigo_passline_pct for name, prof in rows}


def test_seed_is_idempotent() -> None:
    """再実行しても学習者は重複しない (同名を消してから作り直す)。"""
    from app import persistence

    seed.seed_demo()
    seed.seed_demo()
    learners = persistence.list_learners()
    assert len(learners) == len(seed._COHORT)
    # list_learners がプロファイルを読み込めている (ダッシュボードのコホート表)。
    assert all(le.profile is not None for le in learners)


def test_seed_writes_audio_files(tmp_path) -> None:
    seed.seed_demo()
    wavs = list(Path(tmp_path).glob("*.wav"))
    # 6 名 × 5 ターン分の無音 WAV が置かれる。
    assert len(wavs) == len(seed._COHORT) * 5


def test_seed_turns_have_pron_and_rubric() -> None:
    from app import persistence

    seed.seed_demo()
    learners = persistence.list_learners()
    # 最後 = 最弱 (Putra)。要練習語があり発音ヒートマップの素になる。
    turns = persistence.get_learner_turns(learners[-1].id)
    assert len(turns) == 5
    assert any(t.rubric is not None for t in turns)  # ロールプレイ
    assert any(t.weak_phonemes for t in turns)  # 発音ヒートマップの素


# --- ライブ用のデモ学習者 (Phase 7) ---


def test_seed_live_demo_has_short_baseline() -> None:
    from app import persistence

    name, prof = seed.seed_live_demo()
    assert name == seed.LIVE_DEMO_NAME
    learner = next(le for le in persistence.list_learners() if le.name == name)
    turns = persistence.get_learner_turns(learner.id)
    # 短いベースライン (ドリル 2 ターン)。ライブで足す余地を残す。
    assert len(turns) == 2
    # 各ターンに要練習語 → ライブ前でも発音ヒートマップに素材がある。
    assert all(t.weak_phonemes for t in turns)
    assert prof.cefr_estimate is not None


def test_seed_live_demo_not_flagged_at_start() -> None:
    """ライブ前は要フォロー閾値のすぐ上 (コホートの「要フォロー 2 名」を崩さない)。"""
    _name, prof = seed.seed_live_demo()
    assert FOLLOWUP_THRESHOLD <= prof.kaigo_passline_pct < 60.0


def test_seed_live_demo_is_idempotent() -> None:
    from app import persistence

    seed.seed_live_demo()
    seed.seed_live_demo()
    matches = [le for le in persistence.list_learners() if le.name == seed.LIVE_DEMO_NAME]
    assert len(matches) == 1
    assert len(persistence.get_learner_turns(matches[0].id)) == 2


def test_seed_all_sets_up_cohort_and_live_demo() -> None:
    from app import persistence

    cohort, (live_name, _live_prof) = seed.seed_all()
    assert len(cohort) == len(seed._COHORT)
    # コホートの要フォローはちょうど 2 名のまま (ライブ用学習者は閾値の上)。
    followups = [name for name, prof in cohort if prof.kaigo_passline_pct < FOLLOWUP_THRESHOLD]
    assert len(followups) == 2
    names = {le.name for le in persistence.list_learners()}
    assert live_name in names
    assert len(names) == len(seed._COHORT) + 1
