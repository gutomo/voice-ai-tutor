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

// --- Phase 3: 会話ループ + ルーブリック採点 ---

export type ScenarioMeta = {
  scenario: string
  title_ja: string
  title_id: string
  turns: ScenarioTurn[]
  persona: { name: string } | null
  roleplay: { opening_ja: string; opening_gloss_id: string } | null
}

export type ConversationMessage = { role: 'assistant' | 'user'; text: string }
export type PatientLine = { utterance_ja: string; gloss_id: string }

export type RubricScore = {
  task_completed: boolean
  task_reason: string
  grammar: number
  vocabulary: number
  politeness: number
  cefr_estimate: string
  feedback_ja: string
  feedback_id: string
  model_answer_ja: string
}

export type CombinedScore = {
  pron_score: number | null
  rubric_score: number | null
  task_completed: boolean | null
  combined_score: number
  cefr_estimate: string | null
  jlpt_estimate: string | null
  kaigo_passline_pct: number
}

export type TurnEvaluation = {
  turn_id: string
  mode: 'scripted' | 'roleplay'
  pronunciation: PronunciationResult | null
  rubric: RubricScore | null
  combined: CombinedScore
  // session_id を渡して永続化したときだけ、更新後の学習者プロファイルが返る (money shot)。
  profile: LearnerProfile | null
}

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

// シナリオの全メタ (利用者役・ロールプレイの口火を含む)。
export async function getScenario(scenario: string): Promise<ScenarioMeta> {
  const res = await fetch(`/api/scenario/${scenario}`)
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as ScenarioMeta
}

// 利用者役 (例: 田中さん) の次の発話を生成する。
export async function conversationReply(
  scenario: string,
  history: ConversationMessage[] = [],
): Promise<PatientLine> {
  const res = await fetch('/api/conversation/reply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario, history }),
  })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as PatientLine
}

export type EvaluateBody = {
  mode?: 'scripted' | 'roleplay'
  scenario?: string
  turnNo?: number
  transcript?: string
  patientText?: string
  // 指定するとサーバが採点結果を DB に保存し、更新後プロファイルを返す (Phase 4/7)。
  sessionId?: number
}

// 1ターンを統合評価する (scripted=発音、roleplay=STT＋ルーブリック＋合成)。
export async function evaluateTurn(turnId: string, body: EvaluateBody = {}): Promise<TurnEvaluation> {
  const res = await fetch(`/api/turn/${turnId}/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      mode: body.mode ?? 'scripted',
      scenario: body.scenario,
      turn_no: body.turnNo,
      transcript: body.transcript,
      patient_text: body.patientText,
      session_id: body.sessionId,
    }),
  })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as TurnEvaluation
}

// --- Phase 5: 教師ダッシュボード (学習者ビュー + コホートビュー) ---

export type LearnerProfile = {
  learner_id: number
  cefr_estimate: string | null
  jlpt_estimate: string | null
  kaigo_passline_pct: number
  updated_at: string | null
}

export type Learner = {
  id: number
  name: string
  email: string | null
  native_lang: string
  target_sector: string
  created_at: string
  profile: LearnerProfile | null
}

// 保存済みターン (TurnOut)。weak_phonemes は ja-JP では「弱い単語」のリスト。
export type Turn = {
  id: string
  session_id: number
  turn_no: number | null
  transcript: string | null
  pron_accuracy: number | null
  pron_fluency: number | null
  pron_completeness: number | null
  weak_phonemes: WordScore[] | null
  rubric: RubricScore | null
  combined_score: number | null
  created_at: string
}

// コホート一覧 (各学習者のプロファイル付き)。
export async function listLearners(): Promise<Learner[]> {
  const res = await fetch('/api/learners')
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as Learner[]
}

export async function getLearner(learnerId: number): Promise<Learner> {
  const res = await fetch(`/api/learners/${learnerId}`)
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as Learner
}

// 学習者の全ターンを新しい順に返す (会話ログ・推移・ヒートマップの素)。
export async function getLearnerTurns(learnerId: number): Promise<Turn[]> {
  const res = await fetch(`/api/learners/${learnerId}/turns`)
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as Turn[]
}

// 保存済みターンの音声 URL (会話ログの再生用)。
export function turnAudioUrl(turnId: string): string {
  return `/api/turn/${turnId}/audio`
}

// --- Phase 7: セッション ライフサイクル (学習者アプリから終了 → まとめメール) ---

export type Session = {
  id: number
  learner_id: number
  scenario: string
  started_at: string
  ended_at: string | null
  summary_sent_at: string | null
}

export type EmailResult = {
  kind: 'learner' | 'teacher'
  recipient: string
  status: 'sent' | 'skipped' | 'error'
  message_id: string | null
  detail: string | null
}

export type SessionEndResult = {
  session: Session
  emails_sent: boolean
  emails: EmailResult[]
}

// デモ用の学習者を作る (メール未指定なら SES 送信元にフォールバック＝サンドボックスでも届く)。
export async function createLearner(body: { name: string; email?: string }): Promise<Learner> {
  const res = await fetch('/api/learners', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as Learner
}

// 学習者に紐づくレッスンセッションを開始する (以降のターンをここに保存する)。
export async function createSession(
  learnerId: number,
  scenario = 'kaigo_morning',
): Promise<Session> {
  const res = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ learner_id: learnerId, scenario }),
  })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as Session
}

// セッションを終了し、結果メール (学習者まとめ + 教師レポート) を送る。送信ログを返す。
export async function endSession(sessionId: number, resend = false): Promise<SessionEndResult> {
  const res = await fetch(`/api/sessions/${sessionId}/end?resend=${resend}`, { method: 'POST' })
  if (!res.ok) throw await parseError(res)
  return (await res.json()) as SessionEndResult
}

// 日本語テキストを Azure TTS で合成し、再生用の object URL を返す。
// 呼び出し側は使い終わったら URL.revokeObjectURL すること。
export async function synthesizeTtsUrl(text: string, voice?: string): Promise<string> {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, voice }),
  })
  if (!res.ok) throw await parseError(res)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
