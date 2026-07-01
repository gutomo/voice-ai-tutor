"""結果メールの本文生成と SES 送信 (Phase 6)。

役割分担:
- 本文生成 (`build_learner_email` / `build_teacher_email`) は外部 I/O を持たない純関数。
  スキーマ (SessionReport / LearnerOut) を受け取り `EmailContent` を返すのでユニットテストが容易。
- 送信 (`send_email`) は SES ラッパ。bedrock.py と同じ思想:
  - boto3 は関数内で遅延 import (スタブするテスト / CI では boto3 不要)。
  - 認証情報は引数で受け取り、ログに出さない。
  - 一時エラー (Throttling 等) は retriable=True にする。

説明文は Bahasa Indonesia を主、練習内容・スコア名は日本語 (CLAUDE.md「2言語を混ぜない」)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app import combine, scenarios
from app.schemas import LearnerOut, SessionReport, TurnOut


class EmailError(RuntimeError):
    """SES 送信が失敗した。retriable=True は一時的エラー (リトライ可)。"""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text_body: str
    html_body: str


# --- 素材の抽出 (純関数) ---


def _latest_pron_turn(turns: list[TurnOut]) -> TurnOut | None:
    for t in reversed(turns):  # turns は古い順 → 直近を優先する
        if t.pron_accuracy is not None:
            return t
    return None


def _latest_rubric(turns: list[TurnOut]) -> dict[str, Any] | None:
    for t in reversed(turns):
        if t.rubric:
            return t.rubric
    return None


def _conversation_5(rubric: dict[str, Any] | None) -> float | None:
    """ルーブリック (grammar/vocabulary/politeness, 0-5) の平均を返す。"""
    if not rubric:
        return None
    vals = [rubric.get("grammar"), rubric.get("vocabulary"), rubric.get("politeness")]
    nums = [float(v) for v in vals if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 1)


def _passline(learner: LearnerOut) -> float:
    return learner.profile.kaigo_passline_pct if learner.profile else 0.0


def _weak_words(turns: list[TurnOut], limit: int = 3) -> list[tuple[str, float | None]]:
    """セッション全ターンの「弱い単語」を集約し、accuracy の低い順に最大 limit 件返す。

    同じ単語は最も低い accuracy を残す (最新のターンだけだと弱点を取りこぼすため全ターン集約)。
    """
    worst: dict[str, float | None] = {}
    for t in turns:
        for w in t.weak_phonemes or []:
            if not (isinstance(w, dict) and w.get("word")):
                continue
            word = str(w["word"])
            acc = w.get("accuracy")
            prev = worst.get(word, None)
            # 未登録、または今回の方が低い accuracy なら更新する (None は「最悪」扱い)。
            if word not in worst:
                worst[word] = acc
            elif acc is not None and (prev is None or acc < prev):
                worst[word] = acc
    ranked = sorted(
        worst.items(), key=lambda kv: (kv[1] is not None, kv[1] if kv[1] is not None else 0)
    )
    return ranked[:limit]


# --- 学習者向けまとめメール ---


def build_learner_email(report: SessionReport, next_url: str) -> EmailContent:
    """学習者へのまとめメール (スコア + 次回リンク、Bahasa + 日本語)。"""
    learner = report.learner
    sc = scenarios.get_scenario(report.session.scenario)
    title_ja = sc.title_ja if sc else report.session.scenario
    title_id = sc.title_id if sc else ""

    pron_turn = _latest_pron_turn(report.turns)
    # _latest_pron_turn は pron_accuracy が None でないターンだけ返す (0.0 も有効な値)。
    pron = round(pron_turn.pron_accuracy, 1) if pron_turn else None
    conv = _conversation_5(_latest_rubric(report.turns))
    passline = _passline(learner)
    prof = learner.profile
    cefr = prof.cefr_estimate if prof else None
    jlpt = prof.jlpt_estimate if prof else None
    weak = _weak_words(report.turns)

    subject = "【日本語練習】今日のまとめ / Ringkasan latihan hari ini"

    lines: list[str] = [
        f"Halo {learner.name},",
        "",
        "Kerja bagus hari ini! Berikut ringkasan latihan bahasa Jepang Anda.",
        "今日の練習、おつかれさまでした。今日のまとめです。",
        "",
        f"レッスン / Pelajaran: {title_ja}" + (f" ({title_id})" if title_id else ""),
        "",
        "■ 今日のスコア / Skor hari ini",
        f"- 発音 / Pengucapan: {pron if pron is not None else '—'}/100",
        f"- 会話 / Percakapan: {conv if conv is not None else '—'}/5",
        f"- 合格ライン到達度 / Estimasi menuju lulus (介護日本語評価試験): {passline}%",
        f"- 推定レベル / Perkiraan level: {cefr or '—'}" + (f" ({jlpt})" if jlpt else ""),
    ]
    if weak:
        lines += ["", "■ 次に練習する音 / Latih pengucapan lagi:"]
        for word, acc in weak:
            lines.append(f"- {word}" + (f" ({round(acc)}/100)" if acc is not None else ""))
    lines += [
        "",
        "次のレッスンはこちら / Lanjutkan latihan berikutnya:",
        next_url,
        "",
        "がんばってください！ Semangat! 💪",
    ]
    text_body = "\n".join(lines)

    weak_html = ""
    if weak:
        items = "".join(
            f"<li>{word}" + (f" <b>({round(acc)}/100)</b>" if acc is not None else "") + "</li>"
            for word, acc in weak
        )
        weak_html = "<h3>次に練習する音 / Latih pengucapan lagi</h3>" f"<ul>{items}</ul>"
    html_body = (
        f"<div style='font-family:sans-serif;max-width:520px'>"
        f"<p>Halo <b>{learner.name}</b>,</p>"
        f"<p>Kerja bagus hari ini! 今日の練習、おつかれさまでした。</p>"
        f"<p><b>レッスン / Pelajaran:</b> {title_ja}"
        + (f" ({title_id})" if title_id else "")
        + "</p>"
        "<h3>今日のスコア / Skor hari ini</h3>"
        "<ul>"
        f"<li>発音 / Pengucapan: <b>{pron if pron is not None else '—'}/100</b></li>"
        f"<li>会話 / Percakapan: <b>{conv if conv is not None else '—'}/5</b></li>"
        f"<li>合格ライン到達度 / Estimasi lulus: <b>{passline}%</b></li>"
        f"<li>推定レベル / Level: <b>{cefr or '—'}</b>" + (f" ({jlpt})" if jlpt else "") + "</li>"
        "</ul>"
        f"{weak_html}"
        f"<p><a href='{next_url}'>次のレッスンへ / Lanjutkan latihan &raquo;</a></p>"
        "<p>がんばってください！ Semangat! 💪</p>"
        "</div>"
    )
    return EmailContent(subject=subject, text_body=text_body, html_body=html_body)


# --- 教師向けクラスレポート ---


def build_teacher_email(
    cohort: list[LearnerOut],
    *,
    scenario: str,
    as_of: datetime,
    focus_learner: LearnerOut | None = None,
) -> EmailContent:
    """教師へのクラスレポート (当日サマリ + 要フォロー学習者、Bahasa + 日本語)。"""
    sc = scenarios.get_scenario(scenario)
    title_ja = sc.title_ja if sc else scenario
    date_str = as_of.strftime("%Y-%m-%d")

    # 到達度で降順 (合格圏が上、伸び悩みが下)。
    ranked = sorted(cohort, key=_passline, reverse=True)
    followups = [le for le in cohort if _passline(le) < combine.FOLLOWUP_PASSLINE_PCT]

    subject = f"【クラスレポート】{title_ja} {date_str} / Laporan kelas"

    lines: list[str] = [
        f"{date_str} クラスレポート / Laporan kelas ({len(cohort)}名)",
        f"レッスン / Pelajaran: {title_ja}",
    ]
    if focus_learner is not None:
        lines += [
            "",
            f"直近で終了 / Baru saja selesai: {focus_learner.name} — "
            f"到達度 {_passline(focus_learner)}%",
        ]
    lines += ["", "■ 合格ライン到達度 / Estimasi lulus per siswa"]
    for le in ranked:
        flag = " ⚠ 要フォロー" if _passline(le) < combine.FOLLOWUP_PASSLINE_PCT else ""
        prof = le.profile
        cefr = prof.cefr_estimate if prof else "—"
        lines.append(f"- {le.name}: {_passline(le)}% ({cefr}){flag}")

    lines += ["", f"■ 要フォロー / Perlu perhatian ({len(followups)}名)"]
    if followups:
        for le in followups:
            lines.append(f"- {le.name} ({_passline(le)}%)")
    else:
        lines.append("- 該当なし / Tidak ada siswa yang perlu perhatian khusus")
    text_body = "\n".join(lines)

    roster_html = "".join(
        f"<tr><td>{le.name}</td><td align='right'><b>{_passline(le)}%</b></td>"
        f"<td>{(le.profile.cefr_estimate if le.profile else '—')}</td>"
        f"<td>{'⚠' if _passline(le) < combine.FOLLOWUP_PASSLINE_PCT else ''}</td></tr>"
        for le in ranked
    )
    followup_html = (
        "".join(f"<li>{le.name} ({_passline(le)}%)</li>" for le in followups)
        if followups
        else "<li>該当なし / Tidak ada</li>"
    )
    focus_html = (
        f"<p><b>直近で終了 / Baru saja selesai:</b> {focus_learner.name} — "
        f"{_passline(focus_learner)}%</p>"
        if focus_learner is not None
        else ""
    )
    html_body = (
        f"<div style='font-family:sans-serif;max-width:640px'>"
        f"<h2>{date_str} クラスレポート / Laporan kelas ({len(cohort)}名)</h2>"
        f"<p><b>レッスン / Pelajaran:</b> {title_ja}</p>"
        f"{focus_html}"
        "<h3>合格ライン到達度 / Estimasi lulus per siswa</h3>"
        "<table cellpadding='4' style='border-collapse:collapse'>"
        "<tr><th align='left'>学習者</th><th>到達度</th><th>CEFR</th><th></th></tr>"
        f"{roster_html}</table>"
        f"<h3>要フォロー / Perlu perhatian ({len(followups)}名)</h3>"
        f"<ul>{followup_html}</ul>"
        "</div>"
    )
    return EmailContent(subject=subject, text_body=text_body, html_body=html_body)


# --- SES 送信 ---


def _client(region: str, access_key: str, secret_key: str) -> Any:
    # 遅延 import: スタブ時 / CI ではここに到達しないので boto3 不要。
    import boto3

    return boto3.client(
        "ses",
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def send_email(
    content: EmailContent,
    *,
    sender: str,
    recipient: str,
    region: str,
    access_key: str,
    secret_key: str,
) -> str:
    """1 通を SES で送る。成功したら MessageId を返す。失敗は EmailError。"""
    client = _client(region, access_key, secret_key)
    try:
        resp = client.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": content.subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": content.text_body, "Charset": "UTF-8"},
                    "Html": {"Data": content.html_body, "Charset": "UTF-8"},
                },
            },
        )
    except Exception as e:  # noqa: BLE001 - boto3 例外を import せず横断的に扱う
        name = type(e).__name__
        retriable = any(k in name for k in ("Throttling", "Timeout", "ServiceUnavailable"))
        # SES の本文 (str(e)) を残す (例: サンドボックスの未検証宛先)。認証情報は含まない。
        raise EmailError(f"SES 送信に失敗しました ({name}): {e}", retriable=retriable) from e

    try:
        return str(resp["MessageId"])
    except (KeyError, TypeError) as e:
        raise EmailError("SES 応答の形式が想定外です") from e
