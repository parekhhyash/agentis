import { authedFetch, BackendApiError } from './backendApi'
import type { DatasetSummary } from './dataTypes'
import { supabase } from './supabase'

export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024
export const UPLOAD_ACCEPT =
  '.csv,.tsv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

const DATASET_FIELDS = 'id,name,filename,columns,row_count,size_bytes,created_at,source,source_url,source_tab,refreshed_at'

function readAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1] ?? '')
    reader.onerror = () => reject(new BackendApiError('The file could not be read.', 0))
    reader.readAsDataURL(file)
  })
}

// The backend parses the spreadsheet (types, dates, currency) and stores it.
export async function uploadDataset(file: File): Promise<DatasetSummary> {
  if (file.size > MAX_UPLOAD_BYTES) throw new BackendApiError('Files can be up to 5 MB.', 413)
  const content = await readAsBase64(file)
  return authedFetch<DatasetSummary>('/data/datasets', {
    method: 'POST',
    body: JSON.stringify({ filename: file.name, content_base64: content }),
  })
}

// One tab of a Google Sheet as a data file: the tab in the link, else the
// first. The backend reads it again when a report uses it.
export function addSheet(url: string): Promise<DatasetSummary> {
  return authedFetch<DatasetSummary>('/data/sheets', { method: 'POST', body: JSON.stringify({ url }) })
}

export function refreshSheet(id: string): Promise<DatasetSummary> {
  return authedFetch<DatasetSummary>(`/data/sheets/${id}/refresh`, { method: 'POST' })
}

// A new Google Sheet in the user's Drive with this table; returns its link.
export async function exportToSheets(table: {
  title: string
  tab?: string
  headers: string[]
  rows: (string | number | boolean | null)[][]
}): Promise<string> {
  return (await authedFetch<{ url: string }>('/integrations/google/sheets', { method: 'POST', body: JSON.stringify(table) })).url
}

export async function listDatasets(): Promise<DatasetSummary[]> {
  const { data } = await supabase.from('datasets').select(DATASET_FIELDS).order('created_at', { ascending: false })
  return (data ?? []) as unknown as DatasetSummary[]
}

export async function deleteDataset(id: string): Promise<boolean> {
  const { error } = await supabase.from('datasets').delete().eq('id', id)
  return !error
}
