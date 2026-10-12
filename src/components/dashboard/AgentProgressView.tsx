import { useEffect, useState } from 'react'

import { AGENT_NODE, AGENTS } from '../../lib/agentNetwork'
import type { AgentType } from '../../lib/agentTypes'
import type { AgentProgress } from '../../lib/salesAgentTypes'
import { LiveAgentNetwork } from '../agentNetwork'
import { ChevronDownIcon } from '../icons'

function useElapsedSeconds(startedAt: string | null): number {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (!startedAt) return
    const startMs = new Date(startedAt).getTime()

    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startMs) / 1000)))
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [startedAt])

  return elapsed
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

// Another agent's output this run is using, read from its progress steps
// (Sales & Outreach reports "Using 5 lead(s) from your research").
function handoffFor(agentType: AgentType, progress: AgentProgress | null): { from: number; carry: string } | null {
  if (agentType === 'data_reporting') {
    // "Reading 42 leads from Lead Research" / "Reading 18 emails from Sales & Outreach"
    const step = [...(progress?.steps ?? [])].reverse().find((s) => /^Reading \d+ (leads|emails) from/i.test(s.label))
    const match = step?.label.match(/^Reading (\d+) (leads|emails)/i)
    if (!match) return null
    const kind = match[2].toLowerCase()
    return { from: AGENT_NODE[kind === 'leads' ? 'lead_research' : 'sales_outreach'] ?? 0, carry: `${match[1]} ${kind}` }
  }
  if (agentType !== 'sales_outreach') return null
  const step = progress?.steps?.find((s) => /from your research/i.test(s.label))
  if (!step) return null
  const count = step.label.match(/(\d+)\s+lead/i)?.[1]
  return { from: AGENT_NODE.lead_research ?? 0, carry: count ? `${count} leads` : 'leads' }
}

export default function AgentProgressView({
  agentType,
  startedAt,
  progress,
}: {
  agentType: AgentType
  startedAt: string | null
  progress: AgentProgress | null
}) {
  const elapsed = useElapsedSeconds(startedAt)
  const steps = progress?.steps ?? []
  const [expanded, setExpanded] = useState(false)
  const node = AGENT_NODE[agentType] ?? null
  const handoff = handoffFor(agentType, progress)
  const label = node !== null ? AGENTS[node].label : 'Manager'

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
      <div className="w-full max-w-[17rem] shrink-0">
        <LiveAgentNetwork
          agent={node}
          status={
            handoff
              ? `${label} is using your ${handoff.carry.replace(/^\d+ /, '')}`
              : node === null
                ? 'Manager is thinking'
                : `${label} is working`
          }
          handoffFrom={handoff?.from}
          carry={handoff?.carry}
        />
      </div>
      <div className="min-w-0 flex-1 sm:pt-1">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <span className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-sky-500" />
          <span>{progress?.current_step ?? 'Working on it...'}</span>
          {startedAt && (
            <span className="ml-auto shrink-0 font-mono text-xs tabular-nums text-slate-400">
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>

        {steps.length > 0 && (
          <>
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 flex items-center gap-1 text-xs font-medium text-slate-400 transition-colors hover:text-slate-600"
            >
              <ChevronDownIcon className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
              {expanded ? 'Hide steps' : `Show ${steps.length} step${steps.length === 1 ? '' : 's'}`}
            </button>

            {expanded && (
              <ul className="mt-2 max-h-48 space-y-1.5 overflow-y-auto border-l border-slate-200 pl-3">
                {steps.map((step, i) => {
                  const isLast = i === steps.length - 1
                  return (
                    <li key={`${step.at}-${i}`} className="flex items-start gap-1.5 text-xs">
                      <span className="mt-0.5 shrink-0">
                        {isLast ? (
                          <span className="block h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />
                        ) : (
                          <span className="text-green-600">&#10003;</span>
                        )}
                      </span>
                      <span className={isLast ? 'font-medium text-slate-700' : 'text-slate-400'}>{step.label}</span>
                    </li>
                  )
                })}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  )
}
