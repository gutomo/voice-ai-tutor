// 依存を増やさない軽量チャート (CSS バー + SVG スパークライン)。Phase 5。

import type { Band } from './metrics'

export type BarDatum = { label: string; count: number; band?: Band }

// 縦棒の分布図 (合格見込み分布)。値は件数。
export function BarChart({ data, unit = '' }: { data: BarDatum[]; unit?: string }) {
  const max = Math.max(1, ...data.map((d) => d.count))
  return (
    <div className="barchart">
      {data.map((d) => (
        <div className="bar-col" key={d.label}>
          <span className="bar-count">{d.count > 0 ? d.count : ''}</span>
          <div className="bar-track">
            <div
              className={`bar-fill ${d.band ?? ''}`}
              style={{ height: `${(d.count / max) * 100}%` }}
            />
          </div>
          <span className="bar-label">{d.label}</span>
        </div>
      ))}
      {unit && <span className="bar-unit">{unit}</span>}
    </div>
  )
}

// 0-100 の値列を折れ線で描く (合格ライン到達度の推移)。threshold で要フォロー線を引く。
export function Sparkline({
  values,
  threshold,
  width = 280,
  height = 90,
}: {
  values: number[]
  threshold?: number
  width?: number
  height?: number
}) {
  const pad = 6
  const w = width - pad * 2
  const h = height - pad * 2
  const n = values.length
  const x = (i: number) => (n <= 1 ? pad + w / 2 : pad + (i / (n - 1)) * w)
  const y = (v: number) => pad + h - (Math.max(0, Math.min(100, v)) / 100) * h

  const line = values.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  const area = `${pad},${pad + h} ${line} ${pad + w},${pad + h}`
  const last = values.length ? values[values.length - 1] : 0

  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Tren ambang lulus">
      {threshold != null && (
        <line
          className="spark-threshold"
          x1={pad}
          x2={pad + w}
          y1={y(threshold)}
          y2={y(threshold)}
        />
      )}
      {values.length > 0 && <polygon className="spark-area" points={area} />}
      {values.length > 0 && <polyline className="spark-line" points={line} />}
      {values.map((v, i) => (
        <circle key={i} className="spark-dot" cx={x(i)} cy={y(v)} r={i === n - 1 ? 4 : 2.5} />
      ))}
      {values.length > 0 && (
        <text className="spark-last" x={x(n - 1)} y={y(last) - 8} textAnchor="end">
          {Math.round(last)}%
        </text>
      )}
    </svg>
  )
}
