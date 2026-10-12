import { useCallback, useEffect, useState } from 'react'

import { authedFetch } from './backendApi'

export interface GoogleStatus {
  configured: boolean
  // Gmail and Calendar are allowed.
  connected: boolean
  // Google Sheets is allowed (same Google account, its own permission).
  sheets?: boolean
  email: string | null
}

// The user's Google connection: Gmail + Calendar for Sales & Outreach, and
// Google Sheets for data files and exports. Tokens stay on the backend; this
// only sees what's allowed.
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

  // `sheets === true` asks for Google Sheets only (other values, like a click
  // event, mean Gmail and Calendar).
  async function connect(sheets?: unknown) {
    setBusy(true)
    try {
      const { url } = await authedFetch<{ url: string }>(`/integrations/google/auth-url${sheets === true ? '?sheets=true' : ''}`)
      window.location.href = url
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start Google sign-in')
      setBusy(false)
    }
  }

  // One part (Gmail and Calendar, or Sheets), or the whole Google account.
  async function disconnect(part?: 'gmail' | 'sheets') {
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
