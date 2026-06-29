import { useEffect, useState } from 'react'
import {
  ApiError,
  getScenarioTurns,
  scoreTurn,
  uploadTurn,
  type PronunciationResult,
} from './api'
import { ScoreCard } from './ScoreCard'
import { useRecorder } from './useRecorder'
import './Recorder.css'

// Phase 2 のシナリオ/ターンは固定 (介護「朝の声かけ」の 1 ターン)。Phase 3 で多ターン化。
const SCENARIO = 'kaigo_morning'
const TURN_NO = 1
const FALLBACK_PROMPT = 'おはようございます。よく眠れましたか'

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
  const [flow, setFlow] = useState<Flow>({ kind: 'idle' })
  const [prompt, setPrompt] = useState<string>(FALLBACK_PROMPT)

  // モデル文をサーバから取得 (失敗時はフォールバック)。
  useEffect(() => {
    getScenarioTurns(SCENARIO)
      .then((turns) => {
        const t = turns.find((x) => x.turn_no === TURN_NO)
        if (t) setPrompt(t.reference_text)
      })
      .catch(() => {
        /* フォールバックのまま */
      })
  }, [])

  const onToggle = () => {
    if (rec.status === 'recording') rec.stop()
    else void rec.start()
  }

  const onRetry = () => {
    setFlow({ kind: 'idle' })
    rec.reset()
  }

  // 送信 → アップロード → そのまま自動採点。
  const onSend = async () => {
    if (!rec.blob) return
    setFlow({ kind: 'uploading' })
    try {
      const turn = await uploadTurn(rec.blob, { scenario: SCENARIO, turnNo: TURN_NO })
      setFlow({ kind: 'scoring' })
      const result = await scoreTurn(turn.turn_id, { scenario: SCENARIO, turnNo: TURN_NO })
      setFlow({ kind: 'done', result })
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
      <p className="rec-prompt">
        Tekan tombol, lalu ucapkan: <span className="jp">「{prompt}」</span>
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
          <button type="button" className="btn secondary" onClick={onRetry}>
            Rekam lagi
          </button>
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
