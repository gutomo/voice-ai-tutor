import { useEffect, useState } from 'react'
import {
  ApiError,
  evaluateTurn,
  getScenarioTurns,
  uploadTurn,
  type PronunciationResult,
  type ScenarioTurn,
} from './api'
import { ScoreCard } from './ScoreCard'
import { useRecorder } from './useRecorder'
import { useSession } from './session-context'
import './Recorder.css'

// 介護「朝の声かけ」のモデル文を順に復唱するドリル (DESIGN §2 Step 3)。
const SCENARIO = 'kaigo_morning'
const FALLBACK_TURNS: ScenarioTurn[] = [
  { turn_no: 1, reference_text: 'おはようございます。よく眠れましたか', gloss_id: '' },
]

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000)
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

type Flow =
  | { kind: 'idle' }
  | { kind: 'uploading' }
  | { kind: 'scoring' }
  | { kind: 'done'; result: PronunciationResult }
  | { kind: 'error'; message: string }

export function Recorder() {
  const rec = useRecorder()
  const { ensureSession, notePersistedTurn } = useSession()
  const [flow, setFlow] = useState<Flow>({ kind: 'idle' })
  const [turns, setTurns] = useState<ScenarioTurn[]>(FALLBACK_TURNS)
  const [index, setIndex] = useState(0)

  // モデル文をサーバから取得 (失敗時はフォールバック)。
  useEffect(() => {
    getScenarioTurns(SCENARIO)
      .then((t) => {
        if (t.length) setTurns(t)
      })
      .catch(() => {
        /* フォールバックのまま */
      })
  }, [])

  const current = turns[index] ?? turns[0]
  const isLast = index >= turns.length - 1

  const onToggle = () => {
    if (rec.status === 'recording') rec.stop()
    else void rec.start()
  }

  const onRetry = () => {
    setFlow({ kind: 'idle' })
    rec.reset()
  }

  const onNext = () => {
    setIndex((i) => Math.min(i + 1, turns.length - 1))
    setFlow({ kind: 'idle' })
    rec.reset()
  }

  // 送信 → アップロード → 発音採点 (セッションがあればターンも保存する)。
  const onSend = async () => {
    if (!rec.blob) return
    setFlow({ kind: 'uploading' })
    try {
      // 保存先セッションを確保 (取得できなければ採点だけ行い保存はスキップ)。
      const sessionId = await ensureSession().catch(() => undefined)
      const turn = await uploadTurn(rec.blob, { scenario: SCENARIO, turnNo: current.turn_no })
      setFlow({ kind: 'scoring' })
      const evaluation = await evaluateTurn(turn.turn_id, {
        mode: 'scripted',
        scenario: SCENARIO,
        turnNo: current.turn_no,
        sessionId,
      })
      const result = evaluation.pronunciation
      if (!result) throw new Error('Skor pengucapan tidak tersedia.')
      setFlow({ kind: 'done', result })
      if (sessionId != null) notePersistedTurn(evaluation.profile?.kaigo_passline_pct ?? null)
    } catch (err: unknown) {
      setFlow({ kind: 'error', message: errorMessage(err) })
    }
  }

  if (rec.status === 'unsupported') {
    return (
      <section className="recorder">
        <p className="rec-error">
          Browser ini tidak mendukung perekaman. Gunakan Chrome di Android.
        </p>
      </section>
    )
  }

  const isRecording = rec.status === 'recording'
  const hasRecording = rec.status === 'recorded' && !!rec.blobUrl
  const busy = flow.kind === 'uploading' || flow.kind === 'scoring'

  return (
    <section className="recorder">
      <span className="progress">
        Frase {index + 1}/{turns.length}
      </span>

      <p className="rec-prompt">
        Tekan tombol, lalu ucapkan: <span className="jp">「{current.reference_text}」</span>
        {current.gloss_id && <span className="gloss-inline">{current.gloss_id}</span>}
      </p>

      <button
        type="button"
        className={`rec-button ${isRecording ? 'recording' : ''}`}
        onClick={onToggle}
        aria-label={isRecording ? 'Berhenti' : 'Mulai rekam'}
      >
        <span className="rec-icon" />
      </button>

      <div className="rec-status">
        {isRecording && (
          <span className="rec-live">
            <span className="dot" /> merekam… {formatElapsed(rec.elapsedMs)}
          </span>
        )}
        {rec.status === 'idle' && <span>Tekan untuk mulai merekam</span>}
        {hasRecording && flow.kind !== 'done' && (
          <span>Rekaman selesai · {formatElapsed(rec.elapsedMs)}</span>
        )}
        {rec.status === 'error' && <span className="rec-error">{rec.error}</span>}
      </div>

      {hasRecording && flow.kind !== 'done' && rec.blobUrl && (
        <div className="rec-playback">
          <span className="label">Dengarkan rekaman Anda</span>
          <audio controls src={rec.blobUrl} />

          <div className="rec-actions">
            <button type="button" className="btn secondary" onClick={onRetry} disabled={busy}>
              Ulangi
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => void onSend()}
              disabled={busy}
            >
              {flow.kind === 'uploading'
                ? 'Mengirim…'
                : flow.kind === 'scoring'
                  ? 'Menilai…'
                  : 'Kirim & nilai'}
            </button>
          </div>
        </div>
      )}

      {flow.kind === 'error' && <p className="rec-error">{flow.message}</p>}

      {flow.kind === 'done' && (
        <>
          <ScoreCard result={flow.result} />
          <div className="rec-actions">
            <button type="button" className="btn secondary" onClick={onRetry}>
              Rekam lagi
            </button>
            {!isLast && (
              <button type="button" className="btn primary" onClick={onNext}>
                Frase berikutnya →
              </button>
            )}
          </div>
          {isLast && (
            <p className="hint">Selesai! Lanjut ke tab «Percakapan» untuk roleplay.</p>
          )}
        </>
      )}
    </section>
  )
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 503) return 'Penilaian belum dikonfigurasi (Azure Speech).'
    if (err.status === 422) return 'Suara kurang jelas. Coba rekam lagi.'
    return err.message
  }
  return err instanceof Error ? err.message : 'Terjadi kesalahan.'
}
