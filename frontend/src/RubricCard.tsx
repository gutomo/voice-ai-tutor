import type { CombinedScore, RubricScore } from './api'
import './RubricCard.css'

// 会話採点 (ルーブリック) と合成スコアの表示。説明は Bahasa、対象語は日本語。
function band(score: number): 'good' | 'mid' | 'low' {
  if (score >= 85) return 'good'
  if (score >= 70) return 'mid'
  return 'low'
}

function RubricBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="rubric-row">
      <span className="rubric-label">{label}</span>
      <span className="rubric-dots" aria-label={`${value}/5`}>
        {[0, 1, 2, 3, 4].map((i) => (
          <span key={i} className={`dot ${i < value ? 'on' : ''}`} />
        ))}
      </span>
    </div>
  )
}

export function RubricCard({
  rubric,
  combined,
  onPlayModel,
}: {
  rubric: RubricScore
  combined: CombinedScore
  onPlayModel?: (text: string) => void
}) {
  return (
    <section className="rubric-card">
      <div className="overall">
        <span className={`overall-value ${band(combined.combined_score)}`}>
          {Math.round(combined.combined_score)}
        </span>
        <span className="overall-label">Skor gabungan</span>
      </div>

      <div className="passline">
        <div className="passline-bar">
          <div
            className={`passline-fill ${band(combined.kaigo_passline_pct)}`}
            style={{ width: `${combined.kaigo_passline_pct}%` }}
          />
        </div>
        <span className="passline-text">
          Ambang lulus (Ujian Bahasa Kaigo): <b>{Math.round(combined.kaigo_passline_pct)}%</b>
          {combined.jlpt_estimate && <> · est. {combined.jlpt_estimate}</>}
        </span>
      </div>

      <div className={`task ${rubric.task_completed ? 'ok' : 'no'}`}>
        {rubric.task_completed ? '✅ Tugas tercapai' : '⚠️ Tugas belum tercapai'}
      </div>

      <div className="rubric-bars">
        <RubricBar label="Tata bahasa" value={rubric.grammar} />
        <RubricBar label="Kosakata" value={rubric.vocabulary} />
        <RubricBar label="Kesopanan" value={rubric.politeness} />
      </div>

      {rubric.feedback_id && <p className="feedback">{rubric.feedback_id}</p>}
      {rubric.feedback_ja && (
        <p className="feedback jp-note">
          <span className="jp">{rubric.feedback_ja}</span>
        </p>
      )}

      {rubric.model_answer_ja && (
        <div className="model-answer">
          <span className="label">Contoh jawaban</span>
          <p className="jp">{rubric.model_answer_ja}</p>
          {onPlayModel && (
            <button
              type="button"
              className="btn secondary"
              onClick={() => onPlayModel(rubric.model_answer_ja)}
            >
              🔊 Dengarkan
            </button>
          )}
        </div>
      )}
    </section>
  )
}
