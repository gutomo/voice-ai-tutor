"""録音ターン採点パイプラインの同期関数。

audio(ffmpeg) と speech(Azure SDK) はどちらもブロッキングなので、ルート側からは
run_in_threadpool でこれらをまとめて呼ぶ (スレッド往復を抑える)。

- score_turn_sync: 復唱ドリル (scripted)。既知のモデル文を参照に採点。
- score_roleplay_sync: ロールプレイ (free)。先に STT → その文を参照に scripted。
  (DESIGN §3 の二段採点)
"""

import tempfile
import time
from pathlib import Path

from app import audio, parsing, speech
from app.schemas import PronunciationResult, WeakPhoneme, WordScore

_MAX_ATTEMPTS = 2


def _assess_with_retry(wav: Path, reference_text: str, key: str, region: str) -> dict:
    """一時的エラーは _MAX_ATTEMPTS 回までリトライしつつ scripted 採点する。"""
    last_err: speech.SpeechError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            return speech.assess_scripted(wav, reference_text, key, region)
        except speech.SpeechError as e:
            last_err = e
            if not e.retriable or attempt == _MAX_ATTEMPTS:
                raise
            time.sleep(0.5 * attempt)
    raise last_err or speech.SpeechError("採点に失敗しました")  # 到達しない (ループは必ず抜ける)


def _build_result(turn_id: str, reference_text: str, result: dict) -> PronunciationResult:
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
        result = _assess_with_retry(wav, reference_text, key, region)
    return _build_result(turn_id, reference_text, result)


def score_roleplay_sync(
    src_audio: Path,
    turn_id: str,
    key: str,
    region: str,
) -> PronunciationResult:
    """自由発話の二段採点。先に STT で文字起こし → その文を参照に scripted 採点する。

    自由発話には既知のモデル文が無いので、認識結果を参照テキストにして音素レベルの
    弱点を取る。completeness は参照=発話なので高めに出る (DESIGN §3 の注記どおり)。
    """
    with tempfile.TemporaryDirectory(prefix="score-") as tmp:
        wav = Path(tmp) / f"{turn_id}.wav"
        audio.to_wav_16k_mono(src_audio, wav)
        transcript = speech.transcribe(wav, key, region)
        if not transcript.strip():
            raise speech.NoSpeechError()
        result = _assess_with_retry(wav, transcript, key, region)
    return _build_result(turn_id, transcript, result)
