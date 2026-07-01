// レッスンの終了 → まとめメール送信を UI から起こす操作バー (Phase 7)。
// 録音のたびに「保存済みターン数」と「合格ライン到達度」が動き、終了ボタンで
// 学習者まとめ + 教師レポートの 2 通を送る (以前はスクリプトで叩いていた工程)。

import { useState } from 'react'
import { ApiError, type EmailResult, type SessionEndResult } from './api'
import { useSession } from './session-context'
import './SessionBar.css'

type EndFlow =
  | { kind: 'idle' }
  | { kind: 'sending' }
  | { kind: 'done'; result: SessionEndResult }
  | { kind: 'error'; message: string }

const KIND_LABEL: Record<EmailResult['kind'], string> = {
  learner: 'Siswa',
  teacher: 'Guru',
}

const STATUS_LABEL: Record<EmailResult['status'], string> = {
  sent: '✅ Terkirim',
  skipped: '➖ Dilewati',
  error: '⚠️ Gagal',
}

export function SessionBar() {
  const { sessionId, turnCount, passlinePct, endCurrentSession, resetSession } = useSession()
  const [flow, setFlow] = useState<EndFlow>({ kind: 'idle' })

  const onEnd = async () => {
    setFlow({ kind: 'sending' })
    try {
      const result = await endCurrentSession()
      setFlow({ kind: 'done', result })
    } catch (err: unknown) {
      setFlow({ kind: 'error', message: errorMessage(err) })
    }
  }

  const onNewSession = () => {
    resetSession()
    setFlow({ kind: 'idle' })
  }

  // まとめを送り終えたら、送信ログと「新しいセッション」だけを見せる。
  if (flow.kind === 'done') {
    return (
      <section className="session-bar done">
        <p className="session-title">
          {flow.result.emails_sent ? 'Ringkasan terkirim 📧' : 'Sesi diakhiri'}
        </p>
        <ul className="email-log">
          {flow.result.emails.map((e) => (
            <li key={e.kind} className={`email-row ${e.status}`}>
              <span className="email-kind">{KIND_LABEL[e.kind]}</span>
              <span className="email-status">{STATUS_LABEL[e.status]}</span>
              <span className="email-to">{e.recipient}</span>
              {e.detail && <span className="email-detail">{e.detail}</span>}
            </li>
          ))}
        </ul>
        <button type="button" className="btn primary" onClick={onNewSession}>
          Mulai sesi baru
        </button>
      </section>
    )
  }

  const started = sessionId != null || turnCount > 0
  const busy = flow.kind === 'sending'

  return (
    <section className="session-bar">
      <div className="session-status">
        <span className={`session-dot ${started ? 'on' : ''}`} />
        <span className="session-label">
          {started ? `Sesi aktif · ${turnCount} jawaban` : 'Sesi belum dimulai'}
        </span>
        {passlinePct != null && (
          <span className="session-passline">Ambang lulus: {Math.round(passlinePct)}%</span>
        )}
      </div>

      <button
        type="button"
        className="btn primary"
        onClick={() => void onEnd()}
        disabled={turnCount === 0 || busy}
      >
        {busy ? 'Mengirim ringkasan…' : 'Akhiri sesi & kirim ringkasan'}
      </button>

      {turnCount === 0 && (
        <p className="session-hint">Rekam minimal satu jawaban untuk mengakhiri sesi.</p>
      )}
      {flow.kind === 'error' && <p className="rec-error">{flow.message}</p>}
    </section>
  )
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) return 'Sesi tidak ditemukan.'
    return err.message
  }
  return err instanceof Error ? err.message : 'Terjadi kesalahan.'
}
