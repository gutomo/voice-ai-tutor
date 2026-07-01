// 教師ダッシュボードの集計ロジック (Phase 5)。
// バンド分け・分布・推移・発音ヒートマップの素を一箇所に集約し、ビューは描画に専念する。
// 合格ライン到達度の計算は backend の combine.py (avg(combined) - 15) と揃える。

import type { Learner, Turn } from '../api'

// 要フォローの閾値: 合格ライン到達度がこれ未満なら自動フラグ (backend seed と同じ)。
export const FOLLOWUP_THRESHOLD = 50
// 合格圏入口とみなす到達度。
export const ON_TRACK_THRESHOLD = 60
// backend combine.PASSLINE_OFFSET と一致させる (推移の最終点が現在の到達度に一致する)。
const PASSLINE_OFFSET = 15

export type Band = 'good' | 'mid' | 'low'

export type PasslineStatus = {
  band: Band
  // Bahasa Indonesia のステータスラベル (教師向け UI)。
  label: string
  needsFollowup: boolean
}

export function passlineStatus(pct: number): PasslineStatus {
  if (pct >= ON_TRACK_THRESHOLD) return { band: 'good', label: 'Di jalur lulus', needsFollowup: false }
  if (pct >= FOLLOWUP_THRESHOLD) return { band: 'mid', label: 'Hampir lulus', needsFollowup: false }
  return { band: 'low', label: 'Perlu tindak lanjut', needsFollowup: true }
}

// 0-100 スコアを色バンドへ (ScoreCard と同じ閾値: good>=85, mid>=70)。
export function scoreBand(score: number): Band {
  if (score >= 85) return 'good'
  if (score >= 70) return 'mid'
  return 'low'
}

export type CohortStats = {
  size: number
  scored: number // プロファイルを持つ (=採点済みの) 人数
  avgPasslinePct: number
  onTrack: number
  followup: number
}

export function passlinePct(le: Learner): number | null {
  return le.profile ? le.profile.kaigo_passline_pct : null
}

export function cohortStats(learners: Learner[]): CohortStats {
  const scored = learners.map(passlinePct).filter((v): v is number => v != null)
  const sum = scored.reduce((a, b) => a + b, 0)
  return {
    size: learners.length,
    scored: scored.length,
    avgPasslinePct: scored.length ? Math.round((sum / scored.length) * 10) / 10 : 0,
    onTrack: scored.filter((v) => v >= ON_TRACK_THRESHOLD).length,
    followup: scored.filter((v) => v < FOLLOWUP_THRESHOLD).length,
  }
}

export type Bucket = { label: string; from: number; to: number; count: number }

// 合格見込み分布 (到達度の 20 点刻みヒストグラム)。
export function distribution(learners: Learner[]): Bucket[] {
  const edges = [0, 20, 40, 60, 80, 100]
  const buckets: Bucket[] = []
  for (let i = 0; i < edges.length - 1; i++) {
    buckets.push({ label: `${edges[i]}–${edges[i + 1]}`, from: edges[i], to: edges[i + 1], count: 0 })
  }
  for (const le of learners) {
    const pct = passlinePct(le)
    if (pct == null) continue
    // 上端 100 は最後のバケツに含める。
    const idx = Math.min(Math.floor(pct / 20), buckets.length - 1)
    buckets[idx].count++
  }
  return buckets
}

export type TrendPoint = { turnNo: number; passlinePct: number }

// 合格ライン到達度の推移: 古い順に combined_score を累積平均し、オフセットを引く。
// 最終点はプロファイルの現在の到達度と一致する。
export function passlineTrend(turns: Turn[]): TrendPoint[] {
  const ordered = scored(turns)
  const points: TrendPoint[] = []
  let sum = 0
  ordered.forEach((t, i) => {
    sum += t.combined_score as number
    const avg = sum / (i + 1)
    points.push({ turnNo: i + 1, passlinePct: clamp(Math.round((avg - PASSLINE_OFFSET) * 10) / 10) })
  })
  return points
}

export type WeakWordAgg = { word: string; count: number; minAccuracy: number; avgAccuracy: number }

// 全ターンの要練習語を集約して発音ヒートマップにする (苦手な順)。
export function aggregateWeakWords(turns: Turn[]): WeakWordAgg[] {
  const map = new Map<string, { count: number; sum: number; min: number }>()
  for (const t of turns) {
    for (const w of t.weak_phonemes ?? []) {
      const acc = w.accuracy ?? 0
      const cur = map.get(w.word)
      if (cur) {
        cur.count++
        cur.sum += acc
        cur.min = Math.min(cur.min, acc)
      } else {
        map.set(w.word, { count: 1, sum: acc, min: acc })
      }
    }
  }
  return [...map.entries()]
    .map(([word, v]) => ({
      word,
      count: v.count,
      minAccuracy: Math.round(v.min),
      avgAccuracy: Math.round(v.sum / v.count),
    }))
    .sort((a, b) => a.minAccuracy - b.minAccuracy)
}

// 会話ログ用に古い順へ整列 (推移と同じ並び)。
export function chronological(turns: Turn[]): Turn[] {
  return [...turns].sort(byCreatedThenTurn)
}

function scored(turns: Turn[]): Turn[] {
  return [...turns].filter((t) => t.combined_score != null).sort(byCreatedThenTurn)
}

function byCreatedThenTurn(a: Turn, b: Turn): number {
  if (a.created_at !== b.created_at) return a.created_at < b.created_at ? -1 : 1
  return (a.turn_no ?? 0) - (b.turn_no ?? 0)
}

function clamp(v: number, lo = 0, hi = 100): number {
  return Math.max(lo, Math.min(hi, v))
}
