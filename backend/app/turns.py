"""録音ターンのアップロードと再生 (Phase 1)。

ブラウザで録音した WebM/Opus を multipart で受け取り、サーバのファイルシステムに保存する。
Phase 2 でこの保存音声を ffmpeg → Azure 発音評価へ渡す。DB 永続化は Phase 4。
"""

import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app import bedrock, combine, persistence, scenarios, scoring, tts
from app.audio import AudioConversionError
from app.bedrock import BedrockError
from app.config import settings
from app.persistence import UnknownSessionError
from app.schemas import (
    ConversationReplyRequest,
    EvaluateRequest,
    LearnerProfileOut,
    PatientLine,
    PronunciationResult,
    RubricScore,
    ScoreRequest,
    TtsRequest,
    TurnEvaluation,
)
from app.speech import NoSpeechError, SpeechError
from app.tts import TtsError

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


def _find_upload(turn_id: str) -> Path | None:
    """turn_id に対応する保存済み音声 (元のアップロード) を探す。"""
    matches = sorted(_upload_dir().glob(f"{turn_id}.*"))
    return matches[0] if matches else None


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

    path = _find_upload(turn_id)
    if path is None:
        raise HTTPException(status_code=404, detail="音声が見つかりません")

    media_type = {
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.post("/turn/{turn_id}/score")
async def score_turn(turn_id: str, body: ScoreRequest | None = None) -> PronunciationResult:
    """保存済みターンを Azure ja-JP scripted 発音採点にかける。"""
    if not _TURN_ID_RE.match(turn_id):
        raise HTTPException(status_code=404, detail="不正な turn_id です")
    src = _find_upload(turn_id)
    if src is None:
        raise HTTPException(status_code=404, detail="音声が見つかりません")
    if not settings.azure_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "発音採点は未設定です "
                "(AZURE_SPEECH_KEY / AZURE_SPEECH_REGION を設定してください)"
            ),
        )

    req = body or ScoreRequest()
    reference_text = req.reference_text or scenarios.get_reference_text(req.scenario, req.turn_no)
    if not reference_text:
        raise HTTPException(
            status_code=422,
            detail="モデル文を解決できません (scenario+turn_no か reference_text を指定)",
        )

    try:
        return await run_in_threadpool(
            scoring.score_turn_sync,
            src,
            turn_id,
            reference_text,
            settings.azure_speech_key,
            settings.azure_speech_region,
        )
    except AudioConversionError as e:
        raise HTTPException(status_code=422, detail=f"音声を変換できませんでした: {e}") from e
    except NoSpeechError as e:
        raise HTTPException(status_code=422, detail="もう一度録音してください") from e
    except SpeechError as e:
        raise HTTPException(status_code=502, detail="発音採点に失敗しました") from e


@router.get("/scenario/{scenario}/turns")
def get_scenario_turns(scenario: str) -> dict[str, object]:
    """シナリオのモデル文一覧 (フロントがプロンプト表示に使う静的データ)。"""
    turns = scenarios.list_turns(scenario)
    if not turns:
        raise HTTPException(status_code=404, detail="シナリオが見つかりません")
    return {
        "scenario": scenario,
        "turns": [
            {
                "turn_no": t.turn_no,
                "reference_text": t.reference_text,
                "gloss_id": t.gloss_id,
            }
            for t in turns
        ],
    }


@router.get("/scenario/{scenario}")
def get_scenario(scenario: str) -> dict[str, object]:
    """シナリオの全メタ (タイトル・モデル文・利用者役・ロールプレイの口火)。"""
    sc = scenarios.get_scenario(scenario)
    if sc is None:
        raise HTTPException(status_code=404, detail="シナリオが見つかりません")
    return {
        "scenario": sc.key,
        "title_ja": sc.title_ja,
        "title_id": sc.title_id,
        "turns": [
            {"turn_no": t.turn_no, "reference_text": t.reference_text, "gloss_id": t.gloss_id}
            for t in sc.model_turns
        ],
        "persona": ({"name": sc.persona.name} if sc.persona else None),
        "roleplay": (
            {
                "opening_ja": sc.roleplay.opening_ja,
                "opening_gloss_id": sc.roleplay.opening_gloss_id,
            }
            if sc.roleplay
            else None
        ),
    }


def _require_bedrock() -> None:
    if not settings.bedrock_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "会話・採点は未設定です "
                "(AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / BEDROCK_MODEL_ID を設定してください)"
            ),
        )


def _require_azure() -> None:
    if not settings.azure_ready():
        raise HTTPException(
            status_code=503,
            detail=(
                "音声処理は未設定です "
                "(AZURE_SPEECH_KEY / AZURE_SPEECH_REGION を設定してください)"
            ),
        )


@router.post("/conversation/reply")
async def conversation_reply(body: ConversationReplyRequest) -> PatientLine:
    """利用者役 (例: 田中さん) の次の発話を Bedrock Claude で生成する。"""
    sc = scenarios.get_scenario(body.scenario)
    if sc is None or sc.persona is None:
        raise HTTPException(status_code=404, detail="利用者役を持つシナリオが見つかりません")
    _require_bedrock()

    history = [{"role": m.role, "text": m.text} for m in body.history]
    try:
        data = await run_in_threadpool(
            bedrock.generate_patient_line,
            sc,
            history,
            region=settings.aws_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
            model_id=settings.bedrock_model_id,
        )
    except BedrockError as e:
        raise HTTPException(status_code=502, detail="会話生成に失敗しました") from e
    return PatientLine(
        utterance_ja=str(data.get("utterance_ja", "")),
        gloss_id=str(data.get("gloss_id", "")),
    )


@router.post("/turn/{turn_id}/evaluate")
async def evaluate_turn(turn_id: str, body: EvaluateRequest | None = None) -> TurnEvaluation:
    """1ターンを統合評価する。scripted=発音採点、roleplay=STT＋ルーブリック採点＋合成。"""
    if not _TURN_ID_RE.match(turn_id):
        raise HTTPException(status_code=404, detail="不正な turn_id です")
    src = _find_upload(turn_id)
    if src is None:
        raise HTTPException(status_code=404, detail="音声が見つかりません")

    req = body or EvaluateRequest()
    if req.mode == "scripted":
        evaluation = await _evaluate_scripted(turn_id, src, req)
    else:
        evaluation = await _evaluate_roleplay(turn_id, src, req)

    if req.session_id is not None:
        evaluation.profile = await _persist_turn(turn_id, src, req, evaluation)
    return evaluation


async def _persist_turn(
    turn_id: str, src: Path, req: EvaluateRequest, evaluation: TurnEvaluation
) -> LearnerProfileOut:
    """採点結果を DB に保存し、更新後の学習者プロファイルを返す (Phase 4)。"""
    pron = evaluation.pronunciation
    transcript = pron.transcript if pron else req.transcript
    try:
        return await run_in_threadpool(
            persistence.record_turn,
            req.session_id,
            turn_id,
            turn_no=req.turn_no,
            audio_path=str(src),
            transcript=transcript,
            pron=pron,
            rubric=evaluation.rubric,
            combined=evaluation.combined,
        )
    except UnknownSessionError as e:
        raise HTTPException(status_code=404, detail="セッションが見つかりません") from e


async def _evaluate_scripted(turn_id: str, src: Path, req: EvaluateRequest) -> TurnEvaluation:
    _require_azure()
    reference_text = req.reference_text or scenarios.get_reference_text(req.scenario, req.turn_no)
    if not reference_text:
        raise HTTPException(
            status_code=422,
            detail="モデル文を解決できません (scenario+turn_no か reference_text を指定)",
        )
    try:
        pron = await run_in_threadpool(
            scoring.score_turn_sync,
            src,
            turn_id,
            reference_text,
            settings.azure_speech_key,
            settings.azure_speech_region,
        )
    except AudioConversionError as e:
        raise HTTPException(status_code=422, detail=f"音声を変換できませんでした: {e}") from e
    except NoSpeechError as e:
        raise HTTPException(status_code=422, detail="もう一度録音してください") from e
    except SpeechError as e:
        raise HTTPException(status_code=502, detail="発音採点に失敗しました") from e

    combined = combine.combine_scores(pron.pron_score, None)
    return TurnEvaluation(turn_id=turn_id, mode="scripted", pronunciation=pron, combined=combined)


async def _evaluate_roleplay(turn_id: str, src: Path, req: EvaluateRequest) -> TurnEvaluation:
    sc = scenarios.get_scenario(req.scenario)
    if sc is None:
        raise HTTPException(status_code=404, detail="シナリオが見つかりません")
    _require_bedrock()

    pron: PronunciationResult | None = None
    if req.transcript:
        # フロントが転写済み (例: 直前の /score の結果) なら STT を省略する。
        transcript = req.transcript
    else:
        _require_azure()
        try:
            pron = await run_in_threadpool(
                scoring.score_roleplay_sync,
                src,
                turn_id,
                settings.azure_speech_key,
                settings.azure_speech_region,
            )
        except AudioConversionError as e:
            raise HTTPException(status_code=422, detail=f"音声を変換できませんでした: {e}") from e
        except NoSpeechError as e:
            raise HTTPException(status_code=422, detail="もう一度録音してください") from e
        except SpeechError as e:
            raise HTTPException(status_code=502, detail="発音採点に失敗しました") from e
        transcript = pron.transcript

    patient_text = req.patient_text or (sc.roleplay.opening_ja if sc.roleplay else "")
    try:
        rubric_data = await run_in_threadpool(
            bedrock.score_rubric,
            sc,
            transcript,
            patient_text,
            region=settings.aws_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
            model_id=settings.bedrock_model_id,
        )
    except BedrockError as e:
        raise HTTPException(status_code=502, detail="ルーブリック採点に失敗しました") from e

    rubric = RubricScore(**rubric_data)
    combined = combine.combine_scores(pron.pron_score if pron else None, rubric)
    return TurnEvaluation(
        turn_id=turn_id, mode="roleplay", pronunciation=pron, rubric=rubric, combined=combined
    )


@router.post("/tts")
async def synthesize(body: TtsRequest) -> Response:
    """日本語テキストを Azure Neural TTS で WAV に合成して返す (利用者役の読み上げ)。"""
    _require_azure()
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="テキストが空です")
    try:
        audio_bytes = await run_in_threadpool(
            tts.synthesize_ja,
            body.text,
            settings.azure_speech_key,
            settings.azure_speech_region,
            voice=body.voice,
        )
    except TtsError as e:
        raise HTTPException(status_code=502, detail="音声合成に失敗しました") from e
    return Response(content=audio_bytes, media_type="audio/wav")
