"""録音ターン採点パイプラインの一括同期関数。

audio(ffmpeg) と speech(Azure SDK) はどちらもブロッキングなので、ルート側からは
run_in_threadpool でこの 1 関数をまとめて呼ぶ (スレッド往復を 1 回に抑える)。
"""

import tempfile
import time
from pathlib import Path

from app import audio, parsing, speech
from app.schemas import PronunciationResult, WeakPhoneme, WordScore

_MAX_ATTEMPTS = 2


def score_turn_sync(
    src_audio: Path,
    turn_id: str,
    reference_text: str,
    key: str,
    region: str,
) -> PronunciationResult:
    """元音声 → WAV 変換 → Azure scripted 採点 → 結果整形。元の webm は残す。"""
    # WAV は専用の一時ディレクトリに作る。uploads/ には置かない
    # (GET /api/turn/{id}/audio の glob {id}.* が .wav を拾うのを防ぐ)。
    with tempfile.TemporaryDirectory(prefix="score-") as tmp:
        wav = Path(tmp) / f"{turn_id}.wav"
        audio.to_wav_16k_mono(src_audio, wav)

        last_err: speech.SpeechError | None = None
        result: dict | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                result = speech.assess_scripted(wav, reference_text, key, region)
                break
            except speech.SpeechError as e:
                last_err = e
                if not e.retriable or attempt == _MAX_ATTEMPTS:
                    raise
                time.sleep(0.5 * attempt)
        if result is None:  # 念のため (ループは raise か break で必ず抜ける)
            raise last_err or speech.SpeechError("採点に失敗しました")

    raw = result.get("raw", {})
    return PronunciationResult(
        turn_id=turn_id,
        reference_text=reference_text,
        transcript=result.get("transcript", ""),
        accuracy=result["accuracy"],
        fluency=result["fluency"],
        completeness=result["completeness"],
        pron_score=result["pron_score"],
        words=[WordScore(**w) for w in parsing.extract_words(raw)],
        weak_words=[WordScore(**w) for w in parsing.extract_weak_words(raw)],
        weak_phonemes=[WeakPhoneme(**p) for p in parsing.extract_weak_phonemes(raw)],
        raw=raw,
    )
