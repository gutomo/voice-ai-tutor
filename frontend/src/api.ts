// バックエンド API への薄いラッパ。dev では /api が Vite から :8000 へプロキシされる。

export type TurnResponse = {
  turn_id: string
  filename: string
  content_type: string
  size_bytes: number
  scenario: string | null
  turn_no: number | null
  audio_url: string
}

export type WordScore = { word: string; accuracy: number | null; error_type: string }
export type WeakPhoneme = { word: string; phoneme: string; accuracy: number | null }

export type PronunciationResult = {
  turn_id: string
  reference_text: string
  transcript: string
  accuracy: number
  fluency: number
  completeness: number
  pron_score: number
  words: WordScore[]
  weak_words: WordScore[]
  weak_phonemes: WeakPhoneme[]
}

export type ScenarioTurn = { turn_no: number; reference_text: string; gloss_id: string }

export type TurnMeta = { scenario?: string; turnNo?: number }

// HTTP ステータスを保持するエラー (フロントが 503/422 を出し分けられるように)。
export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `HTTP ${res.status}`
  try {
    const body = (await res.json()) as { detail?: string }
    if (body.detail) detail = body.detail
  } catch {
    // ignore parse error
  }
  return new ApiError(res.status, detail)
}

function extForMime(mime: string): string {
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mp4')) return 'm4a'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

// 録音した Blob を multipart で /api/turn に送る。
export async function uploadTurn(blob: Blob, meta: TurnMeta = {}): Promise<TurnResponse> {
  const form = new FormData()
  const type = blob.type || 'audio/webm'
  form.append('audio', blob, `turn.${extForMime(type)}`)
  if (meta.scenario) form.append('scenario', meta.scenario)
  if (meta.turnNo != null) form.append('turn_no', String(meta.turnNo))

  const res = await fetch('/api/turn', { method: 'POST', body: form })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as TurnResponse
}

// 保存済みターンを発音採点する。
export async function scoreTurn(turnId: string, meta: TurnMeta = {}): Promise<PronunciationResult> {
  const res = await fetch(`/api/turn/${turnId}/score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario: meta.scenario, turn_no: meta.turnNo }),
  })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as PronunciationResult
}

// シナリオのモデル文一覧を取得する (プロンプト表示用)。
export async function getScenarioTurns(scenario: string): Promise<ScenarioTurn[]> {
  const res = await fetch(`/api/scenario/${scenario}/turns`)
  if (!res.ok) throw await parseError(res)
  const body = (await res.json()) as { turns: ScenarioTurn[] }
  return body.turns
}
