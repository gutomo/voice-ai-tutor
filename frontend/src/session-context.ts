// 学習者アプリのセッション状態 (Phase 7)。
// Recorder / RolePlay / SessionBar が同じ session_id を共有するための Context。
// 会話の各ターンをこのセッションに保存し、終了ボタンでまとめメールを送る。

import { createContext, useContext } from 'react'
import type { SessionEndResult } from './api'

export type SessionState = {
  // 有効なセッションの id。まだ開始していなければ null。
  sessionId: number | null
  // このセッションで保存できたターン数 (終了ボタンの活性判定に使う)。
  turnCount: number
  // 直近の合格ライン到達度 (%)。録音のたびに動く (money shot)。未保存なら null。
  passlinePct: number | null
  // セッションを (必要ならデモ学習者ごと) 作成し session_id を返す。作成済みなら再利用。
  ensureSession: () => Promise<number>
  // 採点済みターンが保存できたら呼ぶ。到達度を更新しカウントを進める。
  notePersistedTurn: (passlinePct: number | null) => void
  // セッションを終了しまとめメールを送る。
  endCurrentSession: (resend?: boolean) => Promise<SessionEndResult>
  // 次のデモに向けてセッションを破棄する (学習者は再利用し、次の録音で新セッションを作る)。
  resetSession: () => void
}

export const SessionContext = createContext<SessionState | null>(null)

export function useSession(): SessionState {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession は SessionProvider の内側で使ってください')
  return ctx
}
