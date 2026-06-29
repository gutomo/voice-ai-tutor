"""Azure 発音評価の生 JSON を、学習者向けの扱いやすい形に変換する純関数群。

SDK を import しないので、固定の JSON だけでユニットテストできる (ネイティブ依存なし)。
ja-JP では音素「名」は意味を持たない (英語のみ) ため、学習者向けの主役は
弱い「単語」リスト (単語 AccuracyScore < しきい値、または ErrorType あり)。
"""

from typing import Any

WEAK_WORD_THRESHOLD = 60.0
WEAK_PHONEME_THRESHOLD = 60.0


def _nbest_words(raw: dict[str, Any]) -> list[dict[str, Any]]:
    nbest = raw.get("NBest") or []
    if not nbest:
        return []
    return nbest[0].get("Words", []) or []


def extract_words(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """全単語の {word, accuracy, error_type} リスト。"""
    out: list[dict[str, Any]] = []
    for w in _nbest_words(raw):
        pa = w.get("PronunciationAssessment", {}) or {}
        out.append(
            {
                "word": w.get("Word", ""),
                "accuracy": pa.get("AccuracyScore"),
                "error_type": pa.get("ErrorType", "None"),
            }
        )
    return out


def extract_weak_words(
    raw: dict[str, Any], threshold: float = WEAK_WORD_THRESHOLD
) -> list[dict[str, Any]]:
    """要練習の単語: AccuracyScore < threshold もしくは ErrorType が None 以外。"""
    out: list[dict[str, Any]] = []
    for w in _nbest_words(raw):
        pa = w.get("PronunciationAssessment", {}) or {}
        acc = pa.get("AccuracyScore")
        err = pa.get("ErrorType", "None")
        if (acc is not None and acc < threshold) or (err and err != "None"):
            out.append({"word": w.get("Word", ""), "accuracy": acc, "error_type": err})
    return out


def extract_weak_phonemes(
    raw: dict[str, Any], threshold: float = WEAK_PHONEME_THRESHOLD
) -> list[dict[str, Any]]:
    """要練習の音素 (数値スコアのみ。ja-JP では phoneme ラベルは不透明)。"""
    out: list[dict[str, Any]] = []
    for w in _nbest_words(raw):
        word_text = w.get("Word", "")
        for ph in w.get("Phonemes", []) or []:
            score = (ph.get("PronunciationAssessment", {}) or {}).get("AccuracyScore")
            if score is not None and score < threshold:
                out.append(
                    {
                        "word": word_text,
                        "phoneme": ph.get("Phoneme", ""),
                        "accuracy": score,
                    }
                )
    return out
