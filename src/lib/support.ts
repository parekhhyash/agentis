import { useCallback, useEffect, useState } from 'react'

import { authedFetch } from './backendApi'

// Mirrors backend/agents/customer_support/schemas.py.
export type SupportSource = 'freshdesk' | 'zendesk' | 'zoho_desk' | 'gmail'
export type SupportProvider = Exclude<SupportSource, 'gmail'>

export interface SupportDraft {
  body: string
  suggested: 'reply' | 'note'
  status: 'draft' | 'noted' | 'sent' | 'discarded' | 'failed'
  error: string | null
  done_at: string | null
}

export interface SupportTicket {
  id: string
  ticket_id: string
  subject: string
  requester: string
  requester_email: string | null
  status: string
  priority: string | null
  url: string | null
  awaiting_reply: boolean
  triage: {
    category: string
    urgency: 'low' | 'medium' | 'high' | 'urgent'
    sentiment: 'positive' | 'neutral' | 'negative' | 'angry'
    summary: string
    tags: string[]
  }
  needs_human: boolean
  needs_human_reason: string | null
  draft: SupportDraft | null
  warnings: string[]
  articles: { title: string; url: string | null }[]
  triage_applied: boolean
  triage_error: string | null
}

export interface SupportResult {
  kind: 'customer_support'
  summary: string
  source: SupportSource
  source_name: string
  account: string | null
  query: string
  mode: 'draft' | 'triage' | 'summarize'
  tickets: SupportTicket[]
  notes: string[]
}

export function isSupportResult(value: unknown): value is SupportResult {
  return typeof value === 'object' && value !== null && (value as { kind?: string }).kind === 'customer_support'
}

export type TicketDecision = 'reply' | 'note' | 'triage' | 'save' | 'discard'

// Acts on one ticket's draft: send it as a reply or private note (with the
// user's edits), set the suggested priority and tags, keep an edit, or drop it.
export function decideTicket(
  requestId: string,
  draftId: string,
  decision: TicketDecision,
  body?: string,
  senderName?: string | null,
): Promise<SupportTicket> {
  return authedFetch<SupportTicket>(`/support/requests/${requestId}/tickets/${draftId}`, {
    method: 'POST',
    body: JSON.stringify({ decision, body, sender_name: senderName ?? undefined }),
  })
}

export interface SupportProviderStatus {
  provider: SupportProvider
  name: string
  configured: boolean
  connected: boolean
  account: string | null
  connected_at: string | null
  // key: the company's own address and API key; oauth: Agentis's Zoho app.
  connect_with: 'key' | 'oauth'
}

export interface SupportConnectDetails {
  domain?: string
  api_key?: string
  email?: string
}

// The user's helpdesk connections. Keys stay on the backend; this only sees
// which helpdesks are connected and as whom.
export function useSupportConnections(enabled = true) {
  const [providers, setProviders] = useState<SupportProviderStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<SupportProvider | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await authedFetch<{ providers: SupportProviderStatus[] }>('/integrations/support')
      setProviders(data.providers)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check your helpdesk connections')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    authedFetch<{ providers: SupportProviderStatus[] }>('/integrations/support')
      .then((data) => !cancelled && setProviders(data.providers))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Could not check your helpdesk connections'))
    return () => {
      cancelled = true
    }
  }, [enabled])

  // Freshdesk and Zendesk: the key is checked and saved right away. Zoho
  // Desk: off to Zoho's sign-in page.
  async function connect(provider: SupportProvider, details: SupportConnectDetails = {}): Promise<string | null> {
    setBusy(provider)
    try {
      const out = await authedFetch<{ url?: string }>(`/integrations/support/${provider}/connect`, {
        method: 'POST',
        body: JSON.stringify(details),
      })
      if (out.url) {
        window.location.href = out.url
        return null
      }
      await refresh()
      setBusy(null)
      return null
    } catch (err) {
      setBusy(null)
      return err instanceof Error ? err.message : 'Could not connect'
    }
  }

  async function disconnect(provider: SupportProvider) {
    setBusy(provider)
    try {
      await authedFetch(`/integrations/support/${provider}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusy(null)
    }
  }

  const byProvider = (provider: SupportProvider) => providers?.find((p) => p.provider === provider)

  return { providers, error, busy, connect, disconnect, refresh, byProvider }
}
