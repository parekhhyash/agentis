import { AGENT_LABELS } from '../../lib/agentTypes'
import type { Tables } from '../../lib/database.types'
import { isContentResult, type useSocialConnections } from '../../lib/content'
import type { CrmProviderStatus } from '../../lib/crm'
import { attachmentsOf, isDataReport } from '../../lib/dataTypes'
import { relativeTime } from '../../lib/relativeTime'
import { isGeneralResult, type PlanStep } from '../../lib/generalTypes'
import { isOperationsResult, type ScheduledTasks } from '../../lib/operations'
import { isOutreachResult, type OutreachAction } from '../../lib/outreachTypes'
import type { AgentProgress, AnyLeadResult } from '../../lib/salesAgentTypes'
import AgentProgressView from './AgentProgressView'
import ContentResultPanel from './ContentResultPanel'
import GeneralReply from './GeneralReply'
import LeadResultsPanel from './LeadResultsPanel'
import OperationsResultPanel from './OperationsResultPanel'
import OutreachResultsPanel from './OutreachResultsPanel'
import ReportPanel from './report/ReportPanel'
import { ClockIcon, SheetIcon } from '../icons'

type AgentRequest = Tables<'agent_requests'>

// One turn of a chat: the message and the agent's answer. A turn the General
// agent handed off, or a scheduled task started, shows that instead of a
// user message.
export default function ChatConversation({
  request,
  handedOff = false,
  handoffStep,
  plan,
  onContinuePlan,
  onOutreachActionChange,
  onResultChange,
  crms = [],
  onAddLeadsToCrm,
  social,
  onOpenConnect,
  scheduled,
  onOpenChat,
  onOpenScheduled,
  sheetsConnected = false,
}: {
  request: AgentRequest
  handedOff?: boolean
  // This turn's place in General's plan, when it had more than one step.
  handoffStep?: { step: number; total: number }
  // For a General turn: the agents it handed the message to and how far they got.
  plan?: { steps: PlanStep[]; next: number | null } | null
  onContinuePlan?: (from: number) => void
  onOutreachActionChange?: (action: OutreachAction) => void
  onResultChange?: (result: unknown) => void
  // Connected CRMs, for "Add to HubSpot" on lead results.
  crms?: CrmProviderStatus[]
  onAddLeadsToCrm?: (crmName: string, count: number) => void
  social?: ReturnType<typeof useSocialConnections>
  onOpenConnect?: () => void
  scheduled?: ScheduledTasks
  onOpenChat?: (conversationId: string) => void
  onOpenScheduled?: () => void
  // Google Sheets is connected: lead and report tables offer "Export to Google Sheets".
  sheetsConnected?: boolean
}) {
  const files = attachmentsOf(request.attachments)
  const fileChips = files.length > 0 && (
    <ul className={`flex flex-wrap gap-1.5 ${handedOff ? 'mt-2' : 'mb-2 justify-end'}`}>
      {files.map((file) => (
        <li
          key={file.id}
          className={`flex max-w-full items-center gap-1.5 rounded-md px-2 py-1 text-xs ${
            handedOff ? 'bg-slate-100 text-slate-600' : 'bg-white/15 text-white'
          }`}
        >
          <SheetIcon className="h-3 w-3 shrink-0" />
          <span className="truncate">{file.name}</span>
        </li>
      ))}
    </ul>
  )

  return (
    <div className="space-y-6">
      {handedOff ? (
        <div className="flex items-start gap-3 rounded-xl border border-dashed border-slate-300 px-4 py-3">
          <span className="mt-0.5 shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap text-slate-600">
            Manager &rarr; {AGENT_LABELS[request.agent_type]}
            {handoffStep && handoffStep.total > 1 && (
              <span className="font-normal text-slate-500">
                {' '}
                &middot; step {handoffStep.step} of {handoffStep.total}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <p className="text-sm text-slate-600">{request.prompt}</p>
            {fileChips}
          </div>
        </div>
      ) : request.scheduled_task_id ? (
        <div className="flex items-start gap-3 rounded-xl border border-dashed border-slate-300 px-4 py-3">
          <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap text-slate-600">
            <ClockIcon className="h-3 w-3" />
            Scheduled &rarr; {AGENT_LABELS[request.agent_type]}
          </span>
          <div className="min-w-0">
            <p className="text-sm text-slate-600">{request.prompt}</p>
            <p className="mt-1 text-xs text-slate-400">{relativeTime(request.created_at)}</p>
          </div>
        </div>
      ) : (
        <div className="flex justify-end">
          <div className="max-w-xl rounded-2xl rounded-tr-sm bg-sky-600 px-4 py-3 text-white">
            {fileChips}
            <p className="text-[15px] whitespace-pre-line">{request.prompt}</p>
            <p className="mt-1.5 text-xs text-sky-100">
              {AGENT_LABELS[request.agent_type]} &middot; {relativeTime(request.created_at)}
            </p>
          </div>
        </div>
      )}

      <div className="flex justify-start">
        <div
          className={`w-full rounded-2xl rounded-tl-sm border border-slate-200 bg-surface px-4 py-3 ${
            request.status === 'completed' ? '' : 'max-w-2xl'
          }`}
        >
          {request.status === 'queued' && <p className="text-sm text-slate-500">Queued&hellip;</p>}

          {request.status === 'in_progress' && (
            <AgentProgressView
              agentType={request.agent_type}
              startedAt={request.started_at ?? request.created_at}
              progress={request.progress as unknown as AgentProgress | null}
            />
          )}

          {request.status === 'completed' &&
            request.result != null &&
            (isGeneralResult(request.result) ? (
              <GeneralReply
                result={request.result}
                requestId={request.id}
                onResultChange={(result) => onResultChange?.(result)}
                plan={plan}
                onContinue={onContinuePlan}
              />
            ) : isContentResult(request.result) && social ? (
              <ContentResultPanel
                requestId={request.id}
                result={request.result}
                social={social}
                onResultChange={(result) => onResultChange?.(result)}
                onOpenConnect={() => onOpenConnect?.()}
              />
            ) : isOperationsResult(request.result) && scheduled ? (
              <OperationsResultPanel
                requestId={request.id}
                result={request.result}
                scheduled={scheduled}
                onResultChange={(result) => onResultChange?.(result)}
                onOpenChat={(id) => onOpenChat?.(id)}
                onOpenScheduled={() => onOpenScheduled?.()}
              />
            ) : isDataReport(request.result) ? (
              <ReportPanel result={request.result} sheetsConnected={sheetsConnected} />
            ) : isOutreachResult(request.result) ? (
              <OutreachResultsPanel
                key={request.id}
                requestId={request.id}
                result={request.result}
                onActionChange={(action) => onOutreachActionChange?.(action)}
                onResultChange={(result) => onResultChange?.(result)}
              />
            ) : (
              <LeadResultsPanel
                result={request.result as unknown as AnyLeadResult}
                crms={crms.map((c) => c.name)}
                onAddToCrm={onAddLeadsToCrm}
                sheetsConnected={sheetsConnected}
              />
            ))}

          {request.status === 'failed' && (
            <p className="text-sm text-red-700">{request.error ?? 'Something went wrong.'}</p>
          )}
        </div>
      </div>
    </div>
  )
}
