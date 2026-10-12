import { AGENT_TYPES } from '../../lib/agentTypes'
import { handoffsOf, type GeneralResult, type Handoff, type PlanStep, type PlanStepState } from '../../lib/generalTypes'
import CrmResultPanel from './CrmResultPanel'
import RichText from './RichText'

const general = AGENT_TYPES.find((a) => a.value === 'general')!

// CRM steps run through General (it works in the CRM inside its own turn).
function agentOf(handoff: Handoff) {
  if (handoff.agent === 'crm') return { label: 'CRM', icon: general.icon }
  return AGENT_TYPES.find((a) => a.value === handoff.agent) ?? general
}

const STATES: Record<PlanStepState, { text: string; tone: string }> = {
  done: { text: 'Done', tone: 'text-emerald-700' },
  running: { text: 'Working…', tone: 'text-sky-600' },
  failed: { text: 'Didn’t finish', tone: 'text-red-700' },
  skipped: { text: 'Skipped', tone: 'text-slate-400' },
  up_next: { text: 'Up next', tone: 'text-slate-500' },
  waiting: { text: 'Not started', tone: 'text-slate-500' },
  not_run: { text: 'Not started', tone: 'text-slate-400' },
}

export default function GeneralReply({
  result,
  requestId,
  onResultChange,
  plan,
  onContinue,
}: {
  result: GeneralResult
  requestId: string
  onResultChange?: (result: GeneralResult) => void
  // The agents the message went to and how far they got, with the step that
  // can still start (after a reload, say) when nothing else is running.
  plan?: { steps: PlanStep[]; next: number | null } | null
  onContinue?: (from: number) => void
}) {
  // Without plan details, just show where the message went.
  const steps: PlanStep[] = plan?.steps ?? handoffsOf(result).slice(0, 1).map((handoff) => ({ handoff, state: 'not_run' }))
  const next = plan?.next ?? null
  return (
    <div>
      <RichText text={result.reply} />
      {result.crm && (
        <CrmResultPanel requestId={requestId} crm={result.crm} onChange={(crm) => onResultChange?.({ ...result, crm })} />
      )}
      {steps.length === 1 && <HandedTo handoff={steps[0].handoff} />}
      {steps.length > 1 && (
        <ol className="mt-3 space-y-2">
          {steps.map((step, i) => {
            const agent = agentOf(step.handoff)
            const state = STATES[step.state]
            return (
              <li key={i} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
                <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 py-1 pr-3 pl-1 font-medium text-slate-600">
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-blue text-white">
                    <agent.icon className="h-3 w-3" />
                  </span>
                  {i + 1}. {agent.label}
                </span>
                <span className={state.tone}>
                  {state.text}
                  {step.reason && `: ${step.reason}`}
                </span>
              </li>
            )
          })}
        </ol>
      )}
      {next !== null && onContinue && (
        <button
          type="button"
          onClick={() => onContinue(next)}
          className="mt-3 rounded-full bg-brand-blue px-3.5 py-1.5 text-sm font-semibold text-white transition-colors hover:bg-brand-blue/90"
        >
          {steps.length > 1 ? `Continue with step ${next + 1}: ${agentOf(steps[next].handoff).label}` : `Hand to ${agentOf(steps[next].handoff).label}`}
        </button>
      )}
    </div>
  )
}

function HandedTo({ handoff }: { handoff: Handoff }) {
  const agent = agentOf(handoff)
  return (
    <div className="mt-3 inline-flex items-center gap-2 rounded-full bg-slate-100 py-1 pr-3 pl-1 text-xs font-medium text-slate-600">
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-blue text-white">
        <agent.icon className="h-3 w-3" />
      </span>
      Handed to {agent.label}
    </div>
  )
}
