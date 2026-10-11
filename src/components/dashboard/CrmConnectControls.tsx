import { useState } from 'react'

import { listCrmTools, type CrmProvider, type CrmProviderStatus, type CrmTool, type useCrmConnections } from '../../lib/crm'

const KIND_LABELS: Record<CrmTool['kind'], { title: string; tone: string }> = {
  read: { title: 'Looks up on its own', tone: 'bg-emerald-50 text-emerald-700' },
  write: { title: 'Asks you first', tone: 'bg-amber-50 text-amber-700' },
  blocked: { title: 'Never used', tone: 'bg-slate-100 text-slate-500' },
}

const inputClass =
  'w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none'

// The last Salesforce app details entered on this browser (never the secret),
// so teammates and reconnects don't retype them.
const SF_KEY = 'agentis-salesforce-app'

function savedSalesforceApp(): { login_url: string; client_id: string; server: string } {
  try {
    const saved = JSON.parse(localStorage.getItem(SF_KEY) ?? '{}')
    return { login_url: saved.login_url ?? '', client_id: saved.client_id ?? '', server: saved.server ?? 'sobject-all' }
  } catch {
    return { login_url: '', client_id: '', server: 'sobject-all' }
  }
}

// Salesforce's hosted MCP servers only accept an app made in the same org, so
// each company's admin creates one once; people then connect with its key.
function SalesforceAppForm({
  status,
  busy,
  onConnect,
}: {
  status: CrmProviderStatus
  busy: boolean
  onConnect: (details: { client_id: string; client_secret: string; login_url: string; server: string }) => void
}) {
  const [form, setForm] = useState(() => ({ ...savedSalesforceApp(), client_secret: '' }))
  const [copied, setCopied] = useState(false)
  const optionalKey = Boolean(status.server_app)
  const servers = status.servers ?? { 'sobject-all': 'read and change records', 'sobject-reads': 'read records only' }

  async function copyCallback() {
    try {
      await navigator.clipboard.writeText(status.callback_url ?? '')
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        try {
          localStorage.setItem(SF_KEY, JSON.stringify({ login_url: form.login_url, client_id: form.client_id, server: form.server }))
        } catch {
          // Private mode: nothing to remember.
        }
        onConnect(form)
      }}
      className="space-y-2.5"
    >
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Your Salesforce domain (Setup &rsaquo; My Domain)</span>
        <input
          value={form.login_url}
          onChange={(e) => setForm({ ...form, login_url: e.target.value })}
          placeholder="yourcompany.my.salesforce.com"
          className={inputClass}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">
          Consumer key of your company&rsquo;s External Client App{optionalKey ? ' (blank: the server’s own app)' : ''}
        </span>
        <input
          value={form.client_id}
          required={!optionalKey}
          onChange={(e) => setForm({ ...form, client_id: e.target.value })}
          placeholder="3MVG9…"
          className={`${inputClass} font-mono`}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Consumer secret (only if the app requires one)</span>
        <input
          type="password"
          autoComplete="off"
          value={form.client_secret}
          onChange={(e) => setForm({ ...form, client_secret: e.target.value })}
          className={inputClass}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">MCP server your admin activated</span>
        <select value={form.server} onChange={(e) => setForm({ ...form, server: e.target.value })} className={inputClass}>
          {Object.entries(servers).map(([id, label]) => (
            <option key={id} value={id}>
              {id}: {label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="submit"
        disabled={busy || (!optionalKey && !form.client_id.trim())}
        className="rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
      >
        {busy ? 'Opening Salesforce…' : 'Connect'}
      </button>
      <details className="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
        <summary className="cursor-pointer font-medium text-slate-700">First time? Your Salesforce admin sets this up once</summary>
        <ol className="mt-2 list-decimal space-y-1.5 pl-4">
          <li>
            Setup &rsaquo; <b>MCP Servers</b>: activate <code>sobject-all</code> (or <code>sobject-reads</code> for read only).
          </li>
          <li>
            Setup &rsaquo; <b>External Client App Manager</b> &rsaquo; New: turn on OAuth with this callback URL{' '}
            <button type="button" onClick={() => void copyCallback()} className="font-medium text-sky-600 hover:underline">
              {copied ? '(copied)' : '(copy)'}
            </button>
            <code className="mt-1 block break-all rounded bg-surface px-2 py-1 text-[11px] text-slate-700">{status.callback_url}</code>
          </li>
          <li>
            Scopes: <b>mcp_api</b> (hosted MCP servers) and <b>refresh_token, offline_access</b>. Require PKCE, turn on JWT-based
            access tokens for named users, and leave &ldquo;require secret&rdquo; off (then no secret is needed).
          </li>
          <li>Share the app&rsquo;s Consumer Key and your My Domain with your team; each person connects with them here.</li>
        </ol>
      </details>
    </form>
  )
}

// The controls inside a CRM card on the Connect page.
export default function CrmConnectControls({
  provider,
  crm,
}: {
  provider: CrmProvider
  crm: ReturnType<typeof useCrmConnections>
}) {
  const status = crm.providers?.find((p) => p.provider === provider)
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [tools, setTools] = useState<CrmTool[] | null>(null)
  const [toolsOpen, setToolsOpen] = useState(false)
  const [loadingTools, setLoadingTools] = useState(false)
  const busy = crm.busy === provider

  async function connect(details: Parameters<typeof crm.connect>[1] = {}) {
    setError(null)
    const problem = await crm.connect(provider, provider === 'zoho' ? { mcp_url: url.trim() } : details)
    if (problem) setError(problem)
    else if (provider === 'zoho') setUrl('')
  }

  async function toggleTools() {
    if (toolsOpen) return setToolsOpen(false)
    setToolsOpen(true)
    if (tools) return
    setLoadingTools(true)
    try {
      setTools((await listCrmTools(provider)).tools)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the tools')
      setToolsOpen(false)
    } finally {
      setLoadingTools(false)
    }
  }

  if (!status) return <p className="text-sm text-slate-400">{crm.error ?? 'Checking…'}</p>
  if (!status.configured) return <p className="text-sm text-amber-700">Not set up on the server yet.</p>

  return (
    <div className="space-y-3">
      {status.connected ? (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2 text-sm text-slate-600">
            <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
            <span className="truncate" title={status.account ?? undefined}>
              {status.account}
            </span>
            {status.tool_count != null && <span className="shrink-0 text-xs text-slate-400">· {status.tool_count} tools</span>}
          </span>
          <span className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => void toggleTools()}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100"
            >
              {toolsOpen ? 'Hide tools' : 'View tools'}
            </button>
            <button
              type="button"
              onClick={() => void crm.disconnect(provider)}
              disabled={busy}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-500 transition-colors hover:bg-slate-100 disabled:opacity-50"
            >
              Disconnect
            </button>
          </span>
        </div>
      ) : status.connect_with === 'app' ? (
        <SalesforceAppForm status={status} busy={busy} onConnect={(details) => void connect(details)} />
      ) : status.connect_with === 'url' ? (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void connect()
          }}
          className="space-y-2"
        >
          <label htmlFor={`${provider}-mcp-url`} className="block text-xs text-slate-500">
            MCP server URL from Zoho CRM: Setup &rsaquo; Developer Hub &rsaquo; MCP for AI Agents (pick Data Operations to allow
            changes)
          </label>
          <div className="flex gap-2">
            <input
              id={`${provider}-mcp-url`}
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://…zohomcp.com/mcp/…/message"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || !url.trim()}
              className="shrink-0 rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
            >
              {busy ? 'Checking…' : 'Connect'}
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => void connect()}
          disabled={busy}
          className="rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
        >
          {busy ? `Opening ${status.name}…` : 'Connect'}
        </button>
      )}

      {error && <p className="text-sm text-red-700">{error}</p>}

      {toolsOpen && (
        <div className="rounded-xl border border-slate-200 p-3">
          {loadingTools || !tools ? (
            <p className="text-xs text-slate-400">Asking {status.name} for its tools…</p>
          ) : tools.length === 0 ? (
            <p className="text-xs text-slate-500">This server offers no tools.</p>
          ) : (
            <div className="space-y-2.5">
              {(['read', 'write', 'blocked'] as const).map((kind) => {
                const list = tools.filter((t) => t.kind === kind)
                if (list.length === 0) return null
                return (
                  <div key={kind}>
                    <p className="mb-1 text-xs font-medium text-slate-500">
                      {KIND_LABELS[kind].title} ({list.length})
                    </p>
                    <ul className="flex flex-wrap gap-1.5">
                      {list.map((t) => (
                        <li key={t.name} title={t.description} className={`rounded-md px-2 py-0.5 font-mono text-[11px] ${KIND_LABELS[kind].tone}`}>
                          {t.name}
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
