// Mirrors backend/agents/data_reporting/schemas.py.

export type Visual = 'kpi' | 'bar' | 'line' | 'pie' | 'table'
export type Cell = string | number | boolean | null

export interface ReportColumn {
  name: string
  // "text" | "number" | "date" | "month" | "boolean"
  type: string
  role: 'dimension' | 'metric' | 'field'
  unit?: string | null
}

export interface ReportBlock {
  id: string
  title: string
  visual: Visual
  dataset: string
  columns: ReportColumn[]
  rows: Cell[][]
  total: number
  matched_rows: number
  explanation: string
}

export interface DatasetRef {
  id: string
  name: string
  kind: 'activity' | 'upload'
  rows: number
}

export interface DataReportResult {
  kind: 'data_report'
  question: string
  title: string
  summary: string
  blocks: ReportBlock[]
  notes: string[]
  datasets: DatasetRef[]
  replies_checked_at: string | null
  generated_at: string
}

export function isDataReport(value: unknown): value is DataReportResult {
  return typeof value === 'object' && value !== null && (value as { kind?: string }).kind === 'data_report'
}

// A file attached to a chat message (agent_requests.attachments).
export interface Attachment {
  type: 'dataset'
  id: string
  name: string
  rows?: number
}

export function attachmentsOf(value: unknown): Attachment[] {
  if (!Array.isArray(value)) return []
  return value.filter(
    (a): a is Attachment =>
      typeof a === 'object' && a !== null && (a as Attachment).type === 'dataset' && typeof (a as Attachment).id === 'string',
  )
}

// An uploaded spreadsheet (datasets table, without its rows).
export interface DatasetSummary {
  id: string
  name: string
  filename: string
  columns: { name: string; type: string }[]
  row_count: number
  size_bytes: number
  created_at: string
  // Older rows have none of these (uploads).
  source?: 'upload' | 'google_sheets'
  source_url?: string | null
  source_tab?: string | null
  refreshed_at?: string | null
}
