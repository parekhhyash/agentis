import { useCallback, useEffect, useState } from 'react'

import { authedFetch } from './backendApi'

// Gmail, Google Calendar and Google Sheets connect on their own, onto one
// Google account.
export type GooglePart = 'gmail' | 'calendar' | 'sheets'

export interface GoogleStatus {
  configured: boolean
  // Gmail is connected.
  connected: boolean
  // Google Calendar and Google Sheets are connected (same Google account).
  calendar?: boolean
  sheets?: boolean
  email: string | null
}

export function partConnected(status: GoogleStatus | null, part: GooglePart): boolean {
  if (!status) return false
  return part === 'gmail' ? status.connected : Boolean(status[part])
}

// The user's Google connection: Gmail (and Calendar for meetings) for Sales &
// Outreach, and Google Sheets for data files and exports. Tokens stay on the
// backend; this only sees what's allowed.
export function useGoogleConnection(enabled: boolean) {
  const [status, setStatus] = useState<GoogleStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setStatus(await authedFetch<GoogleStatus>('/integrations/google/status'))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check your Google connection')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    authedFetch<GoogleStatus>('/integrations/google/status')
      .then((s) => !cancelled && setStatus(s))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Could not check your Google connection'))
    return () => {
      cancelled = true
    }
  }, [enabled])

  async function connect(part: GooglePart = 'gmail') {
    setBusy(true)
    try {
      const { url } = await authedFetch<{ url: string }>(`/integrations/google/auth-url?part=${part}`)
      window.location.href = url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start Google sign-in')
      setBusy(false)
    }
  }

  // One part, or the whole Google account.
  async function disconnect(part?: GooglePart) {
    setBusy(true)
    try {
      await authedFetch(`/integrations/google${part ? `?part=${part}` : ''}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  return { status, error, busy, connect, disconnect, refresh }
}
