import { useState } from 'react'

import googleSheetsLogo from '../../assets/connectors/google-sheets.svg'
import { BackendApiError } from '../../lib/backendApi'
import { exportToSheets } from '../../lib/dataApi'

type Cell = string | number | boolean | null

// Creates a new Google Sheet in the user's Drive from a table, then links to
// it (opening it right away would be blocked as a pop-up after the wait).
export default function SheetsExportButton({
  table,
  className,
}: {
  table: () => { title: string; tab?: string; headers: string[]; rows: Cell[][] }
  className: string
}) {
  const [state, setState] = useState<{ busy?: boolean; url?: string; error?: string }>({})

  if (state.url)
    return (
      <a href={state.url} target="_blank" rel="noreferrer" className={`${className} inline-flex items-center gap-1.5 text-emerald-700`}>
        <img src={googleSheetsLogo} alt="" className="h-3.5 w-3.5" />
        Open the sheet
      </a>
    )
  return (
    <button
      type="button"
      disabled={state.busy}
      title={state.error}
      onClick={async () => {
        setState({ busy: true })
        try {
          setState({ url: await exportToSheets(table()) })
        } catch (err) {
          setState({ error: err instanceof BackendApiError ? err.message : 'Export to Google Sheets failed' })
        }
      }}
      className={`${className} inline-flex items-center gap-1.5 disabled:opacity-50 ${state.error ? 'text-red-700' : ''}`}
    >
      <img src={googleSheetsLogo} alt="" className="h-3.5 w-3.5" />
      {state.busy ? 'Creating the sheet…' : state.error ? 'Export failed, try again' : 'Export to Google Sheets'}
    </button>
  )
}
