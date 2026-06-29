import { useState } from 'react'
import { uploadTurn, type TurnResponse } from './api'
import { useRecorder } from './useRecorder'
import './Recorder.css'

// Phase 1 のシナリオは固定（介護「朝の声かけ」）。Phase 3 で動的にする。
const SCENARIO = 'kaigo_morning'

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000)
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

type UploadState =
  | { kind: 'idle' }
  | { kind: 'uploading' }
  | { kind: 'done'; res: TurnResponse }
  | { kind: 'error'; message: string }

export function Recorder() {
  const rec = useRecorder()
  const [upload, setUpload] = useState<UploadState>({ kind: 'idle' })

  const onToggle = () => {
    if (rec.status === 'recording') rec.stop()
    else void rec.start()
  }

  const onRetry = () => {
    setUpload({ kind: 'idle' })
    rec.reset()
  }

  const onSend = async () => {
    if (!rec.blob) return
    setUpload({ kind: 'uploading' })
    try {
      const res = await uploadTurn(rec.blob, { scenario: SCENARIO, turnNo: 1 })
      setUpload({ kind: 'done', res })
    } catch (err: unknown) {
      setUpload({ kind: 'error', message: err instanceof Error ? err.message : 'gagal' })
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

  return (
    <section className="recorder">
      <p className="rec-prompt">
        Tekan tombol, lalu ucapkan: <span className="jp">「おはようございます。体温を測りますね」</span>
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
        {hasRecording && <span>Rekaman selesai · {formatElapsed(rec.elapsedMs)}</span>}
        {rec.status === 'error' && <span className="rec-error">{rec.error}</span>}
      </div>

      {hasRecording && rec.blobUrl && (
        <div className="rec-playback">
          <span className="label">Dengarkan rekaman Anda</span>
          <audio controls src={rec.blobUrl} />

          <div className="rec-actions">
            <button type="button" className="btn secondary" onClick={onRetry}>
              Ulangi
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => void onSend()}
              disabled={upload.kind === 'uploading' || upload.kind === 'done'}
            >
              {upload.kind === 'uploading' ? 'Mengirim…' : 'Kirim'}
            </button>
          </div>
        </div>
      )}

      {upload.kind === 'error' && <p className="rec-error">Gagal mengirim: {upload.message}</p>}

      {upload.kind === 'done' && (
        <div className="rec-uploaded">
          <span className="ok">Berhasil terkirim ✓</span>
          <span className="label">Tersimpan di server ({upload.res.size_bytes} byte)</span>
          <audio controls src={upload.res.audio_url} />
        </div>
      )}
    </section>
  )
}
