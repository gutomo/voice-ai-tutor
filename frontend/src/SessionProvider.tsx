// セッション状態のプロバイダ (Phase 7)。
// デモでは固定の「Live Demo」学習者を 1 名だけ再利用し、録音のたびに
// その学習者の合格ライン到達度が動く。教師ダッシュボードにも同じ 1 名として現れる。

import { useCallback, useRef, useState, type ReactNode } from 'react'
import { createLearner, createSession, endSession, listLearners } from './api'
import { SessionContext, type SessionState } from './session-context'

// 教師ダッシュボードに現れるデモ学習者の表示名。存在すれば再利用し、無ければ作る。
const DEMO_LEARNER_NAME = 'Live Demo (Siswa)'
const SCENARIO = 'kaigo_morning'

export function SessionProvider({ children }: { children: ReactNode }) {
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [turnCount, setTurnCount] = useState(0)
  const [passlinePct, setPasslinePct] = useState<number | null>(null)
  // Recorder と RolePlay が同時に ensureSession を呼んでも二重作成しないためのガード。
  const pending = useRef<Promise<number> | null>(null)

  const ensureSession = useCallback(async (): Promise<number> => {
    if (sessionId != null) return sessionId
    if (pending.current) return pending.current
    const task = (async () => {
      const learners = await listLearners()
      const existing = learners.find((l) => l.name === DEMO_LEARNER_NAME)
      const learnerId = existing ? existing.id : (await createLearner({ name: DEMO_LEARNER_NAME })).id
      const sess = await createSession(learnerId, SCENARIO)
      setSessionId(sess.id)
      return sess.id
    })()
    pending.current = task
    try {
      return await task
    } finally {
      pending.current = null
    }
  }, [sessionId])

  const notePersistedTurn = useCallback((pct: number | null) => {
    setTurnCount((n) => n + 1)
    if (pct != null) setPasslinePct(pct)
  }, [])

  const endCurrentSession = useCallback(
    (resend = false) => {
      if (sessionId == null) throw new Error('Belum ada sesi aktif.')
      return endSession(sessionId, resend)
    },
    [sessionId],
  )

  const resetSession = useCallback(() => {
    pending.current = null
    setSessionId(null)
    setTurnCount(0)
    setPasslinePct(null)
  }, [])

  const value: SessionState = {
    sessionId,
    turnCount,
    passlinePct,
    ensureSession,
    notePersistedTurn,
    endCurrentSession,
    resetSession,
  }
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}
