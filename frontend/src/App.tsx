import { useEffect, useState } from 'react'
import { Recorder } from './Recorder'
import { RolePlay } from './RolePlay'
import './App.css'

// 説明UIは Bahasa Indonesia、学習対象は日本語。
type Health = { status: string; service?: string }
type ConnState = 'loading' | 'ok' | 'error'
type Mode = 'drill' | 'roleplay'

function App() {
  const [conn, setConn] = useState<ConnState>('loading')
  const [mode, setMode] = useState<Mode>('drill')

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

      <div className="mode-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'drill'}
          className={`mode-tab ${mode === 'drill' ? 'active' : ''}`}
          onClick={() => setMode('drill')}
        >
          Latihan pengucapan
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'roleplay'}
          className={`mode-tab ${mode === 'roleplay' ? 'active' : ''}`}
          onClick={() => setMode('roleplay')}
        >
          Percakapan
        </button>
      </div>

      {mode === 'drill' ? <Recorder /> : <RolePlay />}

      <p className="hint">
        {mode === 'drill'
          ? 'Ucapkan model kalimat → skor pengucapan instan.'
          : 'Tanggapi penghuni → skor percakapan + ambang lulus.'}
      </p>
    </main>
  )
}

export default App
