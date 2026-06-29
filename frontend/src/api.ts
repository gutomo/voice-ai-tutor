// バックエンド API への薄いラッパ。dev では /api が Vite から :8000 へプロキシされる。

export type TurnResponse = {
  turn_id: string
  filename: string
  content_type: string
  size_bytes: number
  scenario: string | null
  turn_no: number | null
  audio_url: string
}

export type TurnMeta = {
  scenario?: string
  turnNo?: number
}

function extForMime(mime: string): string {
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mp4')) return 'm4a'
  if (mime.includes('wav')) return 'wav'
  return 'webm'
}

// 録音した Blob を multipart で /api/turn に送る。
export async function uploadTurn(blob: Blob, meta: TurnMeta = {}): Promise<TurnResponse> {
  const form = new FormData()
  const type = blob.type || 'audio/webm'
  form.append('audio', blob, `turn.${extForMime(type)}`)
  if (meta.scenario) form.append('scenario', meta.scenario)
  if (meta.turnNo != null) form.append('turn_no', String(meta.turnNo))

  const res = await fetch('/api/turn', { method: 'POST', body: form })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = (await res.json()) as { detail?: string }
      if (body.detail) detail = body.detail
    } catch {
      // ignore parse error
    }
    throw new Error(detail)
  }
  return (await res.json()) as TurnResponse
}
