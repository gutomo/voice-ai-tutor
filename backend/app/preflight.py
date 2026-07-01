"""デモ前のワンコマンド プリフライト (Phase 7)。

DEMO_RUNBOOK.md §1 の準備 (DB 疎通 → デモデータのリセット → 台本の通しスモーク) を
1 コマンドにまとめ、緑/赤のチェックリストを出す。商談前にこれ 1 本を流せば
「今日は回る」ことを確認できる。

    cd backend && uv run python -m app.preflight              # フル (チェック + シード + スモーク)
    cd backend && uv run python -m app.preflight --reset-only # 高速リセットのみ (スモーク省略)

外部 API (Azure / Bedrock / SES) が未設定でも赤にしない。未設定は advisory 表示に留め、
判定はローカルで完結する DB 疎通・シード・スモークで下す (DEMO_RUNBOOK.md §4 の
フォールバック方針に合わせる)。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text

from app import combine, seed
from app.config import settings
from app.db import get_engine, init_db

# このファイルは backend/app/preflight.py なので parent.parent = backend/。
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SMOKE_TEST = "tests/test_demo_rehearsal.py"
# ライブ用ベースラインの想定帯: 要フォロー閾値のすぐ上、かつ 60% 未満
# (コホートの「要フォロー 2 名」を崩さず、当日 1 ターンで上へ動かせる)。
_LIVE_BASELINE_HI = 60.0


@dataclass
class Check:
    """プリフライトの 1 判定。ok=False が 1 つでもあれば全体は赤。"""

    name: str
    ok: bool
    detail: str = ""


def _mark(ok: bool) -> str:
    return "[OK]  " if ok else "[FAIL]"


def _check_db() -> Check:
    """設定された DATABASE_URL に接続できるか (money shot の永続化はここ依存)。"""
    try:
        init_db()
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
    except Exception as exc:  # noqa: BLE001 - デモ前チェックなので理由をそのまま見せる
        hint = "`docker compose up -d` で Postgres を起動する"
        return Check("DB reachable", False, f"{type(exc).__name__}: {exc} / {hint}")
    return Check("DB reachable", True, settings.database_url)


def _report_integrations() -> None:
    """実 API の設定状況を advisory 表示する (未設定でもデモは回る)。"""
    print("\n実 API (未設定でも DEMO_RUNBOOK §4 のフォールバックでデモ可):")
    rows = (
        ("Azure Speech (発音採点・TTS)", settings.azure_ready(), "山場はシード済み Dewi で代替"),
        ("Bedrock Claude (会話・採点)", settings.bedrock_ready(), "ロールプレイを飛ばしドリルのみ"),
        ("SES (結果メール)", settings.ses_ready(), "送信ログの status/MessageId を見せる"),
    )
    for label, ready, fallback in rows:
        state = "設定済み" if ready else f"未設定 (→ {fallback})"
        print(f"  {'[OK] ' if ready else '[--] '}{label}: {state}")


def _seed_and_check() -> Check:
    """デモデータをリセット投入し、台本が前提とする形になっているか検証する。"""
    try:
        cohort, (live_name, live) = seed.seed_all()
    except Exception as exc:  # noqa: BLE001
        return Check("Demo data sane", False, f"シード失敗: {type(exc).__name__}: {exc}")

    print("\nデモデータ (リセット済み):")
    for name, prof in cohort:
        print(
            f"  {name:18} passline={prof.kaigo_passline_pct:5.1f}%  "
            f"cefr={prof.cefr_estimate} jlpt={prof.jlpt_estimate}"
        )
    print("  " + "-" * 54)
    print(
        f"  {live_name:18} passline={live.kaigo_passline_pct:5.1f}%  "
        f"cefr={live.cefr_estimate} jlpt={live.jlpt_estimate}  <- ライブ用ベースライン"
    )

    followups = [n for n, p in cohort if p.kaigo_passline_pct < combine.FOLLOWUP_PASSLINE_PCT]
    problems: list[str] = []
    if len(followups) != 2:
        problems.append(f"要フォローが {len(followups)} 名 (2 名のはず): {followups}")
    if not (combine.FOLLOWUP_PASSLINE_PCT <= live.kaigo_passline_pct < _LIVE_BASELINE_HI):
        problems.append(
            f"ライブ用ベースラインが想定帯 "
            f"[{combine.FOLLOWUP_PASSLINE_PCT}, {_LIVE_BASELINE_HI}) の外: "
            f"{live.kaigo_passline_pct}%"
        )
    if problems:
        return Check("Demo data sane", False, "; ".join(problems))
    return Check(
        "Demo data sane",
        True,
        f"cohort 6 名・要フォロー 2 名・ライブ {live.kaigo_passline_pct:.1f}%",
    )


def _run_smoke() -> Check:
    """台本の通しスモーク (外部 API はスタブ) をサブプロセスで実行する。"""
    print(f"\n台本の通しスモーク ({_SMOKE_TEST}, 外部 API はスタブ):")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", _SMOKE_TEST, "-q"],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    ok = proc.returncode == 0
    out = (proc.stdout + proc.stderr).strip().splitlines()
    if ok:
        # 結果サマリ行 ("N passed in Xs") があれば見せ、無ければ rc=0 を成功として合成する。
        passed = next((ln for ln in out if "passed" in ln or "no tests ran" in ln), None)
        print("  " + (passed.strip() if passed else "全テスト成功 (pytest rc=0)"))
    else:
        for line in out[-15:]:
            print("  " + line)
    return Check("Rehearsal smoke", ok, "" if ok else "pytest 失敗 (上のログ参照)")


def _summary(checks: list[Check]) -> int:
    print("\n" + "=" * 60)
    for c in checks:
        line = f"  {_mark(c.ok)} {c.name}"
        if c.detail:
            line += f": {c.detail}"
        print(line)
    print("=" * 60)
    all_ok = all(c.ok for c in checks)
    print("  GREEN: デモ準備 OK" if all_ok else "  RED: 上の [FAIL] を直してから商談へ")
    return 0 if all_ok else 1


def main(argv: list[str] | None = None) -> int:
    # Windows のコンソールは既定 cp1252 で日本語や罫線が UnicodeEncodeError で落ちる。
    # デモ前にいきなり traceback を出さないよう UTF-8 に切り替える (対応環境のみ)。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="デモ前のワンコマンド プリフライト")
    parser.add_argument(
        "--reset-only",
        action="store_true",
        help="スモークを省き DB チェックとシードだけ実行 (デモ間の高速リセット)",
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("  デモ プリフライト (DEMO_RUNBOOK §1 相当)")
    print("=" * 60)

    checks: list[Check] = []
    db = _check_db()
    checks.append(db)
    if not db.ok:
        # DB が無いと以降 (シード・スモーク) が無意味なので早期に赤で返す。
        return _summary(checks)

    _report_integrations()
    checks.append(_seed_and_check())
    if not args.reset_only:
        checks.append(_run_smoke())

    return _summary(checks)


if __name__ == "__main__":
    raise SystemExit(main())
