"""テスト共通の準備。

サンプル WAV は .gitignore (*.wav) によりコミットしないので、無ければここで生成する。
0.2 秒の無音 16kHz/mono/16bit。CI でも確実に存在させるため import 時に作る。

`db` フィクスチャ: in-memory SQLite に切り替えてテーブルを作る (Postgres 不要)。
DB を使うテストはこれを引数に取る。
"""

import struct
import wave
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import db as db_module

_DATA = Path(__file__).parent / "data"
_SAMPLE = _DATA / "sample_16k_mono.wav"


def _ensure_sample_wav() -> None:
    if _SAMPLE.exists():
        return
    _DATA.mkdir(parents=True, exist_ok=True)
    with wave.open(str(_SAMPLE), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<" + "h" * 3200, *([0] * 3200)))


_ensure_sample_wav()


@pytest.fixture
def db() -> Iterator[None]:
    """テストごとに新しい in-memory SQLite を用意し、終わったら破棄する。"""
    db_module.configure_engine("sqlite://")
    db_module.init_db()
    try:
        yield
    finally:
        db_module.dispose_engine()
