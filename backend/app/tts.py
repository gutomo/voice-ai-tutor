"""Azure Neural TTS (ja-JP) の薄いラッパ。利用者役の発話を音声バイトに合成する。

設計上の要点 (speech.py と同じ思想):
- `import azure...` は関数内で遅延 import (スタブ時 / CI ではネイティブ依存が不要)。
- 鍵 / リージョンは引数で受け取り、ログに出さない。
- 出力は WAV(16kHz/mono/16bit) の生バイト。エンドポイントがそのまま返す。
"""

from typing import Any

# デモの既定ボイス (ja-JP の女性 Neural)。リクエストで上書き可能。
DEFAULT_VOICE = "ja-JP-NanamiNeural"


class TtsError(RuntimeError):
    """音声合成が失敗した。"""


def synthesize_ja(text: str, key: str, region: str, *, voice: str | None = None) -> bytes:
    """日本語テキストを WAV バイトに合成する。"""
    if not text.strip():
        raise TtsError("合成するテキストが空です")

    import azure.cognitiveservices.speech as speechsdk

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice or DEFAULT_VOICE
    # パイプライン全体に合わせて 16kHz/mono/16bit PCM の RIFF WAV にする。
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm
    )

    # audio_config=None: 既定スピーカーへ出さず、メモリに音声バイトを得る。
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result: Any = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return bytes(result.audio_data)
    if result.reason == speechsdk.ResultReason.Canceled:
        details = result.cancellation_details
        raise TtsError(f"音声合成がキャンセルされました: {details.reason}")
    raise TtsError(f"音声合成に失敗しました: {result.reason}")
