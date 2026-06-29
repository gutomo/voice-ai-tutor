"""ffmpeg 変換ラッパのテスト。実際の ffmpeg/Azure は呼ばない。"""

import subprocess
from pathlib import Path

import pytest

from app import audio
from app.audio import AudioConversionError, to_wav_16k_mono

SAMPLE_WAV = Path(__file__).parent / "data" / "sample_16k_mono.wav"


def test_missing_ffmpeg(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(audio.shutil, "which", lambda _: None)
    src = tmp_path / "in.webm"
    src.write_bytes(b"x")
    with pytest.raises(AudioConversionError, match="ffmpeg"):
        to_wav_16k_mono(src, tmp_path / "out.wav")


def test_empty_input(monkeypatch, tmp_path) -> None:
    # ffmpeg の有無に依存しないよう存在する体にしておく (空入力の判定だけを見る)
    monkeypatch.setattr(audio.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    src = tmp_path / "empty.webm"
    src.write_bytes(b"")
    with pytest.raises(AudioConversionError, match="空"):
        to_wav_16k_mono(src, tmp_path / "out.wav")


def test_ffmpeg_nonzero_rc(monkeypatch, tmp_path) -> None:
    src = tmp_path / "in.webm"
    src.write_bytes(b"not really audio")
    monkeypatch.setattr(audio.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def fake_run(*_a, **_k):
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    with pytest.raises(AudioConversionError, match="rc=1"):
        to_wav_16k_mono(src, tmp_path / "out.wav")


def test_success(monkeypatch, tmp_path) -> None:
    src = tmp_path / "in.webm"
    src.write_bytes(b"pretend webm")
    dst = tmp_path / "out.wav"
    monkeypatch.setattr(audio.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def fake_run(*_a, **_k):
        dst.write_bytes(SAMPLE_WAV.read_bytes())  # ffmpeg が WAV を書いた体
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(audio.subprocess, "run", fake_run)
    out = to_wav_16k_mono(src, dst)
    assert out == dst
    assert dst.stat().st_size > 44
