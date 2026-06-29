import { useCallback, useEffect, useRef, useState } from 'react'

// MediaRecorder で録音する最小フック。
// 対象は Android Chrome なので WebM/Opus を優先しつつ、無ければブラウザ既定にフォールバックする。
export type RecorderStatus = 'idle' | 'recording' | 'recorded' | 'error' | 'unsupported'

export type Recorder = {
  status: RecorderStatus
  error: string | null
  blob: Blob | null
  blobUrl: string | null
  mimeType: string | null
  elapsedMs: number
  start: () => Promise<void>
  stop: () => void
  reset: () => void
}

const MIME_PREFERENCES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
]

function pickMimeType(): string {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return ''
  for (const m of MIME_PREFERENCES) {
    if (MediaRecorder.isTypeSupported(m)) return m
  }
  return ''
}

function isSupported(): boolean {
  return (
    typeof MediaRecorder !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia
  )
}

export function useRecorder(): Recorder {
  const [status, setStatus] = useState<RecorderStatus>(() =>
    isSupported() ? 'idle' : 'unsupported',
  )
  const [error, setError] = useState<string | null>(null)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [mimeType, setMimeType] = useState<string | null>(null)
  const [elapsedMs, setElapsedMs] = useState(0)

  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const startedAtRef = useRef<number>(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const blobUrlRef = useRef<string | null>(null)

  const stopTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  const revokeUrl = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
  }, [])

  const start = useCallback(async () => {
    if (!isSupported()) {
      setStatus('unsupported')
      return
    }
    setError(null)
    revokeUrl()
    setBlob(null)
    setBlobUrl(null)
    setElapsedMs(0)
    chunksRef.current = []

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const chosen = pickMimeType()
      const recorder = chosen ? new MediaRecorder(stream, { mimeType: chosen }) : new MediaRecorder(stream)
      recorderRef.current = recorder
      setMimeType(recorder.mimeType || chosen || null)

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        const type = recorder.mimeType || chosen || 'audio/webm'
        const recorded = new Blob(chunksRef.current, { type })
        const url = URL.createObjectURL(recorded)
        blobUrlRef.current = url
        setBlob(recorded)
        setBlobUrl(url)
        setStatus('recorded')
        stopTimer()
        releaseStream()
      }

      recorder.start()
      startedAtRef.current = Date.now()
      setStatus('recording')
      timerRef.current = setInterval(() => {
        setElapsedMs(Date.now() - startedAtRef.current)
      }, 200)
    } catch (err: unknown) {
      releaseStream()
      stopTimer()
      setStatus('error')
      setError(
        err instanceof DOMException && err.name === 'NotAllowedError'
          ? 'Akses mikrofon ditolak. Izinkan mikrofon di browser.'
          : err instanceof Error
            ? err.message
            : 'Gagal memulai rekaman.',
      )
    }
  }, [releaseStream, revokeUrl, stopTimer])

  const stop = useCallback(() => {
    const recorder = recorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
  }, [])

  const reset = useCallback(() => {
    revokeUrl()
    setBlob(null)
    setBlobUrl(null)
    setElapsedMs(0)
    setError(null)
    chunksRef.current = []
    setStatus(isSupported() ? 'idle' : 'unsupported')
  }, [revokeUrl])

  // アンマウント時に後始末
  useEffect(() => {
    return () => {
      stopTimer()
      releaseStream()
      revokeUrl()
    }
  }, [releaseStream, revokeUrl, stopTimer])

  return { status, error, blob, blobUrl, mimeType, elapsedMs, start, stop, reset }
}
