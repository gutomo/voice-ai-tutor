// コホート (クラス) ビュー: 合格見込み分布 + 要フォロー自動フラグ + 学習者一覧。Phase 5。

import type { Learner } from '../api'
import { BarChart, type BarDatum } from './charts'
import {
  cohortStats,
  distribution,
  passlinePct,
  passlineStatus,
  type Band,
} from './metrics'

function bandForBucket(from: number): Band {
  if (from >= 60) return 'good'
  if (from >= 40) return 'mid'
  return 'low'
}

// 到達度の降順 (未採点は末尾)。
function byPasslineDesc(a: Learner, b: Learner): number {
  const pa = passlinePct(a)
  const pb = passlinePct(b)
  if (pa == null && pb == null) return a.name.localeCompare(b.name)
  if (pa == null) return 1
  if (pb == null) return -1
  return pb - pa
}

export function CohortView({
  learners,
  onSelect,
}: {
  learners: Learner[]
  onSelect: (id: number) => void
}) {
  const stats = cohortStats(learners)
  const buckets: BarDatum[] = distribution(learners).map((b) => ({
    label: b.label,
    count: b.count,
    band: bandForBucket(b.from),
  }))
  const sorted = [...learners].sort(byPasslineDesc)
  const followups = sorted.filter((le) => {
    const pct = passlinePct(le)
    return pct != null && passlineStatus(pct).needsFollowup
  })

  return (
    <div className="cohort">
      <div className="stat-row">
        <Stat label="Kandidat" value={String(stats.size)} />
        <Stat label="Rata-rata ambang" value={`${stats.avgPasslinePct}%`} />
        <Stat label="Di jalur lulus" value={String(stats.onTrack)} band="good" />
        <Stat label="Perlu tindak lanjut" value={String(stats.followup)} band="low" />
      </div>

      {followups.length > 0 && (
        <div className="flag-banner">
          <strong>⚠ {followups.length} kandidat perlu tindak lanjut</strong>
          <span className="flag-sub">
            Ambang lulus &lt; 50% (Ujian Bahasa Jepang Kaigo):{' '}
            {followups.map((le) => le.name).join(', ')}
          </span>
        </div>
      )}

      <section className="panel">
        <h3 className="panel-title">Distribusi prospek kelulusan</h3>
        <BarChart data={buckets} unit="% ambang lulus" />
      </section>

      <section className="panel">
        <h3 className="panel-title">Daftar kandidat</h3>
        <table className="cohort-table">
          <thead>
            <tr>
              <th>Nama</th>
              <th>Level</th>
              <th>Ambang lulus</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((le) => (
              <LearnerRow key={le.id} learner={le} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
        {learners.length === 0 && (
          <p className="empty">Belum ada kandidat. Jalankan seed atau rekam sesi.</p>
        )}
      </section>
    </div>
  )
}

function LearnerRow({ learner, onSelect }: { learner: Learner; onSelect: (id: number) => void }) {
  const pct = passlinePct(learner)
  const status = pct != null ? passlineStatus(pct) : null
  return (
    <tr className="cohort-row" onClick={() => onSelect(learner.id)} tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect(learner.id)
        }
      }}
    >
      <td className="td-name">{learner.name}</td>
      <td className="td-level">
        {learner.profile?.cefr_estimate ?? '—'}
        {learner.profile?.jlpt_estimate && (
          <span className="jlpt"> · {learner.profile.jlpt_estimate}</span>
        )}
      </td>
      <td className="td-passline">
        {pct != null ? (
          <span className="passline-cell">
            <span className="passline-bar mini">
              <span className={`passline-fill ${status?.band}`} style={{ width: `${pct}%` }} />
            </span>
            <span className="passline-num">{pct}%</span>
          </span>
        ) : (
          <span className="muted">belum dinilai</span>
        )}
      </td>
      <td className="td-status">
        {status ? <span className={`status-chip ${status.band}`}>{status.label}</span> : '—'}
      </td>
    </tr>
  )
}

function Stat({ label, value, band }: { label: string; value: string; band?: Band }) {
  return (
    <div className="stat">
      <span className={`stat-value ${band ?? ''}`}>{value}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}
