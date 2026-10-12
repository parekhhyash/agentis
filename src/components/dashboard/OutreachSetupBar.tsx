import type { Tables } from '../../lib/database.types'
import type { GooglePart, GoogleStatus } from '../../lib/googleConnection'
import { GoogleIcon } from '../icons'

type AgentRequest = Tables<'agent_requests'>

// Sits above the composer while Sales & Outreach is selected: the Gmail
// account the agent sends from (and whether Calendar is there for meetings),
// and optionally a past lead research run whose contacts it may write to.
export default function OutreachSetupBar({
  status,
  error,
  busy,
  onConnect,
  onDisconnect,
  leadRuns,
  leadRequestId,
  onLeadRequestChange,
}: {
  status: GoogleStatus | null
  error: string | null
  busy: boolean
  onConnect: (part: GooglePart) => void
  onDisconnect: () => void
  leadRuns: AgentRequest[]
  leadRequestId: string | null
  onLeadRequestChange: (id: string | null) => void
}) {
  if (!status) {
    return (
      <div className="mb-3 rounded-xl border border-slate-200 bg-surface px-4 py-3 text-sm text-slate-500">
        {error ?? 'Checking your Google connection…'}
      </div>
    )
  }

  if (!status.configured) {
    return (
      <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
        Google isn't set up on the server yet, so Sales &amp; Outreach can't send email or book meetings.
      </div>
    )
  }

  if (!status.connected) {
    return (
      <div className="mb-3 flex flex-col gap-3 rounded-xl border border-slate-200 bg-surface px-4 py-3 sm:flex-row sm:items-center">
        <p className="flex-1 text-sm text-slate-600">
          Connect Gmail so this agent can draft and send email from your own account. You approve everything
          before it's sent.
        </p>
        <button
          type="button"
          onClick={() => onConnect('gmail')}
          disabled={busy}
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-full border border-slate-300 bg-surface px-4 py-2 text-sm font-medium text-slate-800 transition-colors hover:bg-slate-50 disabled:opacity-50"
        >
          <GoogleIcon />
          {busy ? 'Opening Google…' : 'Connect Gmail'}
        </button>
      </div>
    )
  }

  return (
    <div className="mb-3 flex flex-col gap-2 rounded-xl border border-slate-200 bg-surface px-4 py-2.5 text-sm sm:flex-row sm:items-center sm:gap-4">
      <div className="flex min-w-0 items-center gap-2 text-slate-600">
        <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
        <span className="truncate">
          Sending as <span className="font-medium text-slate-800">{status.email}</span>
        </span>
        <button
          type="button"
          onClick={onDisconnect}
          disabled={busy}
          className="shrink-0 text-xs text-slate-400 underline-offset-2 hover:text-slate-600 hover:underline"
        >
          Disconnect
        </button>
        {!status.calendar && (
          <button
            type="button"
            onClick={() => onConnect('calendar')}
            disabled={busy}
            title="Needed to book meetings"
            className="shrink-0 text-xs font-medium text-sky-600 hover:underline"
          >
            Connect Calendar for meetings
          </button>
        )}
      </div>
      {leadRuns.length > 0 && (
        <label className="flex min-w-0 items-center gap-2 text-slate-600 sm:ml-auto">
          <span className="shrink-0">Leads</span>
          <select
            value={leadRequestId ?? ''}
            onChange={(e) => onLeadRequestChange(e.target.value || null)}
            className="min-w-0 flex-1 truncate rounded-lg border border-slate-200 bg-surface px-2 py-1 text-sm text-slate-800 sm:max-w-64"
          >
            <option value="">None</option>
            {leadRuns.map((run) => (
              <option key={run.id} value={run.id}>
                {run.prompt.length > 60 ? `${run.prompt.slice(0, 60)}…` : run.prompt}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  )
}
