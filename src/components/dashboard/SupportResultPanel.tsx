import { useState } from 'react'

import { BackendApiError } from '../../lib/backendApi'
import { relativeTime } from '../../lib/relativeTime'
import { decideTicket, type SupportResult, type SupportTicket, type TicketDecision } from '../../lib/support'

const inputClass =
  'w-full rounded-lg border border-slate-200 bg-transparent px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none disabled:opacity-70'
const secondary = 'rounded-full border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50'
const primary = 'rounded-full bg-brand-blue px-3.5 py-1 text-sm font-semibold text-white hover:bg-brand-blue/90 disabled:opacity-50'

const URGENCY: Record<SupportTicket['triage']['urgency'], string> = {
  urgent: 'bg-red-50 text-red-700',
  high: 'bg-amber-50 text-amber-700',
  medium: 'bg-sky-50 text-sky-700',
  low: 'bg-slate-100 text-slate-600',
}
const RANK = { urgent: 0, high: 1, medium: 2, low: 3 }

function TicketCard({
  requestId,
  ticket,
  source,
  sourceName,
  senderName,
  onChange,
}: {
  requestId: string
  ticket: SupportTicket
  source: SupportResult['source']
  sourceName: string
  senderName?: string | null
  onChange: (ticket: SupportTicket) => void
}) {
  const draft = ticket.draft
  const [body, setBody] = useState(draft?.body ?? '')
  const [busy, setBusy] = useState<TicketDecision | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const helpdesk = source !== 'gmail'
  const done = draft && ['sent', 'noted', 'discarded'].includes(draft.status)
  const edited = draft ? body.trim() !== draft.body : false

  async function decide(decision: TicketDecision) {
    setBusy(decision)
    setError(null)
    try {
      const updated = await decideTicket(requestId, ticket.id, decision, decision === 'triage' ? undefined : body, senderName)
      onChange(updated)
      if (updated.draft) setBody(updated.draft.body)
      setConfirming(false)
    } catch (err) {
      setError(err instanceof BackendApiError ? err.message : 'That didn’t work; try again')
    } finally {
      setBusy(null)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(body)
      setError(null)
    } catch {
      setError('Copy failed; select the text instead')
    }
  }

  const sentiment = ticket.triage.sentiment === 'angry' || ticket.triage.sentiment === 'negative'
  return (
    <article className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-medium text-slate-900">
            <span className="text-slate-400">#{ticket.ticket_id}</span> {ticket.subject}
          </h3>
          <p className="text-xs text-slate-500">
            {ticket.requester}
            {ticket.requester_email && ticket.requester_email !== ticket.requester ? ` · ${ticket.requester_email}` : ''}
          </p>
        </div>
        {ticket.url && (
          <a href={ticket.url} target="_blank" rel="noreferrer" className="shrink-0 text-xs font-medium text-sky-600 hover:underline">
            Open in {sourceName}
          </a>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] font-medium">
        <span className={`rounded-full px-2 py-0.5 ${URGENCY[ticket.triage.urgency]}`}>{ticket.triage.urgency}</span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{ticket.triage.category}</span>
        <span className={`rounded-full px-2 py-0.5 ${sentiment ? 'bg-red-50 text-red-700' : 'bg-slate-100 text-slate-600'}`}>
          {ticket.triage.sentiment}
        </span>
        {ticket.triage.tags.filter((tag) => tag !== ticket.triage.category).map((tag) => (
          <span key={tag} className="rounded-full border border-slate-200 px-2 py-0.5 text-slate-500">
            {tag}
          </span>
        ))}
      </div>
      {ticket.triage.summary && <p className="mt-2 text-sm text-slate-600">{ticket.triage.summary}</p>}
      {ticket.needs_human && (
        <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-700">
          <span className="font-medium">Needs your team:</span> {ticket.needs_human_reason ?? 'the agent couldn’t answer this from what it has.'}
        </p>
      )}

      {draft && (
        <div className="mt-3">
          <p className="mb-1 text-xs font-medium text-slate-500">
            {draft.suggested === 'reply' ? `Reply to ${ticket.requester.split(' ')[0]}` : 'Note for your team'}
          </p>
          <textarea
            className={`${inputClass} resize-y leading-relaxed`}
            disabled={Boolean(done) || busy !== null}
            rows={Math.min(14, Math.max(4, body.split('\n').length + 1))}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            aria-label={`Draft for ticket ${ticket.ticket_id}`}
          />
          {ticket.warnings.length > 0 && !done && (
            <ul className="mt-1.5 space-y-0.5 text-xs text-amber-700">
              {ticket.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          {ticket.articles.length > 0 && (
            <p className="mt-1.5 text-xs text-slate-500">
              From your help articles:{' '}
              {ticket.articles.map((a, i) => (
                <span key={a.title}>
                  {i > 0 && ', '}
                  {a.url ? (
                    <a href={a.url} target="_blank" rel="noreferrer" className="text-sky-600 hover:underline">
                      {a.title}
                    </a>
                  ) : (
                    a.title
                  )}
                </span>
              ))}
            </p>
          )}
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        {helpdesk && !ticket.triage_applied && (
          <button type="button" disabled={busy !== null} onClick={() => void decide('triage')} className={`${secondary} mr-auto`}>
            {busy === 'triage' ? 'Setting…' : `Set ${ticket.triage.urgency} priority and tags`}
          </button>
        )}
        {helpdesk && ticket.triage_applied && <span className="mr-auto text-xs text-emerald-700">Priority and tags set</span>}

        {draft && !done && (
          <>
            {edited && (
              <button type="button" disabled={busy !== null} onClick={() => void decide('save')} className={secondary}>
                {busy === 'save' ? 'Saving…' : 'Save'}
              </button>
            )}
            <button type="button" disabled={busy !== null} onClick={() => void decide('discard')} className="rounded-full px-3 py-1 text-sm text-slate-500 hover:bg-slate-100">
              Discard
            </button>
            {!helpdesk && draft.suggested === 'note' && (
              <button type="button" onClick={() => void copy()} className={secondary}>
                Copy
              </button>
            )}
            {helpdesk && (
              <button
                type="button"
                disabled={busy !== null || !body.trim()}
                onClick={() => void decide('note')}
                className={draft.suggested === 'note' ? primary : secondary}
              >
                {busy === 'note' ? 'Posting…' : 'Post as private note'}
              </button>
            )}
            {/* A note is written for the team, so it never goes to the customer from here. */}
            {draft.suggested === 'reply' &&
              (confirming ? (
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-slate-600">Send to {ticket.requester}?</span>
                  <button type="button" onClick={() => setConfirming(false)} className="rounded-full px-3 py-1 text-slate-500 hover:bg-slate-100">
                    Cancel
                  </button>
                  <button type="button" disabled={busy !== null} onClick={() => void decide('reply')} className={primary}>
                    {busy === 'reply' ? 'Sending…' : 'Send'}
                  </button>
                </span>
              ) : (
                <button type="button" disabled={busy !== null || !body.trim()} onClick={() => setConfirming(true)} className={primary}>
                  Send reply
                </button>
              ))}
          </>
        )}
        {draft?.status === 'sent' && (
          <span className="text-sm text-emerald-700">Sent to the customer {draft.done_at ? relativeTime(draft.done_at) : ''}</span>
        )}
        {draft?.status === 'noted' && (
          <span className="text-sm text-emerald-700">Posted as a private note {draft.done_at ? relativeTime(draft.done_at) : ''}</span>
        )}
        {draft?.status === 'discarded' && <span className="text-sm text-slate-400">Discarded</span>}
      </div>
      {(error || (draft?.status === 'failed' && draft.error) || ticket.triage_error) && (
        <p className="mt-2 text-xs text-red-700">{error ?? (draft?.status === 'failed' ? draft.error : null) ?? ticket.triage_error}</p>
      )}
    </article>
  )
}

// Customer Support's answer: each ticket triaged, with its draft reply or note
// to edit and approve. Nothing reaches a customer until "Send" is pressed.
export default function SupportResultPanel({
  requestId,
  result,
  onResultChange,
  senderName,
}: {
  requestId: string
  result: SupportResult
  onResultChange: (result: SupportResult) => void
  senderName?: string | null
}) {
  const tickets = [...result.tickets].sort((a, b) => RANK[a.triage.urgency] - RANK[b.triage.urgency])
  return (
    <div className="space-y-3">
      <p className="text-[15px] text-slate-800">{result.summary}</p>
      <p className="text-xs text-slate-500">
        {result.source_name}
        {result.account ? ` · ${result.account}` : ''}
      </p>
      {result.notes.length > 0 && (
        <ul className="space-y-1 text-sm text-amber-700">
          {result.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
      {tickets.map((ticket) => (
        <TicketCard
          key={ticket.id}
          requestId={requestId}
          ticket={ticket}
          source={result.source}
          sourceName={result.source_name}
          senderName={senderName}
          onChange={(updated) => onResultChange({ ...result, tickets: result.tickets.map((t) => (t.id === updated.id ? updated : t)) })}
        />
      ))}
    </div>
  )
}
