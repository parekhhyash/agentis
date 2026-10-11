import { useState } from 'react'

import type { SocialProvider, useSocialConnections } from '../../lib/content'

// The controls inside the LinkedIn / X / Notion / Medium cards on the Connect page.
export default function SocialConnectControls({
  provider,
  social,
}: {
  provider: SocialProvider
  social: ReturnType<typeof useSocialConnections>
}) {
  const status = social.byProvider(provider)
  const [error, setError] = useState<string | null>(null)
  const [token, setToken] = useState('')
  // Captured once: the page doesn't need to tick to know a token is ending soon.
  const [now] = useState(() => Date.now())
  const busy = social.busy === provider

  if (!status) return <p className="text-sm text-slate-400">{social.error ?? 'Checking…'}</p>
  if (!status.configured) return <p className="text-sm text-amber-700">Not set up on the server yet.</p>

  const expires = status.expires_at ? new Date(status.expires_at) : null
  const expiring = provider === 'linkedin' && expires && expires.getTime() - now < 7 * 24 * 3600 * 1000

  return (
    <div className="space-y-2">
      {status.connected ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
            <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
            <span className="truncate">{status.account}</span>
          </span>
          <button
            type="button"
            onClick={() => void social.disconnect(provider)}
            disabled={busy}
            className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 disabled:opacity-50"
          >
            Disconnect
          </button>
        </div>
      ) : status.connect_with === 'token' ? (
        <form
          className="space-y-2"
          onSubmit={async (e) => {
            e.preventDefault()
            setError(null)
            const problem = await social.connectWithToken(provider, token.trim())
            if (problem) setError(problem)
            else setToken('')
          }}
        >
          <p className="text-xs leading-relaxed text-slate-500">
            Medium stopped issuing API tokens in 2025. If you made one before then, find it in Medium under Settings,
            Security and apps, Integration tokens. Without one, use Copy for Medium on a story.
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Integration token"
              autoComplete="off"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-surface px-3 py-1.5 text-sm text-slate-800 focus:border-sky-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || token.trim().length < 10}
              className="rounded-full bg-brand-blue px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
            >
              {busy ? 'Checking…' : 'Connect'}
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={async () => {
            setError(null)
            const problem = await social.connect(provider)
            if (problem) setError(problem)
          }}
          className="rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
        >
          {busy ? `Opening ${status.name}…` : 'Connect'}
        </button>
      )}
      {expiring && expires && (
        <p className="text-xs text-amber-700">LinkedIn access ends {expires.toLocaleDateString()}; reconnect to keep posting.</p>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  )
}
