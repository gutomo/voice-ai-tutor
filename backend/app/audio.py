"""ブラウザ録音 (WebM/Opus 等) を Azure 用の WAV(16k/mono/16bit PCM) へ変換する。

CLAUDE.md の必須ルール: Azure へ渡す前に必ず WAV(16kHz, mono, 16bit) に変換する。
入力コンテナは ffmpeg に自動判別させる (ブラウザの content-type は信用しない)。
"""

import shutil
import subprocess
from pathlib import Path

# ffmpeg は起動時に一度だけ解決する。無ければ呼び出し時に明示エラーにする。
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

# WAV ヘッダのみ (データなし) は 44 バイト。これ以下は変換失敗とみなす。
_MIN_WAV_BYTES = 44


class AudioConversionError(RuntimeError):
    """ffmpeg 変換に失敗した (入力不正・ffmpeg 不在・出力が空 など)。"""


def to_wav_16k_mono(src: Path, dst: Path, *, timeout: float = 30.0) -> Path:
    """任意の ffmpeg 対応音声を WAV(16kHz/mono/16bit PCM) に変換する。

    src のコンテナ/コーデックは ffmpeg が判別するので、webm/opus・ogg/opus・mp4/aac
    などをそのまま渡してよい。固定するのは出力フォーマットだけ。
    """
    if shutil.which(FFMPEG) is None and not Path(FFMPEG).exists():
        raise AudioConversionError("ffmpeg が見つかりません (PATH を確認してください)")
    if not src.exists() or src.stat().st_size == 0:
        raise AudioConversionError(f"入力が空または存在しません: {src}")

    cmd = [
        FFMPEG,
        "-nostdin",  # 親プロセスの stdin を消費しない (uvicorn 配下で重要)
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",  # dst を上書き
        "-i",
        str(src),
        "-vn",  # 映像/カバーアートを捨てる
        "-ar",
        "16000",  # 16 kHz
        "-ac",
        "1",  # mono
        "-c:a",
        "pcm_s16le",  # 16bit signed little-endian PCM
        "-f",
        "wav",  # dst の拡張子に関係なく WAV を強制
        str(dst),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError as e:
        raise AudioConversionError("ffmpeg が見つかりません (PATH を確認してください)") from e
    except subprocess.TimeoutExpired as e:
        raise AudioConversionError("ffmpeg がタイムアウトしました") from e

    if proc.returncode != 0:
        raise AudioConversionError(
            f"ffmpeg が失敗しました (rc={proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    if not dst.exists() or dst.stat().st_size <= _MIN_WAV_BYTES:
        raise AudioConversionError("ffmpeg の出力が空です (音声が無い可能性)")
    return dst
