"""録音ターンのアップロードと再生 (Phase 1)。

ブラウザで録音した WebM/Opus を multipart で受け取り、サーバのファイルシステムに保存する。
Phase 2 でこの保存音声を ffmpeg → Azure 発音評価へ渡す。DB 永続化は Phase 4。
"""

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/api", tags=["turns"])

# 25 MB。短い復唱クリップを想定した上限。
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# content-type → 拡張子。未知なら .webm にフォールバック。
_EXT_BY_TYPE = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
}

_TURN_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _upload_dir() -> Path:
    """保存先ディレクトリ。相対パスは backend/ 起点に解決し、無ければ作る。"""
    configured = Path(settings.upload_dir)
    if not configured.is_absolute():
        # このファイルは backend/app/turns.py なので parent.parent = backend/
        configured = Path(__file__).resolve().parent.parent / configured
    configured.mkdir(parents=True, exist_ok=True)
    return configured


def _pick_extension(content_type: str | None, filename: str | None) -> str:
    if content_type and content_type in _EXT_BY_TYPE:
        return _EXT_BY_TYPE[content_type]
    if filename and "." in filename:
        return Path(filename).suffix.lower()
    return ".webm"


@router.post("/turn")
async def create_turn(
    audio: UploadFile = File(...),
    scenario: str | None = Form(default=None),
    turn_no: int | None = Form(default=None),
) -> dict[str, object]:
    """録音音声を受け取り保存する。再生用 URL 付きのメタデータを返す。"""
    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=415,
            detail=f"音声ファイルではありません (content_type={content_type!r})",
        )

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=400, detail="空のファイルです")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="ファイルが大きすぎます (上限 25MB)")

    turn_id = uuid4().hex
    ext = _pick_extension(content_type, audio.filename)
    path = _upload_dir() / f"{turn_id}{ext}"
    path.write_bytes(data)

    return {
        "turn_id": turn_id,
        "filename": path.name,
        "content_type": content_type,
        "size_bytes": len(data),
        "scenario": scenario,
        "turn_no": turn_no,
        "audio_url": f"/api/turn/{turn_id}/audio",
    }


@router.get("/turn/{turn_id}/audio")
def get_turn_audio(turn_id: str) -> FileResponse:
    """保存済み音声を返す (録音の往復確認・教師ダッシュボードでの再生用)。"""
    if not _TURN_ID_RE.match(turn_id):
        raise HTTPException(status_code=404, detail="不正な turn_id です")

    matches = sorted(_upload_dir().glob(f"{turn_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="音声が見つかりません")

    path = matches[0]
    media_type = {
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)
