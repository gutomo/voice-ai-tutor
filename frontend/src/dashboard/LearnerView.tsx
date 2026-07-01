// 学習者ビュー: 推定レベル + 合格ライン到達度の推移 + 発音ヒートマップ + 会話ログ(再生)。Phase 5。

import { useEffect, useState } from 'react'
import { getLearner, getLearnerTurns, turnAudioUrl, type Learner, type Turn } from '../api'
import { Sparkline } from './charts'
import {
  aggregateWeakWords,
  chronological,
  FOLLOWUP_THRESHOLD,
  passlineStatus,
  passlineTrend,
  scoreBand,
} from './metrics'

type Loaded = { learner: Learner; turns: Turn[] }
type State =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: Loaded }

export function LearnerView({ learnerId, onBack }: { learnerId: number; onBack: () => void }) {
  const [state, setState] = useState<State>({ kind: 'loading' })

  useEffect(() => {
    let alive = true
    setState({ kind: 'loading' })
    Promise.all([getLearner(learnerId), getLearnerTurns(learnerId)])
      .then(([learner, turns]) => {
        if (alive) setState({ kind: 'ready', data: { learner, turns } })
      })
      .catch((err: unknown) => {
        if (alive) setState({ kind: 'error', message: err instanceof Error ? err.message : 'Gagal memuat' })
      })
    return () => {
      alive = false
    }
  }, [learnerId])

  return (
    <div className="learner-view">
      <button type="button" className="back-link" onClick={onBack}>
        ← Kembali ke kelas
      </button>
      {state.kind === 'loading' && <p className="empty">Memuat…</p>}
      {state.kind === 'error' && <p className="rec-error">{state.message}</p>}
      {state.kind === 'ready' && <LearnerDetail data={state.data} />}
    </div>
  )
}

function LearnerDetail({ data }: { data: Loaded }) {
  const { learner, turns } = data
  const pct = learner.profile?.kaigo_passline_pct ?? 0
  const status = passlineStatus(pct)
  const trend = passlineTrend(turns)
  const weak = aggregateWeakWords(turns)
  const log = chronological(turns)

  return (
    <>
      <header className="lv-header">
        <div>
          <h2 className="lv-name">{learner.name}</h2>
          <span className="lv-level">
            {learner.profile?.cefr_estimate ?? '—'}
            {learner.profile?.jlpt_estimate && ` · ${learner.profile.jlpt_estimate}`}
          </span>
        </div>
        <div className="lv-passline">
          <span className={`lv-passline-num ${status.band}`}>{pct}%</span>
          <span className={`status-chip ${status.band}`}>{status.label}</span>
        </div>
      </header>

      <section className="panel">
        <h3 className="panel-title">Tren ambang lulus (Ujian Bahasa Jepang Kaigo)</h3>
        {trend.length > 0 ? (
          <Sparkline values={trend.map((p) => p.passlinePct)} threshold={FOLLOWUP_THRESHOLD} />
        ) : (
          <p className="empty">Belum ada giliran yang dinilai.</p>
        )}
      </section>

      <section className="panel">
        <h3 className="panel-title">Peta panas pengucapan (kata yang perlu latihan)</h3>
        {weak.length > 0 ? (
          <div className="heatmap">
            {weak.map((w) => (
              <span key={w.word} className={`heat-cell ${scoreBand(w.avgAccuracy)}`} title={`min ${w.minAccuracy}`}>
                <span className="heat-word">{w.word}</span>
                <span className="heat-acc">{w.avgAccuracy}</span>
                {w.count > 1 && <span className="heat-count">×{w.count}</span>}
              </span>
            ))}
          </div>
        ) : (
          <p className="all-good">Tidak ada kata bermasalah 👍</p>
        )}
      </section>

      <section className="panel">
        <h3 className="panel-title">Log percakapan</h3>
        {log.length > 0 ? (
          <ol className="turn-log">
            {log.map((t) => (
              <TurnEntry key={t.id} turn={t} />
            ))}
          </ol>
        ) : (
          <p className="empty">Belum ada giliran.</p>
        )}
      </section>
    </>
  )
}

function TurnEntry({ turn }: { turn: Turn }) {
  const isRoleplay = turn.rubric != null
  return (
    <li className="turn-entry">
      <div className="turn-head">
        <span className="turn-no">
          {isRoleplay ? 'Percakapan' : 'Latihan'}
          {turn.turn_no != null && ` · #${turn.turn_no}`}
        </span>
        {turn.combined_score != null && (
          <span className={`turn-score ${scoreBand(turn.combined_score)}`}>
            {Math.round(turn.combined_score)}
          </span>
        )}
      </div>

      {turn.transcript && (
        <p className="turn-transcript">
          <span className="jp">{turn.transcript}</span>
        </p>
      )}

      {turn.pron_accuracy != null && (
        <div className="turn-pron">
          <PronChip label="Akurasi" value={turn.pron_accuracy} />
          {turn.pron_fluency != null && <PronChip label="Kelancaran" value={turn.pron_fluency} />}
          {turn.pron_completeness != null && (
            <PronChip label="Kelengkapan" value={turn.pron_completeness} />
          )}
        </div>
      )}

      {turn.rubric && (
        <div className="turn-rubric">
          <span className={`task ${turn.rubric.task_completed ? 'ok' : 'no'}`}>
            {turn.rubric.task_completed ? '✅ Tugas tercapai' : '◻ Tugas belum tuntas'}
          </span>
          {turn.rubric.feedback_id && <p className="turn-feedback">{turn.rubric.feedback_id}</p>}
          {turn.rubric.model_answer_ja && (
            <p className="turn-model">
              Contoh: <span className="jp">{turn.rubric.model_answer_ja}</span>
            </p>
          )}
        </div>
      )}

      <audio className="turn-audio" controls preload="none" src={turnAudioUrl(turn.id)} />
    </li>
  )
}

function PronChip({ label, value }: { label: string; value: number }) {
  return (
    <span className={`pron-chip ${scoreBand(value)}`}>
      <span className="pron-chip-val">{Math.round(value)}</span>
      <span className="pron-chip-label">{label}</span>
    </span>
  )
}
