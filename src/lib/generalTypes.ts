import type { AgentType } from './agentTypes'
import type { CrmResult } from './crm'
import type { Tables } from './database.types'

type AgentRequest = Tables<'agent_requests'>

type Route =
  | Extract<AgentType, 'lead_research' | 'sales_outreach' | 'data_reporting' | 'content_copy' | 'customer_support' | 'operations'>
  | 'crm'

// One agent a message is handed to. CRM work runs as a General turn.
export interface Handoff {
  agent: Route
  task: string
}

// Mirrors backend/agents/general/agent.py.
export interface GeneralResult {
  kind: 'general'
  reply: string
  route: 'none' | Route
  task: string
  // Every agent the message goes to, in order, when it needs more than one
  // (the first is route/task). Older results don't have it.
  steps?: Handoff[]
  // Present when the answer came from the user's CRM.
  crm?: CrmResult | null
}

export function isGeneralResult(value: unknown): value is GeneralResult {
  return typeof value === 'object' && value !== null && (value as { kind?: string }).kind === 'general'
}

// The agents a General turn hands its message to, in order.
export function handoffsOf(result: GeneralResult): Handoff[] {
  if (result.steps?.length) return result.steps
  return result.route === 'none' || !result.task ? [] : [{ agent: result.route, task: result.task }]
}

// The kind of chat turn that runs a handoff: CRM work goes back through
// General, which handles it inside its turn.
export function turnAgentOf(agent: Route): AgentType {
  return agent === 'crm' ? 'general' : agent
}

// A step went well enough for the next to build on it: it finished, and Lead
// Research found at least one lead.
export function stepSucceeded(turn: Pick<AgentRequest, 'agent_type' | 'status' | 'result'>): boolean {
  if (turn.status !== 'completed') return false
  if (turn.agent_type !== 'lead_research') return true
  const leads = (turn.result as { leads?: unknown } | null)?.leads
  return Array.isArray(leads) && leads.length > 0
}

export type PlanStepState = 'done' | 'running' | 'failed' | 'skipped' | 'up_next' | 'waiting' | 'not_run'

export interface PlanStep {
  handoff: Handoff
  state: PlanStepState
  // Why a skipped step didn't run.
  reason?: string
}

// How far a General turn's plan got, from the turns that follow it in the
// chat. Step turns come right after it, in order, with the step's task as
// their message. `active`: this page is running the plan right now.
export function planOf(
  thread: AgentRequest[],
  index: number,
  active = false,
): { steps: PlanStep[]; turnIds: string[]; next: number | null } | null {
  const general = thread[index]
  const result: unknown = general?.result
  if (!isGeneralResult(result) || general.status !== 'completed') return null
  const handoffs = handoffsOf(result)
  if (handoffs.length === 0) return null

  const turnIds: string[] = []
  const steps: PlanStep[] = []
  // An earlier step failed or found nothing, so the ones after it never run.
  let stopped: string | null = null
  for (const [i, handoff] of handoffs.entries()) {
    const turn = thread[index + 1 + i]
    const matches = turn && turn.agent_type === turnAgentOf(handoff.agent) && turn.prompt === handoff.task
    if (matches && turnIds.length === i) {
      turnIds.push(turn.id)
      const state: PlanStepState =
        turn.status === 'completed' ? 'done' : turn.status === 'failed' ? 'failed' : 'running'
      steps.push({ handoff, state })
      if (!stopped && state !== 'running' && !stepSucceeded(turn))
        stopped = state === 'done' ? 'Lead Research found no leads' : 'the step before didn’t finish'
      continue
    }
    steps.push(stopped ? { handoff, state: 'skipped', reason: stopped } : { handoff, state: 'not_run' })
  }

  // The first step that hasn't run can still start if everything before it
  // went well, nothing is running, and the chat hasn't moved on since.
  const first = steps.findIndex((s) => s.state === 'not_run')
  if (first !== -1 && active) {
    steps[first] = { ...steps[first], state: 'up_next' }
    return { steps, turnIds, next: null }
  }
  const atEnd = index + 1 + turnIds.length === thread.length
  const busy = thread.some((t) => t.status === 'in_progress' || t.status === 'queued')
  let next: number | null = null
  if (first !== -1 && atEnd && !busy) {
    steps[first] = { ...steps[first], state: 'waiting' }
    next = first
  }
  return { steps, turnIds, next }
}
