import type { Cell, ReportBlock, ReportColumn } from './dataTypes'

const CURRENCIES = new Set(['₹', '$', '€', '£', '¥'])
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function trimmed(value: number, digits: number): string {
  return value.toFixed(digits).replace(/\.0+$|(\.\d*?)0+$/, '$1')
}

function compact(value: number, rupees: boolean): string {
  const abs = Math.abs(value)
  if (rupees) {
    if (abs >= 1e7) return `${trimmed(value / 1e7, 2)}Cr`
    if (abs >= 1e5) return `${trimmed(value / 1e5, 2)}L`
  } else {
    if (abs >= 1e9) return `${trimmed(value / 1e9, 1)}B`
    if (abs >= 1e6) return `${trimmed(value / 1e6, 1)}M`
  }
  if (abs >= 1e4) return `${trimmed(value / 1e3, 1)}K`
  return value.toLocaleString(rupees ? 'en-IN' : 'en-US', { maximumFractionDigits: abs >= 100 ? 0 : 2 })
}

function dateLabel(value: string, withYear: boolean): string {
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m) return value
  if (!d) return `${MONTHS[m - 1]} ${y}`
  return withYear ? `${d} ${MONTHS[m - 1]} ${y}` : `${d} ${MONTHS[m - 1]}`
}

export function formatNumber(value: number, unit?: string | null, short = false): string {
  const rupees = unit === '₹'
  let text: string
  if (unit === '%') text = trimmed(value, 1)
  else if (short) text = compact(value, rupees)
  else text = value.toLocaleString(rupees ? 'en-IN' : 'en-US', { maximumFractionDigits: 2 })
  if (unit === '%') return `${text}%`
  if (unit && CURRENCIES.has(unit)) return value < 0 ? `-${unit}${text.replace('-', '')}` : `${unit}${text}`
  return unit ? `${text} ${unit}` : text
}

// One cell, formatted for its column. `short` compacts big numbers (tiles, axes).
export function formatCell(value: Cell, column: ReportColumn, short = false): string {
  if (value === null || value === undefined || value === '') return 'n/a'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number') return formatNumber(value, column.unit, short)
  if ((column.type === 'date' || column.type === 'month') && /^\d{4}-\d{2}(-\d{2})?$/.test(value)) {
    return dateLabel(value, !short)
  }
  return value
}

// Clean round ticks from 0 (or the minimum, if negative) to just past the max.
export function niceTicks(min: number, max: number, count = 4): number[] {
  const low = Math.min(0, min)
  const high = max > low ? max : low + 1
  const rough = (high - low) / count
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? rough
  const ticks: number[] = []
  for (let t = Math.floor(low / step) * step; t < high + step * 0.999; t += step) ticks.push(Number(t.toPrecision(12)))
  return ticks
}

function csvCell(value: Cell): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function blockToCsv(block: ReportBlock): string {
  const header = block.columns.map((c) => csvCell(c.unit ? `${c.name} (${c.unit})` : c.name)).join(',')
  return [header, ...block.rows.map((row) => row.map(csvCell).join(','))].join('\n')
}

// A report table for a new Google Sheet (numbers stay numbers).
export function blockTable(block: ReportBlock) {
  return {
    title: block.title.slice(0, 200) || 'Report',
    tab: block.title.replace(/[[\]*?:/\\]/g, ' ').slice(0, 90) || 'Report',
    headers: block.columns.map((c) => (c.unit ? `${c.name} (${c.unit})` : c.name)),
    rows: block.rows.map((row) => row.map((v) => (v === undefined ? null : v))),
  }
}

export function downloadCsv(block: ReportBlock) {
  const blob = new Blob(['﻿' + blockToCsv(block)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${block.title.replace(/[^\w\- ]+/g, '').trim() || 'report'}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
