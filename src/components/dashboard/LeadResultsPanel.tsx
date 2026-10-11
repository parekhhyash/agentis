import { useState } from 'react'

import { downloadLeadsCsv, leadsTable } from '../../lib/leadExport'
import SheetsExportButton from './SheetsExportButton'
import {
  isLeadResearchResult,
  type AnyLeadResult,
  type LeadResearchResult,
  type LegacyLead,
  type LegacyLeadGenerationResult,
  type ResearchLead,
} from '../../lib/salesAgentTypes'

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function FitBadge({ label }: { label: string }) {
  const strong = label.toLowerCase().startsWith('strong')
  return (
    <span
      className={`inline-block shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
        strong ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
      }`}
    >
      {label}
    </span>
  )
}

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-sky-600 hover:underline">
      {children}
    </a>
  )
}

// Lets a long address wrap after the "@" (care@ / mamaearth.in) before
// breaking anywhere else.
function EmailText({ email }: { email: string }) {
  const at = email.indexOf('@')
  if (at < 0) return <>{email}</>
  return (
    <>
      {email.slice(0, at + 1)}
      <wbr />
      {email.slice(at + 1)}
    </>
  )
}

function LeadRows({ lead }: { lead: ResearchLead }) {
  const contacts = lead.contacts.length > 0 ? lead.contacts : [null]
  const span = contacts.length
  const cell = 'border-t border-slate-100 px-2 py-2.5 align-top break-words'

  return (
    <>
      {contacts.map((contact, i) => (
        <tr key={contact ? contact.source_url : 'none'}>
          {i === 0 && (
            <>
              <td rowSpan={span} className={cell}>
                <div className="font-semibold text-slate-900">{lead.company_name}</div>
                <ExternalLink href={lead.website}>{hostname(lead.website)}</ExternalLink>
                <div className="mt-1">
                  <FitBadge label={lead.qualification} />
                </div>
                {lead.contact_page && (
                  <a
                    href={lead.contact_page}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block text-xs text-sky-600 hover:underline"
                  >
                    Contact page
                  </a>
                )}
              </td>
              <td rowSpan={span} className={`${cell} text-slate-700`}>
                {lead.industry ?? '–'}
                {lead.location && <div className="text-xs text-slate-500">{lead.location}</div>}
                {lead.employee_count && <div className="text-xs text-slate-500">{lead.employee_count} employees</div>}
              </td>
              <td rowSpan={span} className={`${cell} text-slate-700`}>
                {lead.why_relevant || '–'}
              </td>
            </>
          )}
          <td className={cell}>
            {contact ? (
              <>
                <div className="font-medium text-slate-800">{contact.name}</div>
                <div className="text-xs text-slate-500">{contact.title}</div>
                {!contact.linkedin_url && (
                  <a href={contact.source_url} target="_blank" rel="noreferrer" className="text-xs text-slate-400 hover:underline">
                    named on their site
                  </a>
                )}
              </>
            ) : (
              <span className="text-slate-400">Not found</span>
            )}
          </td>
          <td className={cell}>
            {contact?.linkedin_url ? <ExternalLink href={contact.linkedin_url}>Profile</ExternalLink> : <span className="text-slate-400">–</span>}
          </td>
          <td className={cell}>
            {contact?.email && (
              <>
                <a href={`mailto:${contact.email}`} className="text-[13px] [overflow-wrap:anywhere] text-sky-600 hover:underline">
                  <EmailText email={contact.email} />
                </a>
                {contact.email_source_url && (
                  <a
                    href={contact.email_source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-xs text-slate-400 hover:underline"
                  >
                    listed on their site
                  </a>
                )}
              </>
            )}
            {/* Company inboxes (hello@, support@...) once per company, labelled so
                they aren't mistaken for this person's address. */}
            {i === 0 && lead.company_emails.length > 0 && (
              <div className={contact?.email ? 'mt-2' : undefined}>
                <div className="text-[11px] text-slate-400">General</div>
                {lead.company_emails.map((email) => (
                  <a key={email} href={`mailto:${email}`} className="block text-[13px] [overflow-wrap:anywhere] text-sky-600 hover:underline">
                    <EmailText email={email} />
                  </a>
                ))}
              </div>
            )}
            {!contact?.email && !(i === 0 && lead.company_emails.length > 0) && (
              <span className="text-slate-400">–</span>
            )}
          </td>
        </tr>
      ))}
    </>
  )
}

function LeadEvidence({ lead }: { lead: ResearchLead }) {
  return (
    <details className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
      <summary className="cursor-pointer font-medium text-slate-800">
        {lead.company_name} <span className="font-normal text-slate-500">· evidence & sources</span>
      </summary>
      {lead.relevant_signals.length > 0 && (
        <div className="mt-2">
          <div className="text-xs text-slate-400">Signals</div>
          <ul className="list-disc pl-5 text-slate-700">
            {lead.relevant_signals.map((signal) => (
              <li key={signal}>{signal}</li>
            ))}
          </ul>
        </div>
      )}
      {lead.evidence.length > 0 && (
        <div className="mt-2">
          <div className="text-xs text-slate-400">Evidence</div>
          <ul className="space-y-1">
            {lead.evidence.map((item) => (
              <li key={`${item.claim}-${item.source_url}`} className="text-slate-700">
                {item.claim}{' '}
                <span className={`text-xs ${item.status === 'verified' ? 'text-green-700' : 'text-amber-700'}`}>
                  ({item.status})
                </span>{' '}
                <ExternalLink href={item.source_url}>{hostname(item.source_url)}</ExternalLink>
              </li>
            ))}
          </ul>
        </div>
      )}
      {lead.contacts.length > 0 && (
        <div className="mt-2 text-xs text-slate-500">
          Contact sources:{' '}
          {lead.contacts.map((c, i) => (
            <span key={c.source_url}>
              {i > 0 && ', '}
              <ExternalLink href={c.source_url}>{c.name}</ExternalLink>
            </span>
          ))}
        </div>
      )}
      {lead.contact_page && (
        <div className="mt-1 text-xs">
          <ExternalLink href={lead.contact_page}>Company contact page</ExternalLink>
        </div>
      )}
    </details>
  )
}

function ResearchResults({
  result,
  crms,
  onAddToCrm,
  sheetsConnected,
}: {
  result: LeadResearchResult
  crms: string[]
  onAddToCrm?: (crmName: string, count: number) => void
  sheetsConnected: boolean
}) {
  const [asked, setAsked] = useState<string | null>(null)
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs text-slate-500">
          {result.leads_found} of {result.requested_leads} lead{result.requested_leads === 1 ? '' : 's'}
          {result.icp.summary && ` · ${result.icp.summary}`}
        </p>
        {result.leads.length > 0 && (
          <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
            {onAddToCrm &&
              crms.map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={asked === name}
                  onClick={() => {
                    setAsked(name)
                    onAddToCrm(name, result.leads.length)
                  }}
                  className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                >
                  {asked === name ? `Asked to add to ${name}` : `Add to ${name}`}
                </button>
              ))}
            <button
              type="button"
              onClick={() => downloadLeadsCsv(result)}
              className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
            >
              Export CSV
            </button>
            {sheetsConnected && (
              <SheetsExportButton
                table={() => leadsTable(result)}
                className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50"
              />
            )}
          </div>
        )}
      </div>
      {result.notes && <p className="mt-1 text-xs text-amber-700">{result.notes}</p>}

      {result.leads.length > 0 && (
        <>
          <div className="mt-3 overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[600px] table-fixed text-left text-sm">
              <thead className="bg-slate-50 text-xs font-medium text-slate-500">
                <tr>
                  <th className="w-[20%] px-2 py-2">Company</th>
                  <th className="w-[13%] px-2 py-2">Industry</th>
                  <th className="w-[22%] px-2 py-2">Why relevant</th>
                  <th className="w-[17%] px-2 py-2">Contact</th>
                  <th className="w-[9%] px-2 py-2">LinkedIn</th>
                  <th className="w-[19%] px-2 py-2">Email</th>
                </tr>
              </thead>
              <tbody>
                {result.leads.map((lead) => (
                  <LeadRows key={lead.website} lead={lead} />
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-3 space-y-2">
            {result.leads.map((lead) => (
              <LeadEvidence key={lead.website} lead={lead} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function LegacyLeadCard({ lead }: { lead: LegacyLead }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="font-semibold text-slate-900">{lead.company_name}</h4>
          {lead.website && <ExternalLink href={lead.website}>{lead.website}</ExternalLink>}
        </div>
        <span className="shrink-0 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">
          {lead.qualification_score}/100
        </span>
      </div>
      {lead.description && <p className="mt-2 text-sm text-slate-600">{lead.description}</p>}
      {lead.why_good_fit && (
        <p className="mt-3 rounded-lg bg-sky-50 p-2.5 text-sm text-sky-900 dark:text-sky-200">
          <span className="font-medium">Why a good fit: </span>
          {lead.why_good_fit}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        {lead.business_email && (
          <a href={`mailto:${lead.business_email}`} className="text-sky-600 hover:underline">
            {lead.business_email}
          </a>
        )}
        {lead.contact_page && <ExternalLink href={lead.contact_page}>Contact page</ExternalLink>}
        {lead.sources.map((src) => (
          <ExternalLink key={src} href={src}>
            source
          </ExternalLink>
        ))}
      </div>
    </div>
  )
}

function LegacyResults({ result }: { result: LegacyLeadGenerationResult }) {
  return (
    <div>
      <p className="text-xs text-slate-500">
        {result.leads_found} lead{result.leads_found === 1 ? '' : 's'} qualified
        {result.criteria.industry && ` · ${result.criteria.industry}`}
        {result.criteria.geography && ` · ${result.criteria.geography}`}
      </p>
      {result.notes && <p className="mt-1 text-xs text-amber-700">{result.notes}</p>}
      <div className="mt-3 space-y-3">
        {result.leads.map((lead, i) => (
          <LegacyLeadCard key={`${lead.company_name}-${i}`} lead={lead} />
        ))}
      </div>
    </div>
  )
}

export default function LeadResultsPanel({
  result,
  crms = [],
  onAddToCrm,
  sheetsConnected = false,
}: {
  result: AnyLeadResult
  crms?: string[]
  onAddToCrm?: (crmName: string, count: number) => void
  // Google Sheets is connected: offer "Export to Google Sheets".
  sheetsConnected?: boolean
}) {
  return isLeadResearchResult(result) ? (
    <ResearchResults result={result} crms={crms} onAddToCrm={onAddToCrm} sheetsConnected={sheetsConnected} />
  ) : (
    <LegacyResults result={result} />
  )
}
