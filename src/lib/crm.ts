import { useCallback, useEffect, useState } from 'react'

import { authedFetch } from './backendApi'

// Mirrors backend/agents/crm/schemas.py and api/crm.py.

export type CrmProvider = 'hubspot' | 'salesforce' | 'zoho'

export interface CrmProviderStatus {
  provider: CrmProvider
  name: string
  configured: boolean
  connected: boolean
  account: string | null
  tool_count: number | null
  connected_at: string | null
  // oauth: Agentis's own app; app: the company's own Salesforce app; url: Zoho's MCP URL.
  connect_with: 'oauth' | 'app' | 'url'
  // Salesforce: what the company's admin needs, and the app last used.
  callback_url?: string
  servers?: Record<string, string>
  server_app?: boolean
  app?: { client_id: string; login_url: string } | null
}

// Zoho's MCP URL, or a company's Salesforce External Client App.
export interface CrmConnectDetails {
  mcp_url?: string
  client_id?: string
  client_secret?: string
  login_url?: string
  server?: string
}

export interface CrmTool {
  name: string
  kind: 'read' | 'write' | 'blocked'
  description: string
}

export interface CrmCall {
  provider: CrmProvider
  tool: string
  arguments: Record<string, unknown>
  ok: boolean
  preview: string
}

export interface CrmAction {
  id: string
  provider: CrmProvider
  tool: string
  arguments: Record<string, unknown>
  summary: string
  status: 'draft' | 'done' | 'discarded' | 'failed'
  result: string | null
  error: string | null
  done_at: string | null
  sign_in_url: string | null
}

export interface CrmResult {
  providers: CrmProvider[]
  calls: CrmCall[]
  actions: CrmAction[]
  sign_in: { provider: CrmProvider; url: string }[]
  notes: string[]
}

export const CRM_NAMES: Record<CrmProvider, string> = { hubspot: 'HubSpot', salesforce: 'Salesforce', zoho: 'Zoho CRM' }

export function decideCrmAction(requestId: string, actionId: string, decision: 'approve' | 'discard'): Promise<CrmAction> {
  return authedFetch<CrmAction>(`/crm/requests/${requestId}/actions/${actionId}`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  })
}

export function listCrmTools(provider: CrmProvider): Promise<{ tools: CrmTool[] }> {
  return authedFetch<{ tools: CrmTool[] }>(`/integrations/crm/${provider}/tools`)
}

// The user's CRM connections. Credentials stay on the backend; this only
// sees which CRMs are connected and as whom.
export function useCrmConnections(enabled = true) {
  const [providers, setProviders] = useState<CrmProviderStatus[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<CrmProvider | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await authedFetch<{ providers: CrmProviderStatus[] }>('/integrations/crm')
      setProviders(data.providers)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check your CRM connections')
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    authedFetch<{ providers: CrmProviderStatus[] }>('/integrations/crm')
      .then((data) => !cancelled && setProviders(data.providers))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Could not check your CRM connections'))
    return () => {
      cancelled = true
    }
  }, [enabled])

  // HubSpot and Salesforce: off to the CRM's sign-in page (Salesforce with the
  // company's own app). Zoho: the MCP URL is checked and saved right away.
  async function connect(provider: CrmProvider, details: CrmConnectDetails = {}): Promise<string | null> {
    setBusy(provider)
    try {
      const out = await authedFetch<{ url?: string }>(`/integrations/crm/${provider}/connect`, {
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

  async function disconnect(provider: CrmProvider) {
    setBusy(provider)
    try {
      await authedFetch(`/integrations/crm/${provider}`, { method: 'DELETE' })
      await refresh()
    } finally {
      setBusy(null)
    }
  }

  const connected = (providers ?? []).filter((p) => p.connected)
  return { providers, connected, error, busy, connect, disconnect, refresh }
}
