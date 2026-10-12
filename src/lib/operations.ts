import { useCallback, useEffect, useState } from 'react'

import { authedFetch } from './backendApi'

// Mirrors backend/agents/operations/schemas.py and api/operations.py.

export type StepAgent = 'general' | 'lead_research' | 'sales_outreach' | 'data_reporting' | 'content_copy' | 'customer_support'

export interface TaskStep {
  agent: StepAgent
  prompt: string
}

export interface Schedule {
  kind: 'once' | 'daily' | 'weekly' | 'monthly'
  time: string
  days: string[]
  day_of_month: number | null
  date: string | null
  timezone: string
}

export interface RunSummary {
  id: string
  trigger: 'schedule' | 'manual'
  status: 'running' | 'completed' | 'failed' | 'partial'
  started_at: string
  finished_at: string | null
  error: string | null
  emailed: boolean
}

export interface ScheduledTask {
  id: string
  name: string
  status: 'active' | 'paused' | 'finished'
  status_reason: string | null
  schedule: Schedule
  schedule_text: string
  next_run_at: string | null
  last_run_at: string | null
  last_status: 'completed' | 'failed' | 'partial' | null
  last_error: string | null
  steps: TaskStep[]
  notify_email: boolean
  conversation_id: string | null
  running: boolean
  run_count: number
  recent_runs: RunSummary[]
}

export type ProposalAction = 'create' | 'update' | 'pause' | 'resume' | 'delete' | 'run_now'

export interface Proposal {
  id: string
  action: ProposalAction
  task_id: string | null
  name: string
  schedule: Schedule | null
  schedule_text: string
  next_runs: string[]
  steps: TaskStep[]
  notify_email: boolean
  changes: string[]
  warnings: string[]
  status: 'proposed' | 'applied' | 'discarded'
  decided_at: string | null
}

export interface OperationsResult {
  kind: 'operations'
  request: string
  reply: string
  proposals: Proposal[]
  tasks: ScheduledTask[]
  notes: string[]
}

export function isOperationsResult(value: unknown): value is OperationsResult {
  return typeof value === 'object' && value !== null && (value as { kind?: string }).kind === 'operations'
}

export const STEP_LABELS: Record<StepAgent, string> = {
  general: 'Manager',
  lead_research: 'Lead Research',
  sales_outreach: 'Sales & Outreach',
  data_reporting: 'Data & Reporting',
  content_copy: 'Content & Copy',
  customer_support: 'Customer Support',
}

// A run time in the task's own time zone: "Mon 13 Oct, 9:00 AM".
export function runTime(iso: string, timeZone?: string): string {
  const date = new Date(iso)
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: timeZone || undefined,
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }).formatToParts(date)
    const part = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
    return `${part('weekday')} ${part('day')} ${part('month')}, ${part('hour')}:${part('minute')} ${part('dayPeriod').toUpperCase()}`
  } catch {
    return date.toLocaleString()
  }
}

// "Asia/Kolkata" -> "Kolkata", for compact labels.
export function zoneLabel(timeZone: string): string {
  return timeZone.split('/').pop()?.replace(/_/g, ' ') ?? timeZone
}

export function decideProposal(
  requestId: string,
  proposalId: string,
  decision: 'confirm' | 'discard',
  notifyEmail?: boolean,
): Promise<{ proposal: Proposal; task: ScheduledTask | null }> {
  return authedFetch(`/operations/requests/${requestId}/proposals/${proposalId}`, {
    method: 'POST',
    body: JSON.stringify({ decision, notify_email: notifyEmail }),
  })
}

export function useScheduledTasks() {
  const [tasks, setTasks] = useState<ScheduledTask[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setTasks((await authedFetch<{ tasks: ScheduledTask[] }>('/operations/tasks')).tasks)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load your scheduled tasks')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    authedFetch<{ tasks: ScheduledTask[] }>('/operations/tasks')
      .then((data) => !cancelled && setTasks(data.tasks))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'Could not load your scheduled tasks'))
    return () => {
      cancelled = true
    }
  }, [])

  // Swaps in one task as the server returned it (or drops it when deleted).
  const replace = useCallback((id: string, task: ScheduledTask | null) => {
    setTasks((prev) => {
      if (!prev) return prev
      if (!task) return prev.filter((t) => t.id !== id)
      return prev.some((t) => t.id === id) ? prev.map((t) => (t.id === id ? { ...t, ...task, recent_runs: t.recent_runs } : t)) : [...prev, task]
    })
  }, [])

  async function change(id: string, patch: { status?: 'active' | 'paused'; notify_email?: boolean }) {
    replace(id, await authedFetch<ScheduledTask>(`/operations/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }))
  }

  async function remove(id: string) {
    await authedFetch(`/operations/tasks/${id}`, { method: 'DELETE' })
    replace(id, null)
  }

  async function runNow(id: string) {
    replace(id, await authedFetch<ScheduledTask>(`/operations/tasks/${id}/run`, { method: 'POST' }))
  }

  return { tasks, error, refresh, replace, change, remove, runNow }
}

export type ScheduledTasks = ReturnType<typeof useScheduledTasks>
