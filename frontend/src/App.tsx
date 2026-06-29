import { useEffect, useState } from 'react'
import { Recorder } from './Recorder'
import './App.css'

// 説明UIは Bahasa Indonesia、学習対象は日本語。
type Health = { status: string; service?: string }
type ConnState = 'loading' | 'ok' | 'error'

function App() {
  const [conn, setConn] = useState<ConnState>('loading')

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<Health>
      })
      .then(() => setConn('ok'))
      .catch(() => setConn('error'))
  }, [])

  return (
    <main className="app">
      <header className="app-header">
        <h1>Tutor Bahasa Jepang AI</h1>
        <p className="subtitle">Demo untuk LPK · 介護 日本語</p>
        <span className={`chip ${conn}`}>
          backend: {conn === 'ok' ? 'terhubung' : conn === 'loading' ? '…' : 'terputus'}
        </span>
      </header>

      <Recorder />

      <p className="hint">Phase 1 · rekam → kirim → putar ulang.</p>
    </main>
  )
}

export default App
