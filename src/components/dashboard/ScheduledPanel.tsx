import { useState } from 'react'

import { BackendApiError } from '../../lib/backendApi'
import { runTime, zoneLabel, type RunSummary, type ScheduledTask, type ScheduledTasks } from '../../lib/operations'
import { relativeTime } from '../../lib/relativeTime'
import { ChevronDownIcon, ClockIcon } from '../icons'
import { StepList, TaskStatusPill } from './ScheduledTaskParts'

const EXAMPLES = [
  "Every Monday at 9, report last week's emails, replies and meetings, and email it to me",
  'Every weekday at 10, check for replies to my outreach and draft responses',
  'On the 1st of every month, find 10 new leads like my best customers',
]

const RUN_STATUS: Record<RunSummary['status'], { label: string; dot: string }> = {
  running: { label: 'Running', dot: 'bg-sky-500 animate-pulse' },
  completed: { label: 'Done', dot: 'bg-emerald-500' },
  partial: { label: 'Partly done', dot: 'bg-amber-500' },
  failed: { label: 'Failed', dot: 'bg-red-500' },
}

function TaskCard({
  task,
  scheduled,
  onOpenChat,
  gmail,
}: {
  task: ScheduledTask
  scheduled: ScheduledTasks
  onOpenChat: (conversationId: string) => void
  // The connected Gmail address the summary goes from and to; null if none.
  gmail: string | null
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [details, setDetails] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const tz = task.schedule.timezone

  async function act(name: string, run: () => Promise<void>) {
    setBusy(name)
    setError(null)
    try {
      await run()
    } catch (err) {
      setError(err instanceof BackendApiError ? err.message : 'Something went wrong, try again.')
    } finally {
      setBusy(null)
    }
  }

  const last = task.last_status ? RUN_STATUS[task.last_status] : null
  const nextRun =
    task.status === 'active' && task.next_run_at
      ? runTime(task.next_run_at, tz)
      : task.status === 'paused'
        ? 'Paused'
        : 'No more runs'

  return (
    <li className="rounded-2xl border border-slate-200 bg-surface p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="min-w-0 font-semibold text-slate-900">{task.name}</h3>
        <TaskStatusPill task={task} />
      </div>
      <p className="mt-1 flex items-start gap-1.5 text-sm text-slate-600">
        <ClockIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-400" />
        <span>
          {task.schedule_text} <span className="text-slate-400">({zoneLabel(tz)} time)</span>
        </span>
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt className="text-xs text-slate-400">Next run</dt>
          <dd className="text-slate-700">{nextRun}</dd>
        </div>
        <div>
          <dt className="text-xs text-slate-400">Last run</dt>
          <dd className="flex items-center gap-1.5 text-slate-700">
            {last && task.last_run_at ? (
              <>
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${last.dot}`} />
                {last.label} &middot; {relativeTime(task.last_run_at)}
              </>
            ) : (
              'Not run yet'
            )}
          </dd>
        </div>
      </dl>

      {task.status_reason ? (
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">{task.status_reason}</p>
      ) : (
        task.last_status !== 'completed' &&
        task.last_error && <p className="mt-3 text-xs text-red-700">{task.last_error}</p>
      )}

      <button
        type="button"
        onClick={() => setDetails((v) => !v)}
        className="mt-3 flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-800"
      >
        <ChevronDownIcon className={`transition-transform ${details ? 'rotate-180' : ''}`} />
        {details ? 'Hide details' : `Steps (${task.steps.length}) and recent runs`}
      </button>
      {details && (
        <div className="mt-3 space-y-4">
          <StepList steps={task.steps} />
          {task.recent_runs.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-500">Recent runs</p>
              <ul className="mt-1.5 space-y-1">
                {task.recent_runs.map((run) => (
                  <li key={run.id} className="flex flex-wrap items-center gap-x-2 text-xs text-slate-600">
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${RUN_STATUS[run.status].dot}`} />
                    {RUN_STATUS[run.status].label}
                    <span className="text-slate-400">
                      {runTime(run.started_at, tz)}
                      {run.trigger === 'manual' ? ' · run by you' : ''}
                      {run.emailed ? ' · emailed' : ''}
                    </span>
                    {run.error && <span className="w-full pl-3.5 text-red-700">{run.error}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-3 border-t border-slate-100 pt-4">
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={task.notify_email}
            disabled={busy !== null}
            onChange={(e) => void act('email', () => scheduled.change(task.id, { notify_email: e.target.checked }))}
            className="h-4 w-4 rounded border-slate-300 accent-brand-blue"
          />
          Email me the results
          {task.notify_email && (
            <span className={`text-xs ${gmail ? 'text-slate-400' : 'text-amber-700'}`}>
              {gmail ? `to ${gmail}, from your Gmail` : 'connect Gmail on the Connect page to get them'}
            </span>
          )}
        </label>

        {confirmDelete ? (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <span className="text-sm text-slate-600">Delete this task? Its chat stays.</span>
            <button
              type="button"
              onClick={() => setConfirmDelete(false)}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-500 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => void act('delete', () => scheduled.remove(task.id))}
              className="rounded-full bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600/90 disabled:opacity-50"
            >
              {busy === 'delete' ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        ) : (
          <div className="ml-auto flex flex-wrap items-center gap-1">
            {task.conversation_id && (
              <button
                type="button"
                onClick={() => onOpenChat(task.conversation_id!)}
                className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
              >
                Open chat
              </button>
            )}
            <button
              type="button"
              disabled={busy !== null || task.running}
              onClick={() => void act('run', () => scheduled.runNow(task.id))}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            >
              {task.running ? 'Running…' : busy === 'run' ? 'Starting…' : 'Run now'}
            </button>
            {task.status !== 'finished' && (
              <button
                type="button"
                disabled={busy !== null}
                onClick={() =>
                  void act('status', () => scheduled.change(task.id, { status: task.status === 'active' ? 'paused' : 'active' }))
                }
                className="rounded-full px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
              >
                {task.status === 'active' ? 'Pause' : 'Resume'}
              </button>
            )}
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="rounded-full px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50"
            >
              Delete
            </button>
          </div>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
    </li>
  )
}

function Examples({ onAsk }: { onAsk: (prompt: string) => void }) {
  return (
    <ul className="mt-4 space-y-2">
      {EXAMPLES.map((example) => (
        <li key={example}>
          <button
            type="button"
            onClick={() => onAsk(example)}
            className="w-full rounded-xl border border-slate-200 bg-surface px-4 py-3 text-left text-sm text-slate-700 transition-colors hover:border-brand-blue/40 hover:bg-sky-50"
          >
            {example}
          </button>
        </li>
      ))}
    </ul>
  )
}

export default function ScheduledPanel({
  scheduled,
  onOpenChat,
  onAsk,
  gmail,
}: {
  scheduled: ScheduledTasks
  onOpenChat: (conversationId: string) => void
  onAsk: (prompt: string) => void
  // The connected Gmail address that "Email me the results" uses; null if none.
  gmail: string | null
}) {
  const { tasks, error } = scheduled

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="font-display text-3xl text-slate-900">Scheduled</h1>
      <p className="mt-2 text-slate-500">
        Tasks the Operations agent runs for you. Each run adds its results to the task&rsquo;s own chat, and any
        drafts still wait for your approval.
      </p>

      {error && <p className="mt-6 text-sm text-red-700">{error}</p>}

      {!tasks ? (
        !error && <p className="mt-8 text-sm text-slate-400">Loading…</p>
      ) : tasks.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-slate-300 p-6">
          <p className="font-semibold text-slate-900">Nothing scheduled yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Tell the Operations agent what to do and when, in your own words. For example:
          </p>
          <Examples onAsk={onAsk} />
        </div>
      ) : (
        <>
          <ul className="mt-8 space-y-4">
            {tasks.map((task) => (
              <TaskCard key={task.id} task={task} scheduled={scheduled} onOpenChat={onOpenChat} gmail={gmail} />
            ))}
          </ul>
          <div className="mt-10">
            <p className="font-semibold text-slate-900">Schedule something else</p>
            <p className="mt-1 text-sm text-slate-500">Pick one to start from, or ask the Operations agent in your own words.</p>
            <Examples onAsk={onAsk} />
          </div>
        </>
      )}
    </div>
  )
}
