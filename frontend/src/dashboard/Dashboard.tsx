// 教師ダッシュボードのコンテナ: コホート一覧を取得し、コホートビューと学習者ビューを切り替える。Phase 5。

import { useEffect, useState } from 'react'
import { listLearners, type Learner } from '../api'
import { CohortView } from './CohortView'
import { LearnerView } from './LearnerView'
import './Dashboard.css'

type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; learners: Learner[] }

export function Dashboard() {
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [selected, setSelected] = useState<number | null>(null)

  const load = () => {
    setState({ kind: 'loading' })
    listLearners()
      .then((learners) => setState({ kind: 'ready', learners }))
      .catch((err: unknown) =>
        setState({ kind: 'error', message: err instanceof Error ? err.message : 'Gagal memuat' }),
      )
  }

  useEffect(load, [])

  return (
    <div className="dash">
      <header className="dash-header">
        <div>
          <h1 className="dash-title">Dasbor Guru</h1>
          <p className="dash-sub">介護 日本語 · ambang lulus &amp; tindak lanjut</p>
        </div>
        {state.kind === 'ready' && selected == null && (
          <button type="button" className="btn secondary dash-refresh" onClick={load}>
            ↻ Segarkan
          </button>
        )}
      </header>

      {state.kind === 'loading' && <p className="empty">Memuat kelas…</p>}
      {state.kind === 'error' && (
        <div className="dash-error">
          <p className="rec-error">{state.message}</p>
          <button type="button" className="btn secondary" onClick={load}>
            Coba lagi
          </button>
        </div>
      )}
      {state.kind === 'ready' &&
        (selected == null ? (
          <CohortView learners={state.learners} onSelect={setSelected} />
        ) : (
          <LearnerView learnerId={selected} onBack={() => setSelected(null)} />
        ))}
    </div>
  )
}
