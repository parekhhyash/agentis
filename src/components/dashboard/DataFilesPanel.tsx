import { useEffect, useRef, useState } from 'react'

import googleSheetsLogo from '../../assets/connectors/google-sheets.svg'
import { BackendApiError } from '../../lib/backendApi'
import { addSheet, deleteDataset, listDatasets, refreshSheet, UPLOAD_ACCEPT, uploadDataset } from '../../lib/dataApi'
import type { DatasetSummary } from '../../lib/dataTypes'
import { relativeTime } from '../../lib/relativeTime'
import { SheetIcon } from '../icons'

const TYPE_LABELS: Record<string, string> = { number: 'number', date: 'date', boolean: 'yes/no', text: 'text' }

function size(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

// Spreadsheets uploaded, or linked from Google Sheets, for Data & Reporting:
// the agent can report on any of them; a file attached to a message is the
// one that message is about. A linked sheet is read again when it's used.
export default function DataFilesPanel({
  sheets,
}: {
  sheets: { configured: boolean; connected: boolean; busy: boolean; connect: () => void }
}) {
  const [files, setFiles] = useState<DatasetSummary[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const [linking, setLinking] = useState(false)
  const [link, setLink] = useState('')
  const [refreshing, setRefreshing] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function linkSheet() {
    setBusy(true)
    setError(null)
    try {
      const dataset = await addSheet(link.trim())
      setFiles((prev) => [dataset, ...(prev ?? []).filter((f) => f.id !== dataset.id)])
      setLink('')
      setLinking(false)
    } catch (err) {
      setError(err instanceof BackendApiError ? err.message : 'That sheet could not be added.')
    } finally {
      setBusy(false)
    }
  }

  async function refresh(id: string) {
    setRefreshing(id)
    setError(null)
    try {
      const dataset = await refreshSheet(id)
      setFiles((prev) => (prev ?? []).map((f) => (f.id === id ? dataset : f)))
    } catch (err) {
      setError(err instanceof BackendApiError ? err.message : 'That sheet could not be read.')
    } finally {
      setRefreshing(null)
    }
  }

  useEffect(() => {
    listDatasets().then(setFiles)
  }, [])

  async function upload(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const dataset = await uploadDataset(file)
      setFiles((prev) => [dataset, ...(prev ?? [])])
    } catch (err) {
      setError(err instanceof BackendApiError ? err.message : 'Upload failed.')
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: string) {
    setConfirming(null)
    if (await deleteDataset(id)) setFiles((prev) => (prev ?? []).filter((f) => f.id !== id))
    else setError('That file could not be deleted. Try again.')
  }

  return (
    <section className="mt-12">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Data files</h2>
          <p className="mt-1 text-sm text-slate-500">
            CSV or Excel files, or Google Sheets, for Data &amp; Reporting. You can also attach one to a message.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={inputRef}
            type="file"
            accept={UPLOAD_ACCEPT}
            className="hidden"
            onChange={(e) => {
              void upload(e.target.files?.[0])
              e.target.value = ''
            }}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={busy}
            className="rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
          >
            {busy && !linking ? 'Reading file…' : 'Upload a file'}
          </button>
          {sheets.configured && (
            <button
              type="button"
              onClick={() => (sheets.connected ? setLinking((v) => !v) : sheets.connect())}
              disabled={busy || sheets.busy}
              title={sheets.connected ? undefined : 'Connect Google Sheets first'}
              className="flex items-center gap-1.5 rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-50"
            >
              <img src={googleSheetsLogo} alt="" className="h-4 w-4" />
              {sheets.connected ? 'Add a Google Sheet' : 'Connect Google Sheets'}
            </button>
          )}
        </div>
      </div>

      {linking && (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void linkSheet()
          }}
          className="mt-3 rounded-2xl border border-slate-200 bg-surface p-4"
        >
          <label htmlFor="sheet-link" className="block text-xs text-slate-500">
            Link to the sheet, opened on the tab you want (the first tab if the link has none)
          </label>
          <div className="mt-1.5 flex gap-2">
            <input
              id="sheet-link"
              type="url"
              required
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="https://docs.google.com/spreadsheets/d/…/edit#gid=0"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={busy || !link.trim()}
              className="shrink-0 rounded-full bg-brand-blue px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90 disabled:opacity-50"
            >
              {busy ? 'Reading…' : 'Add'}
            </button>
          </div>
        </form>
      )}

      {error && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-surface">
        {files === null ? (
          <p className="px-5 py-4 text-sm text-slate-400">Loading…</p>
        ) : files.length === 0 ? (
          <p className="px-5 py-6 text-sm text-slate-500">
            No files yet. Upload or link a sales, orders or expenses sheet and ask things like &ldquo;revenue by
            month&rdquo; or &ldquo;which product sells most&rdquo;.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {files.map((file) => (
              <li key={file.id} className="px-5 py-3">
                <div className="flex items-center gap-3">
                  {file.source === 'google_sheets' ? (
                    <img src={googleSheetsLogo} alt="Google Sheet" className="h-4 w-4 shrink-0" />
                  ) : (
                    <SheetIcon className="shrink-0 text-slate-400" />
                  )}
                  <button
                    type="button"
                    onClick={() => setOpen((id) => (id === file.id ? null : file.id))}
                    className="min-w-0 flex-1 text-left"
                  >
                    <p className="truncate text-sm font-medium text-slate-800">{file.filename}</p>
                    <p className="text-xs text-slate-500">
                      {file.row_count.toLocaleString('en-US')} rows · {file.columns.length} columns ·{' '}
                      {file.source === 'google_sheets'
                        ? `read ${relativeTime(file.refreshed_at ?? file.created_at)}, again when used`
                        : `${size(file.size_bytes)} · ${relativeTime(file.created_at)}`}
                    </p>
                  </button>
                  {file.source === 'google_sheets' && confirming !== file.id && (
                    <span className="flex shrink-0 items-center">
                      {file.source_url && (
                        <a
                          href={file.source_url}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded-full px-3 py-1 text-sm text-slate-500 hover:bg-slate-100"
                        >
                          Open
                        </a>
                      )}
                      <button
                        type="button"
                        onClick={() => void refresh(file.id)}
                        disabled={refreshing === file.id || !sheets.connected}
                        className="rounded-full px-3 py-1 text-sm text-slate-500 hover:bg-slate-100 disabled:opacity-50"
                      >
                        {refreshing === file.id ? 'Reading…' : 'Refresh'}
                      </button>
                    </span>
                  )}
                  {confirming === file.id ? (
                    <span className="flex shrink-0 items-center gap-1">
                      <button type="button" onClick={() => void remove(file.id)} className="rounded-full px-3 py-1 text-sm font-medium text-red-600 hover:bg-red-50">
                        Delete
                      </button>
                      <button type="button" onClick={() => setConfirming(null)} className="rounded-full px-3 py-1 text-sm text-slate-500 hover:bg-slate-100">
                        Keep
                      </button>
                    </span>
                  ) : (
                    <button type="button" onClick={() => setConfirming(file.id)} className="shrink-0 rounded-full px-3 py-1 text-sm text-slate-500 hover:bg-slate-100">
                      Delete
                    </button>
                  )}
                </div>
                {open === file.id && (
                  <ul className="mt-2 flex flex-wrap gap-1.5 pl-7">
                    {file.columns.map((c) => (
                      <li key={c.name} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                        {c.name} <span className="text-slate-400">{TYPE_LABELS[c.type] ?? c.type}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
