import { useEffect, useRef, useState } from 'react'
import { Navigate, useLocation, useSearchParams } from 'react-router-dom'
import ChatConversation from '../components/dashboard/ChatConversation'
import ConversationSidebar from '../components/dashboard/ConversationSidebar'
import ConnectionsPanel from '../components/dashboard/ConnectionsPanel'
import OutreachSetupBar from '../components/dashboard/OutreachSetupBar'
import ProfileMenu from '../components/dashboard/ProfileMenu'
import ScheduledPanel from '../components/dashboard/ScheduledPanel'
import TaskComposer from '../components/dashboard/TaskComposer'
import { ClockIcon, CloseIcon, MenuIcon, PlugIcon, PlusIcon } from '../components/icons'
import ThemeToggle from '../components/ThemeToggle'
import {
  createAgentRequest,
  isPlanActive,
  runHandoffs,
  RUNNABLE_AGENTS,
  startAgentRun,
  stopAgentRun,
  subscribeToRuns,
  type AgentRunOptions,
} from '../lib/agentRuns'
import type { AgentType } from '../lib/agentTypes'
import { useAuth } from '../lib/AuthContext'
import { createConversation, type Conversation } from '../lib/conversations'
import type { Json, Tables } from '../lib/database.types'
import type { Attachment } from '../lib/dataTypes'
import { handoffsOf, isGeneralResult, planOf } from '../lib/generalTypes'
import { useSocialConnections } from '../lib/content'
import { useSupportConnections } from '../lib/support'
import { CRM_NAMES, useCrmConnections, type CrmProvider } from '../lib/crm'
import { useGoogleConnection } from '../lib/googleConnection'
import { useScheduledTasks } from '../lib/operations'
import { isOutreachResult, type OutreachAction } from '../lib/outreachTypes'
import { CLIENT_TIMEOUT_MESSAGE, STOPPED_BY_USER_MESSAGE } from '../lib/salesAgentApi'
import { supabase } from '../lib/supabase'
import { useProfile } from '../lib/useProfile'

type AgentRequest = Tables<'agent_requests'>

const CLIENT_SIDE_FAILURE_MESSAGES = new Set([CLIENT_TIMEOUT_MESSAGE, STOPPED_BY_USER_MESSAGE])

// A little past the backend's own real timeout (1200s) - the backend is the
// source of truth for how a run actually ended (see finalize_request in
// request_store.py), so a row this browser marked 'failed' on its own
// timeout is still worth re-checking until the backend has had its full
// window to write its own final answer.
const CLIENT_SIDE_FAILURE_GRACE_MS = 1_250_000

// What each Google part is for, shown after connecting it.
const GOOGLE_CONNECTED: Record<string, string> = {
  gmail: 'Gmail connected. Sales & Outreach can now draft and send email for you.',
  calendar: 'Google Calendar connected. Sales & Outreach can now book meetings with Meet links.',
  sheets: 'Google Sheets connected. Add a sheet under Data files, or export leads and report tables to Sheets.',
}

export default function DashboardPage() {
  const { user } = useAuth()
  const { profile, loading: loadingProfile } = useProfile()
  // All of the user's turns (requests), oldest first, and the chats they belong to.
  const [requests, setRequests] = useState<AgentRequest[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loadingRequests, setLoadingRequests] = useState(true)
  const [agentType, setAgentType] = useState<AgentType>('general')
  // Opens on a fresh chat; past chats are one click away in the sidebar. A
  // run started from the landing page's prompt box opens on that chat.
  const location = useLocation()
  const [selectedId, setSelectedId] = useState<string | null>(
    (location.state as { openConversationId?: string } | null)?.openConversationId ?? null,
  )
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [leadRequestId, setLeadRequestId] = useState<string | null>(null)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const [view, setView] = useState<'chat' | 'connect' | 'scheduled'>('chat')
  // Always checked: chats offer "Export to Google Sheets" when Sheets is connected.
  const google = useGoogleConnection(true)
  const crm = useCrmConnections()
  const social = useSocialConnections()
  const support = useSupportConnections()
  const scheduled = useScheduledTasks()

  // Back from Google's consent screen (see api/integrations.py's callback).
  const googleResult = searchParams.get('google')
  const returnMessage = searchParams.get('message')
  const [handledGoogleResult, setHandledGoogleResult] = useState<string | null>(null)
  const googlePart = searchParams.get('for') ?? 'gmail'
  if (googleResult && googleResult !== handledGoogleResult) {
    setHandledGoogleResult(googleResult)
    if (googlePart !== 'sheets') setAgentType('sales_outreach')
    setView('connect')
    setNotice(
      googleResult !== 'connected'
        ? { tone: 'error', text: returnMessage ?? 'Google could not be connected.' }
        : { tone: 'ok', text: GOOGLE_CONNECTED[googlePart] ?? GOOGLE_CONNECTED.gmail },
    )
  }
  // Back from a CRM's sign-in page (see api/crm.py's callback).
  const crmResult = searchParams.get('crm')
  const crmProvider = searchParams.get('provider') as CrmProvider | null
  const [handledCrmResult, setHandledCrmResult] = useState<string | null>(null)
  if (crmResult && `${crmResult}:${crmProvider}` !== handledCrmResult) {
    setHandledCrmResult(`${crmResult}:${crmProvider}`)
    setView('connect')
    const name = crmProvider && crmProvider in CRM_NAMES ? CRM_NAMES[crmProvider] : 'Your CRM'
    setNotice(
      crmResult === 'connected'
        ? { tone: 'ok', text: `${name} connected. Ask the Manager about your contacts, companies and deals, or to update them.` }
        : { tone: 'error', text: returnMessage ?? `${name} could not be connected.` },
    )
  }
  // Back from Zoho Desk's sign-in page (see api/support.py's callback).
  const supportResult = searchParams.get('support')
  const [handledSupportResult, setHandledSupportResult] = useState<string | null>(null)
  if (supportResult && supportResult !== handledSupportResult) {
    setHandledSupportResult(supportResult)
    setView('connect')
    setNotice(
      supportResult === 'connected'
        ? { tone: 'ok', text: 'Zoho Desk connected. Ask Customer Support to triage your open tickets and draft replies.' }
        : { tone: 'error', text: returnMessage ?? 'Zoho Desk could not be connected.' },
    )
  }
  // Back from LinkedIn's or X's sign-in page (see api/social.py's callback).
  const socialResult = searchParams.get('social')
  const socialProvider = searchParams.get('provider')
  const [handledSocialResult, setHandledSocialResult] = useState<string | null>(null)
  if (socialResult && `${socialResult}:${socialProvider}` !== handledSocialResult) {
    setHandledSocialResult(`${socialResult}:${socialProvider}`)
    setView('connect')
    const name = { x: 'X', notion: 'Notion', medium: 'Medium' }[socialProvider ?? ''] ?? 'LinkedIn'
    const done =
      socialProvider === 'notion'
        ? 'Notion connected. Content & Copy drafts now have a Save to Notion button.'
        : `${name} connected. Content & Copy drafts for ${name} now have a Post button.`
    setNotice(
      socialResult === 'connected'
        ? { tone: 'ok', text: done }
        : { tone: 'error', text: returnMessage ?? `${name} could not be connected.` },
    )
  }
  // A link to one chat, e.g. from a scheduled task's summary email.
  const chatParam = searchParams.get('chat')
  const [handledChatParam, setHandledChatParam] = useState<string | null>(null)
  if (chatParam && chatParam !== handledChatParam) {
    setHandledChatParam(chatParam)
    setSelectedId(chatParam)
    setView('chat')
  }
  useEffect(() => {
    if (googleResult || crmResult || socialResult || chatParam) setSearchParams({}, { replace: true })
  }, [googleResult, crmResult, socialResult, chatParam, setSearchParams])

  // The conversation scrolls; the composer below it doesn't. A visible
  // scrollbar (e.g. on Windows) narrows the scroll area and shifts its
  // centred column left of the composer's. Measure the scrollbar and give
  // the composer row the same gap so both columns line up exactly.
  const scrollRef = useRef<HTMLDivElement>(null)
  const [scrollbarWidth, setScrollbarWidth] = useState(0)

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const measure = () => setScrollbarWidth(el.offsetWidth - el.clientWidth)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!user) return

    Promise.all([
      supabase.from('agent_requests').select('*').order('created_at', { ascending: true }),
      supabase.from('conversations').select('*').order('updated_at', { ascending: false }),
    ]).then(([turns, chats]) => {
      setRequests(turns.data ?? [])
      setConversations(chats.data ?? [])
      setLoadingRequests(false)
    })
  }, [user])

  // Turns started by other runs (the Manager handing off) and their
  // progress, even when the run began before this page mounted.
  useEffect(
    () =>
      subscribeToRuns((event) => {
        if (event.type === 'spawn') {
          setRequests((prev) => (prev.some((r) => r.id === event.request.id) ? prev : [...prev, event.request]))
          if (event.request.conversation_id) touchConversation(event.request.conversation_id)
        } else {
          setRequests((prev) => prev.map((r) => (r.id === event.id ? { ...r, ...event.patch } : r)))
        }
      }),
    [],
  )

  const requestsRef = useRef<AgentRequest[]>(requests)
  useEffect(() => {
    requestsRef.current = requests
  }, [requests])

  // Scheduled tasks add turns from the server while the page is open: pick
  // up new ones (and the chats they moved to the top) every so often.
  const refreshScheduled = scheduled.refresh
  useEffect(() => {
    if (!user) return
    const since = new Date(Date.now() - 5 * 60_000).toISOString()
    const interval = setInterval(async () => {
      const { data } = await supabase
        .from('agent_requests')
        .select('*')
        .not('scheduled_task_id', 'is', null)
        .gte('created_at', since)
        .order('created_at', { ascending: true })
      const known = new Set(requestsRef.current.map((r) => r.id))
      const fresh = (data ?? []).filter((r) => !known.has(r.id))
      if (fresh.length === 0) return
      setRequests((prev) => [...prev, ...fresh.filter((r) => !prev.some((p) => p.id === r.id))])
      const chats = await supabase.from('conversations').select('*').order('updated_at', { ascending: false })
      if (chats.data) setConversations(chats.data)
      void refreshScheduled()
    }, 20_000)
    return () => clearInterval(interval)
  }, [user, refreshScheduled])

  // While a task runs, or the Scheduled page is open, keep its status fresh.
  const anyRunning = Boolean(scheduled.tasks?.some((t) => t.running))
  useEffect(() => {
    if (!anyRunning && view !== 'scheduled') return
    const interval = setInterval(() => void refreshScheduled(), anyRunning ? 10_000 : 30_000)
    return () => clearInterval(interval)
  }, [anyRunning, view, refreshScheduled])

  // The backend pushes live progress straight to Supabase as it runs (see
  // ProgressTracker in the Python service) - poll the in-progress rows so
  // the chat view can show it updating instead of just a static spinner.
  //
  // Also keep polling a row this browser itself just marked 'failed' on a
  // client-side timeout/stop: the backend may still be running (its own
  // timeout is longer than the frontend's on purpose - see
  // salesAgentApi.ts) and can correct that guess later via finalize_request
  // once it actually finishes. Without this, a run that times out on the
  // client but succeeds on the backend gets stuck showing "cancelled"
  // forever, even though real results are sitting in Supabase.
  useEffect(() => {
    const interval = setInterval(async () => {
      const watchIds = requestsRef.current
        .filter((r) => {
          if (r.status === 'in_progress') return true
          if (r.status === 'failed' && r.error && CLIENT_SIDE_FAILURE_MESSAGES.has(r.error)) {
            const startedAt = r.started_at ? new Date(r.started_at).getTime() : null
            return startedAt !== null && Date.now() - startedAt < CLIENT_SIDE_FAILURE_GRACE_MS
          }
          return false
        })
        .map((r) => r.id)
      if (watchIds.length === 0) return

      const { data } = await supabase.from('agent_requests').select('*').in('id', watchIds)
      if (!data) return
      setRequests((prev) => prev.map((r) => data.find((d) => d.id === r.id) ?? r))
    }, 2000)

    return () => clearInterval(interval)
  }, [])

  // Keep the newest message in view when a chat opens or gets a new turn.
  const openTurns = selectedId ? requests.filter((r) => r.conversation_id === selectedId) : []
  const threadLength = openTurns.length
  const lastStatus = openTurns[threadLength - 1]?.status
  useEffect(() => {
    const el = scrollRef.current
    if (!el || threadLength === 0) return
    // After the browser lays out the new turn (it grows once it starts working).
    const frame = requestAnimationFrame(() => el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' }))
    return () => cancelAnimationFrame(frame)
  }, [selectedId, threadLength, lastStatus])

  if (!loadingProfile && profile && !profile.onboarding_completed) {
    return <Navigate to="/setup-company" replace />
  }

  function updateRequest(id: string, patch: Partial<AgentRequest>) {
    setRequests((prev) => prev.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  }

  // Moves a chat to the top of the list, as the database trigger does.
  function touchConversation(id: string) {
    setConversations((prev) => {
      const chat = prev.find((c) => c.id === id)
      if (!chat) return prev
      return [{ ...chat, updated_at: new Date().toISOString() }, ...prev.filter((c) => c.id !== id)]
    })
  }

  async function handleSubmit(
    prompt: string,
    attachments: Attachment[] = [],
    agent: AgentType = agentType,
    intoChat: string | null | undefined = undefined,
  ) {
    if (!user) return

    // A message goes into the open chat; with none open it starts a new one.
    let conversationId = intoChat !== undefined ? intoChat : view === 'chat' ? selectedId : null
    if (!conversationId) {
      const chat = await createConversation(user.id, prompt)
      if (!chat) return
      setConversations((prev) => [chat, ...prev])
      conversationId = chat.id
    }

    const data = await createAgentRequest(user.id, agent, prompt, conversationId, attachments)
    if (!data) return
    setRequests((prev) => [...prev, data])
    touchConversation(conversationId)
    setSelectedId(conversationId)
    setView('chat')

    // Agents without a backend yet just sit in the queue. Runs are
    // fire-and-forget: status updates flow back via updateRequest.
    void startAgentRun(
      data,
      { ...runOptions(), leadRequestId: agent === 'sales_outreach' ? leadRequestId : null },
      (patch) => updateRequest(data.id, patch),
    )
  }

  function runOptions(): AgentRunOptions {
    return {
      companyContext: {
        company_name: profile?.company_name,
        company_website: profile?.company_website,
        industry: profile?.industry,
        target_audience_location: profile?.target_audience_location,
        company_description: profile?.company_description,
      },
      senderName: profile?.full_name,
    }
  }

  function mergeOutreachAction(requestId: string, action: OutreachAction) {
    setRequests((prev) =>
      prev.map((r) => {
        const result: unknown = r.result
        if (r.id !== requestId || !isOutreachResult(result)) return r
        const actions = result.actions.map((a) => (a.id === action.id ? action : a))
        return { ...r, result: { ...result, actions } as unknown as Json }
      }),
    )
  }

  const leadRuns = requests
    .filter((r) => r.agent_type === 'lead_research' && r.status === 'completed')
    .reverse()
    .slice(0, 10)
  const outreachBlocked = agentType === 'sales_outreach' && !google.status?.connected

  function selectRequest(id: string | null) {
    setSelectedId(id)
    setView('chat')
    setSidebarOpen(false)
  }

  function openConnect() {
    setSelectedId(null)
    setView('connect')
    setSidebarOpen(false)
  }

  function openScheduled() {
    setSelectedId(null)
    setView('scheduled')
    setSidebarOpen(false)
    void scheduled.refresh()
  }

  // A chat a scheduled task writes into may have been created after this
  // page loaded; fetch the chat list again if it's not known yet.
  async function openChat(conversationId: string) {
    if (!conversations.some((c) => c.id === conversationId)) {
      const [turns, chats] = await Promise.all([
        supabase.from('agent_requests').select('*').eq('conversation_id', conversationId).order('created_at', { ascending: true }),
        supabase.from('conversations').select('*').order('updated_at', { ascending: false }),
      ])
      if (chats.data) setConversations(chats.data)
      if (turns.data?.length) {
        setRequests((prev) => [...prev, ...turns.data.filter((t) => !prev.some((r) => r.id === t.id))])
      }
    }
    selectRequest(conversationId)
  }

  const scheduledChatIds = new Set((scheduled.tasks ?? []).map((t) => t.conversation_id).filter((id): id is string => Boolean(id)))
  const activeTaskCount = (scheduled.tasks ?? []).filter((t) => t.status === 'active').length

  const noticeBanner = notice && (
    <div
      className={`flex items-start gap-3 rounded-xl px-4 py-3 text-sm ${
        notice.tone === 'ok' ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
      }`}
    >
      <p className="flex-1">{notice.text}</p>
      <button type="button" aria-label="Dismiss" onClick={() => setNotice(null)} className="shrink-0 opacity-70 hover:opacity-100">
        <CloseIcon />
      </button>
    </div>
  )

  const firstName = profile?.full_name.split(' ')[0]
  const thread = selectedId ? requests.filter((r) => r.conversation_id === selectedId) : []
  const runningTurn = [...thread].reverse().find((r) => r.status === 'in_progress' || r.status === 'queued')
  const latestTurn = (conversationId: string) => {
    for (let i = requests.length - 1; i >= 0; i--) {
      if (requests[i].conversation_id === conversationId) return requests[i]
    }
    return undefined
  }
  // General's plans in this chat (the agents each message went to, in order)
  // and the turns that ran them, which show as hand-offs, not user messages.
  const plans = new Map<string, NonNullable<ReturnType<typeof planOf>>>()
  const handoffSteps = new Map<string, { step: number; total: number }>()
  thread.forEach((turn, index) => {
    const plan = planOf(thread, index, isPlanActive(turn.id))
    if (!plan) return
    plans.set(turn.id, plan)
    plan.turnIds.forEach((id, i) => handoffSteps.set(id, { step: i + 1, total: plan.steps.length }))
  })

  function continuePlan(turn: AgentRequest, from: number) {
    const result: unknown = turn.result
    // Already running (a quick second click, say).
    if (!isGeneralResult(result) || isPlanActive(turn.id)) return
    void runHandoffs(turn, handoffsOf(result), from, runOptions())
  }

  return (
    <div className="relative flex h-[calc(100vh-var(--banner-h))] overflow-hidden bg-slate-50">
      {sidebarOpen && (
        <div
          className="absolute inset-0 z-10 bg-black/40 sm:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`absolute inset-y-0 left-0 z-20 flex w-72 shrink-0 flex-col border-r border-slate-200 bg-surface transition-transform duration-200 ease-in-out sm:static sm:z-auto sm:translate-x-0 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between gap-2 p-3">
          <span className="font-display text-lg text-slate-900">Agentis</span>
          <ThemeToggle className="ml-auto hidden p-2 text-slate-500 hover:bg-slate-100 sm:block" />
          <button
            type="button"
            aria-label="Close sidebar"
            onClick={() => setSidebarOpen(false)}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 sm:hidden"
          >
            <CloseIcon />
          </button>
        </div>

        <div className="px-3 pb-2">
          <button
            type="button"
            onClick={() => selectRequest(null)}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
          >
            <PlusIcon className="text-slate-500" />
            New chat
          </button>
          <button
            type="button"
            onClick={openConnect}
            className={`mt-0.5 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              view === 'connect' ? 'bg-slate-100 text-slate-900' : 'text-slate-700 hover:bg-slate-100'
            }`}
          >
            <PlugIcon className="text-slate-500" />
            Connect
          </button>
          <button
            type="button"
            onClick={openScheduled}
            className={`mt-0.5 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              view === 'scheduled' ? 'bg-slate-100 text-slate-900' : 'text-slate-700 hover:bg-slate-100'
            }`}
          >
            <ClockIcon className="text-slate-500" />
            Scheduled
            {activeTaskCount > 0 && <span className="ml-auto text-xs font-normal text-slate-400">{activeTaskCount}</span>}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-2">
          <ConversationSidebar
            conversations={conversations}
            latestTurn={latestTurn}
            loading={loadingRequests}
            selectedId={view === 'chat' ? selectedId : null}
            onSelect={selectRequest}
            scheduledIds={scheduledChatIds}
          />
        </div>

        <ProfileMenu
          fullName={profile?.full_name ?? 'Account'}
          companyName={profile?.company_name ?? null}
        />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-slate-100 p-3 sm:hidden">
          <button
            type="button"
            aria-label="Open sidebar"
            onClick={() => setSidebarOpen(true)}
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
          >
            <MenuIcon />
          </button>
          <span className="font-display text-lg text-slate-900">Agentis</span>
          <ThemeToggle className="ml-auto p-2 text-slate-500 hover:bg-slate-100" />
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto [scrollbar-gutter:stable]">
          {view === 'connect' ? (
            <ConnectionsPanel google={google} crm={crm} social={social} support={support} notice={noticeBanner} />
          ) : view === 'scheduled' ? (
            <ScheduledPanel
              scheduled={scheduled}
              gmail={google.status?.connected ? google.status.email : null}
              onOpenChat={(id) => void openChat(id)}
              onAsk={(prompt) => {
                setSelectedId(null)
                setView('chat')
                setAgentType('operations')
                void handleSubmit(prompt, [], 'operations', null)
              }}
            />
          ) : thread.length > 0 ? (
            <div className="mx-auto max-w-3xl space-y-8 px-6 py-8">
              {thread.map((turn) => (
                <ChatConversation
                  key={turn.id}
                  request={turn}
                  handedOff={handoffSteps.has(turn.id)}
                  handoffStep={handoffSteps.get(turn.id)}
                  plan={plans.get(turn.id)}
                  onContinuePlan={(from) => continuePlan(turn, from)}
                  onOutreachActionChange={(action) => mergeOutreachAction(turn.id, action)}
                  onResultChange={(result) => updateRequest(turn.id, { result: result as Json })}
                  crms={crm.connected}
                  social={social}
                  onOpenConnect={openConnect}
                  scheduled={scheduled}
                  onOpenChat={(id) => void openChat(id)}
                  onOpenScheduled={openScheduled}
                  sheetsConnected={Boolean(google.status?.sheets)}
                  senderName={profile?.full_name}
                  onAddLeadsToCrm={(name, count) =>
                    void handleSubmit(
                      `Add the ${count} lead${count === 1 ? '' : 's'} from my last research to ${name}: create each company and its contacts with their emails, and skip any that are already in ${name}.`,
                      [],
                      'general',
                    )
                  }
                />
              ))}
            </div>
          ) : (
            <div className="mx-auto flex h-full max-w-3xl flex-col items-center justify-center px-6 text-center">
              <h1 className="font-display text-3xl text-slate-900">
                {firstName ? `Welcome back, ${firstName}` : 'Welcome back'}
              </h1>
              <p className="mt-2 text-slate-500">
                Ask the Manager anything, from questions to plans. It answers, or hands the
                task to the right agent. Attach a CSV or Excel file to ask about your numbers,
                or ask Operations to put any of it on a schedule.
              </p>
            </div>
          )}
        </div>

        <div style={{ paddingRight: scrollbarWidth }} className={view === 'chat' ? '' : 'hidden'}>
          <div className="mx-auto w-full max-w-3xl px-6 pb-6">
            {noticeBanner && <div className="mb-3">{noticeBanner}</div>}
            {agentType === 'sales_outreach' && (
              <OutreachSetupBar
                status={google.status}
                error={google.error}
                busy={google.busy}
                onConnect={(part) => google.connect(part)}
                onDisconnect={() => google.disconnect('gmail')}
                leadRuns={leadRuns}
                leadRequestId={leadRequestId}
                onLeadRequestChange={setLeadRequestId}
              />
            )}
            <TaskComposer
              blocked={outreachBlocked}
              runnableAgents={RUNNABLE_AGENTS}
              agentType={agentType}
              onAgentTypeChange={setAgentType}
              onSubmit={handleSubmit}
              isRunning={Boolean(runningTurn)}
              onStop={() => runningTurn && stopAgentRun(runningTurn.id)}
            />
          </div>
        </div>
      </main>
    </div>
  )
}
