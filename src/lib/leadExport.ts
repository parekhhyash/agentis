import type { LeadResearchResult } from './salesAgentTypes'

const COLUMNS = [
  'Company',
  'Website',
  'Fit',
  'Industry',
  'Location',
  'Employees',
  'Why relevant',
  'Signals',
  'Contact name',
  'Contact title',
  'LinkedIn',
  'Email',
  'Email found on',
  'Contact source',
  'General emails',
  'Contact page',
  'Sources',
]

function csvCell(value: string | null | undefined): string {
  const text = value ?? ''
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

// One row per contact (like the on-screen table); companies without a
// contact still get a row so nothing drops out of the export.
export function leadRows(result: LeadResearchResult): string[][] {
  const rows: string[][] = []
  for (const lead of result.leads) {
    const company = [
      lead.company_name,
      lead.website,
      lead.qualification,
      lead.industry ?? '',
      lead.location ?? '',
      lead.employee_count ?? '',
      lead.why_relevant,
      lead.relevant_signals.join('; '),
    ]
    const general = [lead.company_emails.join('; '), lead.contact_page ?? '', lead.sources.join(' ')]
    const contacts = lead.contacts.length > 0 ? lead.contacts : [null]
    for (const contact of contacts) {
      rows.push([
        ...company,
        contact?.name ?? '',
        contact?.title ?? '',
        contact?.linkedin_url ?? '',
        contact?.email ?? '',
        contact?.email_source_url ?? '',
        contact?.source_url ?? '',
        ...general,
      ])
    }
  }
  return rows
}

export function leadsToCsv(result: LeadResearchResult): string {
  return [COLUMNS, ...leadRows(result)].map((row) => row.map(csvCell).join(',')).join('\r\n')
}

// The same rows for a new Google Sheet.
export function leadsTable(result: LeadResearchResult) {
  const date = new Date().toISOString().slice(0, 10)
  return { title: `Leads ${date}${result.icp.summary ? ` · ${result.icp.summary}` : ''}`.slice(0, 200), tab: 'Leads', headers: COLUMNS, rows: leadRows(result) }
}

export function downloadLeadsCsv(result: LeadResearchResult): void {
  // BOM so Excel opens UTF-8 (names, ₹, accents) correctly.
  const blob = new Blob(['﻿', leadsToCsv(result)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `leads-${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
