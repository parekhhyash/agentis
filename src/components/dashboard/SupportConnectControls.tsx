import { useState } from 'react'

import type { SupportConnectDetails, SupportProvider, useSupportConnections } from '../../lib/support'
import Dialog from './Dialog'

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none'
const primaryButton =
  'rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50'

// Where each company finds its own key; nothing is set up on Agentis's side.
const KEY_HELP: Record<'freshdesk' | 'zendesk', string> = {
  freshdesk: 'In Freshdesk, click your profile picture, open Profile settings and copy "Your API key".',
  zendesk:
    'In Zendesk Admin Center: Apps and integrations > APIs > Zendesk API. Turn on Token access, then Add API token. Use it with the email of the agent it belongs to.',
}

// The controls inside a helpdesk card on the Connect page. Typing the address
// and key happens in a dialog, so the card keeps the size of the others.
export default function SupportConnectControls({
  provider,
  support,
}: {
  provider: SupportProvider
  support: ReturnType<typeof useSupportConnections>
}) {
  const status = support.byProvider(provider)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<SupportConnectDetails>({ domain: '', api_key: '', email: '' })
  const [error, setError] = useState<string | null>(null)
  const busy = support.busy === provider

  if (!status) return <p className="text-sm text-slate-400">{support.error ?? 'Checking…'}</p>
  if (!status.configured) return <p className="text-sm text-amber-700">Not set up on the server yet.</p>

  async function connect(details: SupportConnectDetails = {}) {
    setError(null)
    const problem = await support.connect(provider, details)
    if (problem) setError(problem)
    else if (status?.connect_with === 'key') {
      setOpen(false)
      setForm({ domain: '', api_key: '', email: '' })
    }
  }

  function close() {
    setOpen(false)
    setError(null)
  }

  const zendesk = provider === 'zendesk'
  return (
    <div className="space-y-2">
      {status.connected ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
            <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
            <span className="truncate" title={status.account ?? undefined}>
              {status.account}
            </span>
          </span>
          <button
            type="button"
            onClick={() => void support.disconnect(provider)}
            disabled={busy}
            className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 disabled:opacity-50"
          >
            Disconnect
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => (status.connect_with === 'oauth' ? void connect() : setOpen(true))}
          className={primaryButton}
        >
          {busy && status.connect_with === 'oauth' ? `Opening ${status.name}…` : 'Connect'}
        </button>
      )}
      {error && !open && <p className="text-sm text-red-700">{error}</p>}

      {status.connect_with === 'key' && (
        <Dialog open={open} onClose={close} title={`Connect ${status.name}`}>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              void connect(zendesk ? form : { domain: form.domain, api_key: form.api_key })
            }}
          >
            <p className="text-sm leading-relaxed text-slate-600">{KEY_HELP[provider as 'freshdesk' | 'zendesk']}</p>
            <label className="block">
              <span className="mb-1 block text-xs text-slate-500">Your {status.name} address</span>
              <input
                value={form.domain}
                required
                autoFocus
                onChange={(e) => setForm({ ...form, domain: e.target.value })}
                placeholder={zendesk ? 'yourcompany.zendesk.com' : 'yourcompany.freshdesk.com'}
                className={inputClass}
              />
            </label>
            {zendesk && (
              <label className="block">
                <span className="mb-1 block text-xs text-slate-500">Agent email</span>
                <input
                  type="email"
                  value={form.email}
                  required
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="you@yourcompany.com"
                  className={inputClass}
                />
              </label>
            )}
            <label className="block">
              <span className="mb-1 block text-xs text-slate-500">{zendesk ? 'API token' : 'API key'}</span>
              <input
                type="password"
                autoComplete="off"
                value={form.api_key}
                required
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                className={`${inputClass} font-mono`}
              />
            </label>
            <p className="text-xs text-slate-500">
              Agentis checks the key works, then keeps it encrypted. It reads tickets and only posts a reply or note you
              approve; it never deletes tickets.
            </p>
            {error && <p className="text-sm text-red-700">{error}</p>}
            <button
              type="submit"
              disabled={busy || !form.domain?.trim() || !form.api_key?.trim() || (zendesk && !form.email?.trim())}
              className={primaryButton}
            >
              {busy ? 'Checking…' : 'Connect'}
            </button>
          </form>
        </Dialog>
      )}
    </div>
  )
}
