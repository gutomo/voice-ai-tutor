"""ワンコマンド プリフライト (Phase 7) のテスト。

DB は in-memory SQLite (`db` フィクスチャ)。実 Postgres・pytest サブプロセスには触れず、
DB 疎通チェックとシード検証、`--reset-only` の合否ロジックだけを確かめる
(実スモークは test_demo_rehearsal.py 本体が担う)。
"""

import pytest

from app import combine, preflight, seed
from app.config import settings


@pytest.fixture(autouse=True)
def _uploads(db, tmp_path, monkeypatch):
    # `db` フィクスチャ (引数) が in-memory SQLite を構成する。
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


def test_check_db_ok_on_sqlite() -> None:
    check = preflight._check_db()
    assert check.ok, check.detail


def test_seed_and_check_passes_for_healthy_data() -> None:
    check = preflight._seed_and_check()
    assert check.ok, check.detail
    # 台本が前提とする形: 要フォロー 2 名 + ライブ用ベースライン。
    assert "要フォロー 2 名" in check.detail


def test_seed_and_check_fails_when_followups_off(monkeypatch) -> None:
    # コホート全員を強学習者にすると要フォロー 0 名 → 台本 (要フォロー 2 名) が崩れ赤。
    strong = [seed._Spec(spec.name, 90) for spec in seed._COHORT]
    monkeypatch.setattr(seed, "_COHORT", strong)
    check = preflight._seed_and_check()
    assert not check.ok
    assert "要フォロー" in check.detail


def test_reset_only_returns_zero_without_running_smoke(monkeypatch) -> None:
    # --reset-only はサブプロセスのスモークを呼ばない。呼んだら失敗させて検出する。
    def _boom() -> preflight.Check:
        raise AssertionError("--reset-only なのにスモークが実行された")

    monkeypatch.setattr(preflight, "_run_smoke", _boom)
    assert preflight.main(["--reset-only"]) == 0


def test_full_run_invokes_smoke_and_reports_its_result(monkeypatch) -> None:
    # スモークをスタブ (実 pytest サブプロセスは走らせない)。失敗を返すと全体が赤 (=1)。
    monkeypatch.setattr(
        preflight, "_run_smoke", lambda: preflight.Check("Rehearsal smoke", False, "stub fail")
    )
    assert preflight.main([]) == 1

    monkeypatch.setattr(preflight, "_run_smoke", lambda: preflight.Check("Rehearsal smoke", True))
    assert preflight.main([]) == 0


def test_followup_threshold_matches_combine() -> None:
    # プリフライトが使う閾値は本番ロジック (combine) と同じ 1 か所を参照する。
    assert combine.FOLLOWUP_PASSLINE_PCT == 50.0
