import { useEffect, useState } from 'react'
import { Recorder } from './Recorder'
import { RolePlay } from './RolePlay'
import { Dashboard } from './dashboard/Dashboard'
import './App.css'

// 説明UIは Bahasa Indonesia、学習対象は日本語。
type Health = { status: string; service?: string }
type ConnState = 'loading' | 'ok' | 'error'
type Mode = 'drill' | 'roleplay'
type Role = 'learner' | 'teacher'

function App() {
  const [conn, setConn] = useState<ConnState>('loading')
  const [mode, setMode] = useState<Mode>('drill')
  const [role, setRole] = useState<Role>('learner')

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
    <>
      {/* 学習者アプリ (候補者の端末) と教師ダッシュボードの切替。デモで画面を切り替える。 */}
      <nav className="role-switch" role="tablist" aria-label="Tampilan">
        <button
          type="button"
          role="tab"
          aria-selected={role === 'learner'}
          className={`role-btn ${role === 'learner' ? 'active' : ''}`}
          onClick={() => setRole('learner')}
        >
          📱 Siswa
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={role === 'teacher'}
          className={`role-btn ${role === 'teacher' ? 'active' : ''}`}
          onClick={() => setRole('teacher')}
        >
          🎓 Guru
        </button>
      </nav>

      {role === 'teacher' ? (
        <Dashboard />
      ) : (
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
      )}
    </>
  )
}

export default App
