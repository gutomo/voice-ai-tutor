import type { PronunciationResult } from './api'
import './ScoreCard.css'

// 発音スコアの画面表示。説明は Bahasa、対象語は日本語。
function band(score: number): 'good' | 'mid' | 'low' {
  if (score >= 85) return 'good'
  if (score >= 70) return 'mid'
  return 'low'
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className={`metric ${band(value)}`}>
      <span className="metric-value">{Math.round(value)}</span>
      <span className="metric-label">{label}</span>
    </div>
  )
}

export function ScoreCard({ result }: { result: PronunciationResult }) {
  return (
    <section className="scorecard">
      <div className="overall">
        <span className={`overall-value ${band(result.pron_score)}`}>
          {Math.round(result.pron_score)}
        </span>
        <span className="overall-label">Skor pengucapan</span>
      </div>

      <div className="metrics">
        <Metric label="Akurasi" value={result.accuracy} />
        <Metric label="Kelancaran" value={result.fluency} />
        <Metric label="Kelengkapan" value={result.completeness} />
      </div>

      {result.weak_words.length > 0 ? (
        <div className="weak">
          <span className="label">Perlu latihan</span>
          <ul className="weak-list">
            {result.weak_words.map((w, i) => (
              <li key={`${w.word}-${i}`}>
                <span className="jp">{w.word}</span>
                {w.accuracy != null && <span className="acc">{Math.round(w.accuracy)}</span>}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="all-good">Bagus! Semua kata terdengar jelas 👍</p>
      )}

      {result.transcript && (
        <p className="transcript">
          Terdengar: <span className="jp">{result.transcript}</span>
        </p>
      )}
    </section>
  )
}
