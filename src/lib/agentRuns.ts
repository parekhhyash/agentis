// Shared "create a request, then fire its agent" logic - used by both the
// dashboard composer and the landing page's Hero prompt box, since a
// logged-in visitor can now kick off a real run straight from Hero before
// ever mounting DashboardPage.
//
// The abort-controller registry is a module-level singleton (not a
// component-local useRef) specifically so a run started from one mounted
// component (Hero, about to unmount on navigation) can still be stopped
// later from another (DashboardPage, mounted fresh after that navigation).

import type { AgentType } from './agentTypes'
import { authedFetch, BackendApiError } from './backendApi'
import type { Json, Tables } from './database.types'
import { attachmentsOf, type Attachment, type DataReportResult } from './dataTypes'
import { handoffsOf, stepSucceeded, turnAgentOf, type GeneralResult, type Handoff } from './generalTypes'
import { runOutreach } from './outreachApi'
import {
  cancelLeadsGeneration,
  generateLeads,
  SalesAgentApiError,
  STOPPED_BY_USER_MESSAGE,
  type CompanyContext,
} from './salesAgentApi'
import { supabase } from './supabase'

type AgentRequest = Tables<'agent_requests'>

const abortControllers = new Map<string, AbortController>()

// General turns whose steps this page is running now, so the chat doesn't
// offer to continue a plan that is already moving.
const activePlans = new Set<string>()

export function isPlanActive(generalId: string): boolean {
  return activePlans.has(generalId)
}

// Runs can start other runs (the Manager handing a task to a
// specialist), possibly after the component that started them unmounted, so
// the dashboard listens here for new requests and their status changes.
type RunEvent =
  | { type: 'spawn'; request: AgentRequest }
  | { type: 'update'; id: string; patch: Partial<AgentRequest> }
const runListeners = new Set<(event: RunEvent) => void>()

export function subscribeToRuns(listener: (event: RunEvent) => void): () => void {
  runListeners.add(listener)
  return () => runListeners.delete(listener)
}

function emit(event: RunEvent) {
  runListeners.forEach((listener) => listener(event))
}

export async function createAgentRequest(
  userId: string,
  agentType: AgentType,
  prompt: string,
  conversationId: string,
  attachments: Attachment[] = [],
): Promise<AgentRequest | null> {
  const { data, error } = await supabase
    .from('agent_requests')
    .insert({
      user_id: userId,
      agent_type: agentType,
      prompt,
      conversation_id: conversationId,
      attachments: attachments.length ? (attachments as unknown as Json) : null,
    })
    .select()
    .single()

  return error || !data ? null : data
}

// Fire-and-forget: a real run takes minutes, so callers shouldn't await
// this before moving on. Status updates are written to Supabase directly
// (the backend also does this server-side - see request_store.py - so a
// caller doesn't strictly need `onUpdate`, but it lets an already-mounted
// list view like DashboardPage reflect the change instantly instead of
// waiting for its next poll).
export async function runLeadResearchAgent(
  requestId: string,
  prompt: string,
  companyContext: CompanyContext | undefined,
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  const startedAt = new Date().toISOString()
  await supabase
    .from('agent_requests')
    .update({ status: 'in_progress', started_at: startedAt })
    .eq('id', requestId)
  onUpdate?.({ status: 'in_progress', started_at: startedAt })

  const controller = new AbortController()
  abortControllers.set(requestId, controller)

  try {
    const result = await generateLeads(prompt, requestId, companyContext, controller.signal)
    await supabase
      .from('agent_requests')
      .update({ status: 'completed', result: result as unknown as Json })
      .eq('id', requestId)
    onUpdate?.({ status: 'completed', result: result as unknown as Json })
  } catch (err) {
    const message =
      err instanceof SalesAgentApiError ? err.message : 'Unexpected error running the agent.'
    await supabase
      .from('agent_requests')
      .update({ status: 'failed', error: message })
      .eq('id', requestId)
    onUpdate?.({ status: 'failed', error: message })
  } finally {
    abortControllers.delete(requestId)
  }
}

// Runs one backend agent call for a request, keeping its row (and any
// listening view) in step: in progress, then completed with the result, or
// failed with a message.
async function runBackendAgent(
  requestId: string,
  call: (signal: AbortSignal) => Promise<unknown>,
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  const startedAt = new Date().toISOString()
  await supabase
    .from('agent_requests')
    .update({ status: 'in_progress', started_at: startedAt })
    .eq('id', requestId)
  onUpdate?.({ status: 'in_progress', started_at: startedAt })

  const controller = new AbortController()
  abortControllers.set(requestId, controller)

  try {
    const result = await call(controller.signal)
    await supabase
      .from('agent_requests')
      .update({ status: 'completed', result: result as unknown as Json, error: null })
      .eq('id', requestId)
    onUpdate?.({ status: 'completed', result: result as unknown as Json, error: null })
  } catch (err) {
    const message =
      err instanceof DOMException && err.name === 'AbortError'
        ? STOPPED_BY_USER_MESSAGE
        : err instanceof BackendApiError
          ? err.message
          : 'Unexpected error running the agent.'
    await supabase.from('agent_requests').update({ status: 'failed', error: message }).eq('id', requestId)
    onUpdate?.({ status: 'failed', error: message })
  } finally {
    abortControllers.delete(requestId)
  }
}

// Sales & Outreach: drafts emails, replies and meetings for review. Nothing
// is sent until the user approves a draft in OutreachResultsPanel.
export function runSalesOutreachAgent(
  requestId: string,
  prompt: string,
  options: { companyContext?: CompanyContext; senderName?: string | null; leadRequestId?: string | null },
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  return runBackendAgent(requestId, (signal) => runOutreach({ prompt, requestId, ...options }, signal), onUpdate)
}

// Data & Reporting: answers with numbers, charts and tables from the user's
// Agentis activity and the files attached to the message.
export function runDataReportingAgent(
  requestId: string,
  prompt: string,
  options: { companyContext?: CompanyContext },
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  return runBackendAgent(
    requestId,
    (signal) =>
      authedFetch<DataReportResult>('/data/run', {
        method: 'POST',
        signal,
        body: JSON.stringify({
          prompt,
          request_id: requestId,
          company_context: options.companyContext,
          time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }),
      }),
    onUpdate,
  )
}

// Content & Copy: scored drafts for each requested piece; posting happens
// later, from the results, when the user confirms.
export function runContentAgent(
  requestId: string,
  prompt: string,
  options: { companyContext?: CompanyContext },
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  return runBackendAgent(
    requestId,
    (signal) =>
      authedFetch<unknown>('/content/run', {
        method: 'POST',
        signal,
        body: JSON.stringify({ prompt, request_id: requestId, company_context: options.companyContext }),
      }),
    onUpdate,
  )
}

// Customer Support: triages tickets and drafts replies or notes; each one is
// sent from the results only when the user approves it.
export function runSupportAgent(
  requestId: string,
  prompt: string,
  options: { companyContext?: CompanyContext; senderName?: string | null },
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  return runBackendAgent(
    requestId,
    (signal) =>
      authedFetch<unknown>('/support/run', {
        method: 'POST',
        signal,
        body: JSON.stringify({
          prompt,
          request_id: requestId,
          company_context: options.companyContext,
          user_name: options.senderName,
        }),
      }),
    onUpdate,
  )
}

// Operations: proposes scheduled tasks (or changes to them) for the user to
// confirm in the chat; the backend runs them on their schedule.
export function runOperationsAgent(
  requestId: string,
  prompt: string,
  options: { companyContext?: CompanyContext; senderName?: string | null },
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  return runBackendAgent(
    requestId,
    (signal) =>
      authedFetch<unknown>('/operations/run', {
        method: 'POST',
        signal,
        body: JSON.stringify({
          prompt,
          request_id: requestId,
          company_context: options.companyContext,
          time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          user_name: options.senderName,
        }),
      }),
    onUpdate,
  )
}

export interface AgentRunOptions {
  companyContext?: CompanyContext
  senderName?: string | null
  leadRequestId?: string | null
}

// General: answers in the chat, or hands the message to a specialist agent,
// which then runs as the next turn of the same conversation.
export async function runGeneralAgent(
  request: AgentRequest,
  options: AgentRunOptions,
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> {
  const update = (patch: Partial<AgentRequest>) => {
    onUpdate?.(patch)
    emit({ type: 'update', id: request.id, patch })
  }
  const startedAt = new Date().toISOString()
  await supabase.from('agent_requests').update({ status: 'in_progress', started_at: startedAt }).eq('id', request.id)
  update({ status: 'in_progress', started_at: startedAt })

  const controller = new AbortController()
  abortControllers.set(request.id, controller)
  let result: GeneralResult
  try {
    result = await authedFetch<GeneralResult>('/general/run', {
      method: 'POST',
      signal: controller.signal,
      body: JSON.stringify({
        prompt: request.prompt,
        request_id: request.id,
        company_context: options.companyContext,
        user_name: options.senderName,
      }),
    })
  } catch (err) {
    const message =
      err instanceof DOMException && err.name === 'AbortError'
        ? STOPPED_BY_USER_MESSAGE
        : err instanceof BackendApiError
          ? err.message
          : 'Unexpected error running the agent.'
    await supabase.from('agent_requests').update({ status: 'failed', error: message }).eq('id', request.id)
    update({ status: 'failed', error: message })
    return
  } finally {
    abortControllers.delete(request.id)
  }

  const handoffs = handoffsOf(result)
  if (handoffs.length && request.conversation_id) activePlans.add(request.id)
  await supabase
    .from('agent_requests')
    .update({ status: 'completed', result: result as unknown as Json, error: null })
    .eq('id', request.id)
  update({ status: 'completed', result: result as unknown as Json, error: null })

  await runHandoffs(request, handoffs, 0, options)
}

// Runs a General turn's handoffs from step `from` on, each as the next turn
// of the chat and only once the one before it succeeded. Each agent reads the
// chat, so it sees what the earlier steps found (Sales & Outreach picks up
// the leads on the backend).
export async function runHandoffs(
  general: AgentRequest,
  handoffs: Handoff[],
  from: number,
  options: AgentRunOptions,
): Promise<void> {
  if (!general.conversation_id) return
  activePlans.add(general.id)
  try {
    for (const [i, handoff] of handoffs.entries()) {
      if (i < from) continue
      // Files attached to the message go to the first step, and to any step
      // that works on data.
      const files = i === 0 || handoff.agent === 'data_reporting' ? attachmentsOf(general.attachments) : []
      const next = await createAgentRequest(general.user_id, turnAgentOf(handoff.agent), handoff.task, general.conversation_id, files)
      if (!next) return
      emit({ type: 'spawn', request: next })
      let latest: AgentRequest = next
      await startAgentRun(next, { ...options, leadRequestId: null }, (patch) => {
        latest = { ...latest, ...patch }
        emit({ type: 'update', id: next.id, patch })
      })
      if (!stepSucceeded(latest)) return
    }
  } finally {
    activePlans.delete(general.id)
    // Lets the chat re-check the plan now that nothing is running it.
    emit({ type: 'update', id: general.id, patch: {} })
  }
}

// Agents with a real backend behind them; the rest stay queued for now.
export const RUNNABLE_AGENTS: AgentType[] = [
  'general',
  'lead_research',
  'sales_outreach',
  'data_reporting',
  'content_copy',
  'customer_support',
  'operations',
]

export function startAgentRun(
  request: AgentRequest,
  options: AgentRunOptions,
  onUpdate?: (patch: Partial<AgentRequest>) => void,
): Promise<void> | undefined {
  if (request.agent_type === 'lead_research') {
    return runLeadResearchAgent(request.id, request.prompt, options.companyContext, onUpdate)
  }
  if (request.agent_type === 'sales_outreach') {
    return runSalesOutreachAgent(request.id, request.prompt, options, onUpdate)
  }
  if (request.agent_type === 'content_copy') {
    return runContentAgent(request.id, request.prompt, options, onUpdate)
  }
  if (request.agent_type === 'data_reporting') {
    return runDataReportingAgent(request.id, request.prompt, options, onUpdate)
  }
  if (request.agent_type === 'operations') {
    return runOperationsAgent(request.id, request.prompt, options, onUpdate)
  }
  if (request.agent_type === 'customer_support') {
    return runSupportAgent(request.id, request.prompt, options, onUpdate)
  }
  if (request.agent_type === 'general') {
    return runGeneralAgent(request, options, onUpdate)
  }
  return undefined
}

export function stopAgentRun(requestId: string) {
  abortControllers.get(requestId)?.abort()
  void cancelLeadsGeneration(requestId)
}
