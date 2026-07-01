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
