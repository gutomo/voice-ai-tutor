"""Azure Speech SDK の薄いラッパ (ja-JP scripted 発音採点)。

設計上の要点:
- `import azure...` は関数内で遅延 import する。モジュール import 時にネイティブ .so を
  ロードしないので、スタブするユニットテストや CI ではネイティブ依存が不要になる。
- 鍵/リージョンは引数で受け取り、絶対にログに出さない。
"""

import json
from pathlib import Path
from typing import Any


class SpeechError(RuntimeError):
    """Azure 発音採点が失敗した。retriable=True は一時的エラー (リトライ可)。"""

    def __init__(self, message: str, *, retriable: bool = False) -> None:
        super().__init__(message)
        self.retriable = retriable


class NoSpeechError(SpeechError):
    """音声が認識されなかった (無音/短すぎ)。学習者には録り直しを促す。"""

    def __init__(self, message: str = "音声を認識できませんでした") -> None:
        super().__init__(message, retriable=False)


class SpeechNotConfigured(RuntimeError):
    """AZURE_SPEECH_KEY / REGION が未設定。"""


def transcribe(wav_path: Path, key: str, region: str) -> str:
    """自由発話の STT (ja-JP)。ロールプレイで学習者の発話を文字起こしする。

    DESIGN §3 の二段採点 (先に STT → その文を参照に scripted) の前段に使う。
    """
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = "ja-JP"
    audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))
    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    result = recognizer.recognize_once()
    if result.reason == speechsdk.ResultReason.NoMatch:
        raise NoSpeechError()
    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        retriable = details.reason == speechsdk.CancellationReason.Error
        raise SpeechError(f"認識がキャンセルされました: {details.reason}", retriable=retriable)
    if result.reason != speechsdk.ResultReason.RecognizedSpeech:
        raise SpeechError(f"認識に失敗しました: {result.reason}", retriable=False)
    return result.text


def assess_scripted(wav_path: Path, reference_text: str, key: str, region: str) -> dict[str, Any]:
    """既知のモデル文に対する scripted 発音採点。WAV(16k/mono/16bit) を渡すこと。"""
    # 遅延 import: スタブ時/CI ではここに到達しないのでネイティブロードを避けられる
    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_recognition_language = "ja-JP"
    audio_config = speechsdk.audio.AudioConfig(filename=str(wav_path))

    pa_config = speechsdk.PronunciationAssessmentConfig(
        reference_text=reference_text,
        grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
        granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
        enable_miscue=True,
    )
    # ja-JP は prosody 非対応なので enable_prosody_assessment() は呼ばない。

    recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)
    pa_config.apply_to(recognizer)

    result = recognizer.recognize_once()

    if result.reason == speechsdk.ResultReason.NoMatch:
        raise NoSpeechError()
    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        # 一時的なネットワーク/スロットリングはリトライ可とみなす
        retriable = details.reason == speechsdk.CancellationReason.Error
        raise SpeechError(f"認識がキャンセルされました: {details.reason}", retriable=retriable)
    if result.reason != speechsdk.ResultReason.RecognizedSpeech:
        raise SpeechError(f"認識に失敗しました: {result.reason}", retriable=False)

    pa = speechsdk.PronunciationAssessmentResult(result)
    raw_json = result.properties.get(speechsdk.PropertyId.SpeechServiceResponse_JsonResult)
    raw: dict[str, Any] = json.loads(raw_json) if raw_json else {}

    return {
        "transcript": result.text,
        "accuracy": pa.accuracy_score,
        "fluency": pa.fluency_score,
        "completeness": pa.completeness_score,
        "pron_score": pa.pronunciation_score,
        "raw": raw,
    }
