/**
 * Fire-and-forget event log to the backend (/api/client-log → backend/logs/app.log), so what
 * happens in the browser (microphone, transcripts, playback) is visible next to server logs.
 */
type Level = 'debug' | 'info' | 'warning' | 'error'

let sessionId: string | null = null

export function setLogSession(id: string | null) {
  sessionId = id
}

export function logEvent(level: Level, event: string, data?: Record<string, unknown>) {
  const payload = JSON.stringify({ level, event, session_id: sessionId, data })
  if (level === 'error' || level === 'warning') console.warn(event, data)
  try {
    void fetch('/api/client-log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: payload,
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* logging must never break the app */
  }
}

export const errorText = (e: unknown) =>
  e instanceof Error ? `${e.name}: ${e.message}` : typeof e === 'string' ? e : JSON.stringify(e)
