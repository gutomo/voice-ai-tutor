"""Azure 生 JSON のパース純関数のテスト (ネットワーク/SDK 不要)。"""

import json
from pathlib import Path

from app.parsing import extract_weak_phonemes, extract_weak_words, extract_words

RAW = json.loads((Path(__file__).parent / "data" / "sample_pa_result.json").read_text("utf-8"))


def test_extract_words() -> None:
    words = extract_words(RAW)
    assert [w["word"] for w in words] == ["おはよう", "体温", "を"]
    assert words[0]["accuracy"] == 92.0


def test_extract_weak_words() -> None:
    weak = extract_weak_words(RAW)
    # 体温 だけが AccuracyScore<60 / Mispronunciation
    assert [w["word"] for w in weak] == ["体温"]
    assert weak[0]["error_type"] == "Mispronunciation"


def test_extract_weak_phonemes() -> None:
    weak = extract_weak_phonemes(RAW)
    # t (38.0) のみが 60 未満
    assert len(weak) == 1
    assert weak[0]["word"] == "体温"
    assert weak[0]["accuracy"] == 38.0


def test_empty_nbest_is_safe() -> None:
    assert extract_words({}) == []
    assert extract_weak_words({"NBest": []}) == []
    assert extract_weak_phonemes({"NBest": []}) == []
