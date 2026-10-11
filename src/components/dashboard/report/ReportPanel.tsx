import { useState } from 'react'

import type { DataReportResult, ReportBlock } from '../../../lib/dataTypes'
import { blockTable, downloadCsv } from '../../../lib/reportFormat'
import SheetsExportButton from '../SheetsExportButton'
import { relativeTime } from '../../../lib/relativeTime'
import RichText from '../RichText'
import { BarList, DataTable, Donut, LineChart, StatTiles } from './ReportCharts'

function showing(block: ReportBlock): string | null {
  if (block.visual === 'kpi' || block.total <= block.rows.length) return null
  const other = block.rows[block.rows.length - 1]?.[0] === 'Other'
  return other
    ? `${block.rows.length - 1} largest of ${block.total}, the rest grouped as Other`
    : `Showing ${block.rows.length} of ${block.total}`
}

function Chart({ block }: { block: ReportBlock }) {
  if (block.visual === 'line') return <LineChart block={block} />
  if (block.visual === 'pie') return <Donut block={block} />
  if (block.visual === 'bar') return <BarList block={block} />
  return <DataTable block={block} />
}

function BlockCard({ block, sheetsConnected }: { block: ReportBlock; sheetsConnected: boolean }) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const [explain, setExplain] = useState(false)
  const isChart = block.visual !== 'table'
  const note = showing(block)

  return (
    <section className="rounded-xl border border-slate-200 bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="text-sm font-semibold text-slate-900">{block.title}</h4>
        {note && <span className="text-xs text-slate-500">{note}</span>}
      </div>

      {block.rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">No rows match this part of the report.</p>
      ) : view === 'table' || !isChart ? (
        <DataTable block={block} />
      ) : (
        <Chart block={block} />
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span>From {block.dataset}</span>
        <button type="button" onClick={() => setExplain((v) => !v)} className="font-medium hover:text-slate-800">
          {explain ? 'Hide calculation' : 'How it’s calculated'}
        </button>
        {isChart && block.rows.length > 0 && (
          <button type="button" onClick={() => setView((v) => (v === 'chart' ? 'table' : 'chart'))} className="font-medium hover:text-slate-800">
            {view === 'chart' ? 'Show table' : 'Show chart'}
          </button>
        )}
        {block.rows.length > 0 && (
          <button type="button" onClick={() => downloadCsv(block)} className="font-medium hover:text-slate-800">
            Download CSV
          </button>
        )}
        {block.rows.length > 0 && sheetsConnected && (
          <SheetsExportButton table={() => blockTable(block)} className="font-medium hover:text-slate-800" />
        )}
      </div>
      {explain && <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">{block.explanation}</p>}
    </section>
  )
}

// Consecutive headline-number blocks share one row of tiles.
function groupBlocks(blocks: ReportBlock[]): (ReportBlock | ReportBlock[])[] {
  const out: (ReportBlock | ReportBlock[])[] = []
  for (const block of blocks) {
    const last = out[out.length - 1]
    if (block.visual === 'kpi' && block.rows.length > 0) {
      if (Array.isArray(last)) last.push(block)
      else out.push([block])
    } else {
      out.push(block)
    }
  }
  return out
}

function Tiles({ blocks }: { blocks: ReportBlock[] }) {
  const [explain, setExplain] = useState(false)
  const tiles = blocks.flatMap((b) => b.columns.map((column, i) => ({ column, value: b.rows[0][i], explanation: b.explanation })))
  return (
    <div>
      <StatTiles tiles={tiles} />
      <button type="button" onClick={() => setExplain((v) => !v)} className="mt-2 text-xs font-medium text-slate-500 hover:text-slate-800">
        {explain ? 'Hide calculation' : 'How these are calculated'}
      </button>
      {explain && (
        <ul className="mt-2 space-y-1 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
          {blocks.map((b) => (
            <li key={b.id}>{b.explanation}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ReportPanel({ result, sheetsConnected = false }: { result: DataReportResult; sheetsConnected?: boolean }) {
  const uploads = result.datasets.filter((d) => d.kind === 'upload')
  const activity = result.datasets.filter((d) => d.kind === 'activity')

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-slate-900">{result.title}</h3>
        <div className="mt-2">
          <RichText text={result.summary} />
        </div>
      </div>

      {groupBlocks(result.blocks).map((item) =>
        Array.isArray(item) ? (
          <Tiles key={item[0].id} blocks={item} />
        ) : (
          <BlockCard key={item.id} block={item} sheetsConnected={sheetsConnected} />
        ),
      )}

      {result.notes.length > 0 && (
        <ul className="space-y-1 text-sm text-slate-600">
          {result.notes.map((note, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
              <span>{note}</span>
            </li>
          ))}
        </ul>
      )}

      {result.datasets.length > 0 && (
        <p className="text-xs text-slate-500">
          Based on{' '}
          {[
            ...activity.map((d) => `${d.name} (${d.rows.toLocaleString('en-US')})`),
            ...uploads.map((d) => `${d.name} (${d.rows.toLocaleString('en-US')} rows)`),
          ].join(', ')}
          {result.replies_checked_at && ` · replies checked in Gmail ${relativeTime(result.replies_checked_at)}`}
        </p>
      )}
    </div>
  )
}
