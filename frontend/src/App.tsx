import { useEffect, useState } from 'react'
import './App.css'

// Phase 0: バックエンドとの疎通を画面で確認するだけの最小ページ。
// 説明UIは Bahasa Indonesia、学習対象 (Phase 1 以降) は日本語。
type Health = { status: string; service?: string }

type ConnState =
  | { kind: 'loading' }
  | { kind: 'ok'; data: Health }
  | { kind: 'error'; message: string }

function App() {
  const [conn, setConn] = useState<ConnState>({ kind: 'loading' })

  useEffect(() => {
    fetch('/api/health')
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return (await res.json()) as Health
      })
      .then((data) => setConn({ kind: 'ok', data }))
      .catch((err: unknown) =>
        setConn({ kind: 'error', message: err instanceof Error ? err.message : 'gagal' }),
      )
  }, [])

  return (
    <main className="app">
      <h1>Tutor Bahasa Jepang AI</h1>
      <p className="subtitle">Demo untuk LPK · 介護 日本語</p>

      <section className="card">
        <span className="label">Status backend</span>
        {conn.kind === 'loading' && <span className="status loading">memuat…</span>}
        {conn.kind === 'ok' && (
          <span className="status ok">terhubung ✓ ({conn.data.service ?? conn.data.status})</span>
        )}
        {conn.kind === 'error' && (
          <span className="status error">gagal terhubung: {conn.message}</span>
        )}
      </section>

      <p className="hint">Phase 0 · scaffold. Halaman rekam suara menyusul di Phase 1.</p>
    </main>
  )
}

export default App
