import { useEffect, useState } from 'react'
import {
  ApiError,
  evaluateTurn,
  getScenario,
  synthesizeTtsUrl,
  uploadTurn,
  type TurnEvaluation,
} from './api'
import { RubricCard } from './RubricCard'
import { ScoreCard } from './ScoreCard'
import { useRecorder } from './useRecorder'
import './Recorder.css'

// 介護「朝の声かけ」のロールプレイ1ターン (DESIGN §2 Step 4)。
// 利用者役 (田中さん) の口火に、学習者が音声で応答 → STT＋ルーブリック採点＋合成。
const SCENARIO = 'kaigo_morning'
const FALLBACK_OPENING = 'ああ、おはよう…なんだか今日は少し寒いねえ'

function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000)
  const mm = String(Math.floor(total / 60)).padStart(2, '0')
  const ss = String(total % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

type Flow =
  | { kind: 'idle' }
  | { kind: 'uploading' }
  | { kind: 'scoring' }
  | { kind: 'done'; result: TurnEvaluation }
  | { kind: 'error'; message: string }

export function RolePlay() {
  const rec = useRecorder()
  const [flow, setFlow] = useState<Flow>({ kind: 'idle' })
  const [opening, setOpening] = useState<string>(FALLBACK_OPENING)
  const [openingGloss, setOpeningGloss] = useState<string>('')
  const [ttsBusy, setTtsBusy] = useState(false)

  useEffect(() => {
    getScenario(SCENARIO)
      .then((meta) => {
        if (meta.roleplay) {
          setOpening(meta.roleplay.opening_ja)
          setOpeningGloss(meta.roleplay.opening_gloss_id)
        }
      })
      .catch(() => {
        /* フォールバックのまま */
      })
  }, [])

  // 日本語テキストを TTS で合成して再生する (利用者役の口火・模範応答)。
  const playJa = async (text: string) => {
    setTtsBusy(true)
    try {
      const url = await synthesizeTtsUrl(text)
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      await audio.play()
    } catch {
      /* TTS 未設定でも会話自体は進められるので黙って無視 */
    } finally {
      setTtsBusy(false)
    }
  }

  const onToggle = () => {
    if (rec.status === 'recording') rec.stop()
    else void rec.start()
  }

  const onRetry = () => {
    setFlow({ kind: 'idle' })
    rec.reset()
  }

  const onSend = async () => {
    if (!rec.blob) return
    setFlow({ kind: 'uploading' })
    try {
      const turn = await uploadTurn(rec.blob, { scenario: SCENARIO })
      setFlow({ kind: 'scoring' })
      const result = await evaluateTurn(turn.turn_id, {
        mode: 'roleplay',
        scenario: SCENARIO,
        patientText: opening,
      })
      setFlow({ kind: 'done', result })
    } catch (err: unknown) {
      setFlow({ kind: 'error', message: errorMessage(err) })
    }
  }

  if (rec.status === 'unsupported') {
    return (
      <section className="recorder">
        <p className="rec-error">
          Browser ini tidak mendukung perekaman. Gunakan Chrome di Android.
        </p>
      </section>
    )
  }

  const isRecording = rec.status === 'recording'
  const hasRecording = rec.status === 'recorded' && !!rec.blobUrl
  const busy = flow.kind === 'uploading' || flow.kind === 'scoring'

  return (
    <section className="recorder">
      <div className="patient-line">
        <span className="label">田中さん (penghuni)</span>
        <p className="jp">「{opening}」</p>
        {openingGloss && <p className="gloss">{openingGloss}</p>}
        <button
          type="button"
          className="btn secondary"
          onClick={() => void playJa(opening)}
          disabled={ttsBusy}
        >
          {ttsBusy ? '…' : '🔊 Dengarkan'}
        </button>
      </div>

      <p className="rec-prompt">Jawab dengan sopan dan sesuai situasi.</p>

      <button
        type="button"
        className={`rec-button ${isRecording ? 'recording' : ''}`}
        onClick={onToggle}
        aria-label={isRecording ? 'Berhenti' : 'Mulai rekam'}
      >
        <span className="rec-icon" />
      </button>

      <div className="rec-status">
        {isRecording && (
          <span className="rec-live">
            <span className="dot" /> merekam… {formatElapsed(rec.elapsedMs)}
          </span>
        )}
        {rec.status === 'idle' && <span>Tekan untuk menjawab</span>}
        {hasRecording && flow.kind !== 'done' && (
          <span>Rekaman selesai · {formatElapsed(rec.elapsedMs)}</span>
        )}
        {rec.status === 'error' && <span className="rec-error">{rec.error}</span>}
      </div>

      {hasRecording && flow.kind !== 'done' && rec.blobUrl && (
        <div className="rec-playback">
          <span className="label">Dengarkan jawaban Anda</span>
          <audio controls src={rec.blobUrl} />
          <div className="rec-actions">
            <button type="button" className="btn secondary" onClick={onRetry} disabled={busy}>
              Ulangi
            </button>
            <button
              type="button"
              className="btn primary"
              onClick={() => void onSend()}
              disabled={busy}
            >
              {flow.kind === 'uploading'
                ? 'Mengirim…'
                : flow.kind === 'scoring'
                  ? 'Menilai…'
                  : 'Kirim & nilai'}
            </button>
          </div>
        </div>
      )}

      {flow.kind === 'error' && <p className="rec-error">{flow.message}</p>}

      {flow.kind === 'done' && (
        <>
          <RubricCard
            rubric={flow.result.rubric!}
            combined={flow.result.combined}
            onPlayModel={(t) => void playJa(t)}
          />
          {flow.result.pronunciation && <ScoreCard result={flow.result.pronunciation} />}
          <button type="button" className="btn secondary" onClick={onRetry}>
            Coba lagi
          </button>
        </>
      )}
    </section>
  )
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 503) return 'Percakapan belum dikonfigurasi (Bedrock / Azure).'
    if (err.status === 422) return 'Suara kurang jelas. Coba rekam lagi.'
    return err.message
  }
  return err instanceof Error ? err.message : 'Terjadi kesalahan.'
}
