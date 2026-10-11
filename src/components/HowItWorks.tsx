import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'

import AgentCluster from './AgentCluster'
import { AGENTS, arcPath, HUB, NODES, ORBIT, STAGE_H, STAGE_W } from '../lib/agentNetwork'
import { AgentBadge, AgentWork, CheckIcon, Stage } from './agentNetwork'

// The three cards play one story together: a request is typed (01), routed
// to the matching agent (02), and its finished work is approved (03). Then
// the next story starts.

type Story = {
  chip: string
  prompt: string
  agent: number
  // What the agent is doing while it works, shown under the hub.
  work: string
  // Some jobs take two agents: the first passes its output to the second.
  handoff?: { to: number; carry: string; work: string }
  title: string
  rows: { mark: string; name: string; meta: string; tile: string }[]
}

const STORIES: Story[] = [
  {
    chip: 'Find leads',
    prompt: 'Find 20 D2C skincare brands in India and draft an intro for each',
    agent: 0,
    work: 'finding brands',
    handoff: { to: 1, carry: '20 leads', work: 'drafting intros' },
    title: '20 intros drafted',
    rows: [
      { mark: 'M', name: 'Mamaearth', meta: 'Strong fit · intro ready', tile: 'bg-brand-pink text-ink' },
      { mark: 'P', name: 'Plum Goodness', meta: 'Strong fit · intro ready', tile: 'bg-brand-sky text-white' },
      { mark: 'D', name: 'Dot & Key', meta: 'Possible · intro ready', tile: 'bg-brand-yellow text-ink' },
    ],
  },
  {
    chip: 'Write posts',
    prompt: 'Write three launch posts for our new summer collection',
    agent: 4,
    work: 'writing posts',
    handoff: { to: 5, carry: '3 posts', work: 'scheduling' },
    title: '3 posts drafted',
    rows: [
      { mark: 'IG', name: 'Instagram carousel', meta: '5 slides with captions', tile: 'bg-brand-orchid text-white' },
      { mark: 'in', name: 'LinkedIn post', meta: 'Launch announcement', tile: 'bg-brand-blue text-white' },
      { mark: 'X', name: 'Teaser thread', meta: '4 posts, scheduled Friday', tile: 'bg-brand-violet text-white' },
    ],
  },
  {
    chip: 'Answer tickets',
    prompt: "Reply to today's refund tickets and flag anything urgent",
    agent: 2,
    work: 'answering tickets',
    title: '18 tickets handled',
    rows: [
      { mark: '#', name: 'Refund issued', meta: 'Ticket 4821 · replied in 2 min', tile: 'bg-brand-sky text-white' },
      { mark: '#', name: 'Order delayed', meta: 'Ticket 4822 · sent tracking', tile: 'bg-brand-sky text-white' },
      { mark: '!', name: 'Damaged item', meta: 'Ticket 4825 · flagged for you', tile: 'bg-brand-pink text-ink' },
    ],
  },
]

// Story timeline, in ms from the start of each cycle.
const TYPE_START = 300
const TYPE_END = 2600
const SEND = 2800
const ROUTE_START = 3200
const ARRIVE = 4100
const HANDOFF = 4900
const HANDOFF_ARRIVE = 5700
const ROWS = [5800, 6200, 6600]
const CURSOR = 7100
const CLICK = 7700
const SHIPPED = 7850
const CYCLE = 9800
const TICK = 40

type Frame = { story: number; t: number }

// Advances the shared clock only while the cards are on screen. With reduced
// motion it stays on the finished state of the first story.
function useStoryClock(ref: RefObject<HTMLElement | null>): Frame {
  const reduced = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [elapsed, setElapsed] = useState(reduced ? CYCLE - 1 : 0)

  useEffect(() => {
    if (reduced) return
    const el = ref.current
    if (!el) return
    let visible = false
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
    })
    observer.observe(el)
    const timer = window.setInterval(() => {
      if (visible) setElapsed((e) => e + TICK)
    }, TICK)
    return () => {
      observer.disconnect()
      window.clearInterval(timer)
    }
  }, [ref, reduced])

  return { story: Math.floor(elapsed / CYCLE) % STORIES.length, t: elapsed % CYCLE }
}

// Visuals are laid out on a fixed 320 x 288 canvas and scaled to the card, so
// they look the same in the narrow three-column tablet layout and on desktop.
// 01: the request types itself out, the right agent is picked up, and it's sent.
function PromptVisual({ story, t }: Frame) {
  const s = STORIES[story]
  const progress = Math.min(1, Math.max(0, (t - TYPE_START) / (TYPE_END - TYPE_START)))
  const typed = s.prompt.slice(0, Math.round(s.prompt.length * progress))
  const detected = progress > 0.45
  const sent = t >= SEND
  const pressing = sent && t < SEND + 220

  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center px-5">
      <div className="flex gap-1.5">
        {STORIES.map((x, i) => (
          <span
            key={x.chip}
            className={`rounded-full px-2.5 py-1 text-[10px] font-semibold transition-colors duration-500 ${
              i === story ? AGENTS[x.agent].tile : 'bg-surface text-slate-500 ring-1 ring-slate-200'
            }`}
          >
            {x.chip}
          </span>
        ))}
      </div>

      <div className="mt-3 w-full rounded-2xl bg-surface p-4 shadow-lg ring-1 shadow-slate-900/5 ring-slate-200">
        <p className="h-[60px] text-[13px] leading-5 text-slate-700">
          {typed}
          {!sent && <span className="ml-0.5 inline-block h-4 w-px animate-pulse bg-brand-blue align-middle" />}
        </p>
        <div className="mt-3 flex items-center justify-between">
          <span className="relative h-7 flex-1">
            <span
              className={`absolute inset-y-0 left-0 inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-400 transition-opacity duration-300 ${
                detected ? 'opacity-0' : 'opacity-100'
              }`}
            >
              <span className="flex gap-0.5">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="h-1 w-1 animate-bounce rounded-full bg-slate-400"
                    style={{ animationDelay: `${d * 120}ms` }}
                  />
                ))}
              </span>
              Picking an agent
            </span>
            <span
              className={`absolute inset-y-0 left-0 inline-flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pr-2.5 pl-1 text-[11px] font-semibold text-slate-700 transition duration-300 ${
                detected ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
              }`}
            >
              <AgentBadge agent={s.agent} className="h-5 w-5" />
              {AGENTS[s.agent].label}
            </span>
          </span>
          <span className="relative flex h-8 w-8 items-center justify-center">
            {progress === 1 && !sent && (
              <span className="absolute inset-0 animate-ping rounded-full bg-brand-blue/40" />
            )}
            <span
              className={`relative flex h-8 w-8 items-center justify-center rounded-full bg-brand-blue text-white transition-transform duration-150 ${
                pressing ? 'scale-90' : 'scale-100'
              }`}
            >
              {sent ? (
                <CheckIcon className="h-3.5 w-3.5" />
              ) : (
                <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </span>
          </span>
        </div>
      </div>

      <span
        className={`mt-3 inline-flex items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-[11px] font-semibold text-slate-700 shadow-sm ring-1 ring-slate-200 transition duration-300 ${
          sent ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0'
        }`}
      >
        <CheckIcon className="h-3 w-3 text-brand-blue" />
        Sent to Agentis
      </span>
    </div>
  )
}

// 02: the hub hands the task to one of the agents around it.
function RoutingVisual({ story, t }: Frame) {
  const s = STORIES[story]
  const first = s.agent
  const second = s.handoff?.to
  const routing = t >= ROUTE_START && t < ARRIVE
  const arrived = t >= ARRIVE
  const handingOff = second !== undefined && t >= HANDOFF && t < HANDOFF_ARRIVE
  const secondWorking = second !== undefined && t >= HANDOFF_ARRIVE
  const firstWorking = arrived && !handingOff && !secondWorking
  const packet = t >= ROUTE_START + 150 ? NODES[first] : HUB
  const passed = second !== undefined && t >= HANDOFF + 150
  const linked = second !== undefined && t >= HANDOFF

  const status = !arrived
    ? routing
      ? 'Routing the task'
      : 'Waiting for a task'
    : handingOff && s.handoff
      ? `Passing ${s.handoff.carry} to ${AGENTS[s.handoff.to].label}`
      : secondWorking && s.handoff
        ? `${AGENTS[s.handoff.to].label} is ${s.handoff.work}`
        : `${AGENTS[first].label} is ${s.work}`
  const statusAgent = secondWorking && second !== undefined ? second : first

  return (
    <div className="absolute inset-0">
      <svg viewBox={`0 0 ${STAGE_W} ${STAGE_H}`} className="absolute inset-0 h-full w-full">
        <circle
          cx={HUB.x}
          cy={HUB.y}
          r={ORBIT}
          fill="none"
          strokeWidth="1.5"
          strokeDasharray="2 7"
          strokeLinecap="round"
          className="origin-center animate-[spin_40s_linear_infinite] stroke-slate-300 [transform-box:fill-box] motion-reduce:animate-none"
        />
        {NODES.map((n, i) => {
          const active = i === first && (routing || arrived)
          return (
            <line
              key={i}
              x1={HUB.x}
              y1={HUB.y}
              x2={n.x}
              y2={n.y}
              strokeLinecap="round"
              className={
                active
                  ? `${AGENTS[i].line} animate-dash-flow stroke-current motion-reduce:animate-none`
                  : 'stroke-slate-300'
              }
              strokeWidth={active ? 2.5 : 1.5}
              strokeDasharray={active ? '6 6' : '2 5'}
            />
          )
        })}
        {/* Agents talking to each other: the ring between the two comes alive. */}
        {second !== undefined && (
          <path
            d={arcPath(first, second)}
            fill="none"
            strokeLinecap="round"
            strokeWidth="2.5"
            strokeDasharray="6 6"
            className={`${AGENTS[second].line} animate-dash-flow stroke-current transition-opacity duration-500 motion-reduce:animate-none`}
            style={{ opacity: linked ? 1 : 0 }}
          />
        )}
      </svg>

      {/* The task travelling from the hub to its agent. */}
      <span
        className={`absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-4 ring-surface ${AGENTS[first].tile}`}
        style={{
          left: packet.x,
          top: packet.y,
          opacity: routing ? 1 : 0,
          transition: 'left 0.8s cubic-bezier(0.65, 0, 0.35, 1), top 0.8s cubic-bezier(0.65, 0, 0.35, 1), opacity 0.2s',
        }}
      />

      {firstWorking && <AgentWork agent={first} />}
      {secondWorking && second !== undefined && <AgentWork agent={second} />}

      {NODES.map((n, i) => {
        const { icon: Icon, tile } = AGENTS[i]
        const isFirst = i === first && arrived
        const isSecond = i === second && linked
        const busy = (i === first && firstWorking) || (i === second && (secondWorking || handingOff))
        const done = i === first && secondWorking
        return (
          <span
            key={i}
            className={`absolute flex h-10 w-10 items-center justify-center rounded-xl shadow-sm transition duration-500 ${tile} ${
              busy ? 'scale-125 shadow-lg' : isFirst || isSecond ? 'scale-110' : arrived ? 'scale-90 opacity-40' : 'opacity-90'
            }`}
            style={{ left: n.x - 20, top: n.y - 20 }}
          >
            <Icon className={`h-4 w-4 ${i === 5 && busy ? 'animate-[spin_3s_linear_infinite] motion-reduce:animate-none' : ''}`} />
            {done && (
              <span className="absolute -top-1.5 -right-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-emerald-500 text-white ring-2 ring-surface">
                <CheckIcon className="h-2.5 w-2.5" />
              </span>
            )}
          </span>
        )
      })}

      {/* What one agent hands the next, travelling along the ring. */}
      {s.handoff && second !== undefined && (
        <span
          className="absolute top-0 left-0 z-10 inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap text-slate-700 shadow-md ring-1 ring-slate-200"
          style={{
            offsetPath: `path('${arcPath(first, second)}')`,
            offsetRotate: '0deg',
            offsetDistance: passed ? '100%' : '0%',
            opacity: handingOff ? 1 : 0,
            transition: 'offset-distance 0.75s cubic-bezier(0.65, 0, 0.35, 1), opacity 0.25s',
          }}
        >
          <AgentBadge agent={first} className="h-3.5 w-3.5 [&_svg]:h-2 [&_svg]:w-2" />
          {s.handoff.carry}
        </span>
      )}

      {/* Hub */}
      <span
        className="absolute flex h-14 w-14 items-center justify-center rounded-full bg-surface shadow-md ring-1 ring-slate-200"
        style={{ left: HUB.x - 28, top: HUB.y - 28 }}
      >
        {routing && <span className="absolute inset-0 animate-ping rounded-full bg-brand-blue/25" />}
        <span className="font-display relative text-[26px] leading-none text-slate-900">A</span>
      </span>

      <span className="absolute inset-x-0 bottom-4 flex justify-center">
        <span className="inline-flex max-w-[90%] items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-[11px] font-semibold whitespace-nowrap text-slate-700 shadow-sm ring-1 ring-slate-200">
          {arrived ? (
            <AgentBadge agent={statusAgent} className="h-4 w-4 shrink-0 [&_svg]:h-2.5 [&_svg]:w-2.5" />
          ) : (
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full bg-brand-blue ${routing ? 'animate-pulse' : 'opacity-40'}`} />
          )}
          <span className="truncate">{status}</span>
        </span>
      </span>
    </div>
  )
}

// 03: the work arrives line by line, gets approved and ships.
const BURST = ['bg-brand-blue', 'bg-brand-pink', 'bg-brand-yellow', 'bg-brand-violet', 'bg-brand-sky', 'bg-brand-orchid', 'bg-brand-blue', 'bg-brand-yellow']

function ReviewVisual({ story, t }: Frame) {
  const s = STORIES[story]
  const ready = t >= ROWS[ROWS.length - 1]
  const shipped = t >= SHIPPED
  const clicking = t >= CLICK && t < SHIPPED + 100
  const cursorIn = t >= CURSOR && t < SHIPPED + 700

  const status = shipped
    ? { label: 'Shipped', className: 'bg-emerald-50 text-emerald-700' }
    : ready
      ? { label: 'Ready for review', className: 'bg-brand-yellow/30 text-slate-800' }
      : { label: 'Working', className: 'bg-slate-100 text-slate-500' }

  return (
    <div className="absolute inset-0 flex items-center justify-center px-5">
      <div className="w-full rounded-2xl bg-surface p-4 shadow-lg ring-1 shadow-slate-900/5 ring-slate-200">
        <div className="flex items-center gap-2">
          <AgentBadge agent={s.handoff?.to ?? s.agent} className="h-6 w-6" />
          <span className="flex-1 truncate text-[12px] font-semibold text-slate-900">{s.title}</span>
          <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold transition-colors duration-300 ${status.className}`}>
            {status.label}
          </span>
        </div>

        <ul className="mt-3 space-y-2">
          {s.rows.map((row, i) => {
            const shown = t >= ROWS[i]
            return (
              <li key={i} className="relative h-9">
                <span
                  className={`absolute inset-0 flex items-center gap-2 rounded-lg px-1 transition-opacity duration-300 ${
                    shown ? 'opacity-0' : 'opacity-100'
                  }`}
                >
                  <span className="h-7 w-7 shrink-0 animate-pulse rounded-lg bg-slate-100" />
                  <span className="flex-1 space-y-1.5">
                    <span className="block h-2 w-2/3 animate-pulse rounded-full bg-slate-100" />
                    <span className="block h-2 w-1/2 animate-pulse rounded-full bg-slate-100" />
                  </span>
                </span>
                <span
                  className={`absolute inset-0 flex items-center gap-2 rounded-lg px-1 transition duration-500 ${
                    shown ? 'translate-x-0 opacity-100' : '-translate-x-3 opacity-0'
                  }`}
                >
                  <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold ${row.tile}`}>
                    {row.mark}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[11px] font-semibold text-slate-900">{row.name}</span>
                    <span className="block truncate text-[10px] text-slate-500">{row.meta}</span>
                  </span>
                  <CheckIcon className={`h-3.5 w-3.5 shrink-0 text-emerald-500 transition-opacity duration-300 ${shipped ? 'opacity-100' : 'opacity-0'}`} />
                </span>
              </li>
            )
          })}
        </ul>

        <div className="mt-3 flex items-center justify-end gap-2">
          <span className="rounded-full px-3 py-1.5 text-[11px] font-medium text-slate-500 ring-1 ring-slate-200">Edit</span>
          <span className="relative">
            <span
              className={`relative inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] font-semibold text-white transition duration-200 ${
                shipped ? 'bg-brand-violet' : 'bg-brand-blue'
              } ${clicking ? 'scale-95' : 'scale-100'} ${ready || shipped ? 'opacity-100' : 'opacity-40'}`}
            >
              {shipped && <CheckIcon className="h-3 w-3 text-brand-yellow" />}
              {shipped ? 'Shipped' : 'Approve & ship'}
            </span>

            {/* A little burst of brand colours on ship. */}
            {BURST.map((color, i) => {
              const a = (i / BURST.length) * Math.PI * 2
              return (
                <span
                  key={i}
                  className={`absolute top-1/2 left-1/2 h-1.5 w-1.5 rounded-full ${color}`}
                  style={{
                    transform: shipped
                      ? `translate(${Math.cos(a) * 46 - 3}px, ${Math.sin(a) * 26 - 3}px) scale(1)`
                      : 'translate(-3px, -3px) scale(0)',
                    opacity: shipped && t < SHIPPED + 600 ? 1 : 0,
                    transition: shipped ? 'transform 0.6s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.4s 0.25s' : 'none',
                  }}
                />
              )
            })}

            {/* The reviewer's cursor. */}
            <svg
              viewBox="0 0 24 24"
              className="pointer-events-none absolute top-1/2 left-1/2 h-5 w-5 drop-shadow"
              style={{
                transform: cursorIn
                  ? `translate(${clicking ? 4 : 6}px, ${clicking ? 2 : 4}px) scale(${clicking ? 0.85 : 1})`
                  : 'translate(90px, 90px)',
                opacity: cursorIn ? 1 : 0,
                transition: 'transform 0.7s cubic-bezier(0.65, 0, 0.35, 1), opacity 0.3s',
              }}
            >
              <path d="M5 3l14 7.5-6.2 1.6L10 18.5z" className="fill-ink stroke-white" strokeWidth="1.5" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </div>
    </div>
  )
}

const steps: { number: string; title: string; description: string; Visual: (frame: Frame) => ReactNode }[] = [
  {
    number: '01',
    title: 'Describe the task',
    description: "Tell Agentis what you need in plain language, the same way you'd brief a teammate.",
    Visual: PromptVisual,
  },
  {
    number: '02',
    title: 'The right agent takes it',
    description: 'Agentis routes the job to a specialized agent with the context and tools to do it well.',
    Visual: RoutingVisual,
  },
  {
    number: '03',
    title: 'Review and ship',
    description: 'Get finished work back for approval, tweak if needed, and publish. No back-and-forth.',
    Visual: ReviewVisual,
  },
]

export default function HowItWorks() {
  const gridRef = useRef<HTMLDivElement>(null)
  const frame = useStoryClock(gridRef)

  return (
    <section id="how-it-works" className="bg-page px-4 py-24 sm:px-6 sm:py-32">
      <div className="mx-auto max-w-2xl text-center">
        <span className="text-sm font-semibold tracking-[0.2em] text-brand-blue uppercase">
          How it works
        </span>
        <h2 className="font-display mt-4 text-4xl text-slate-900 sm:text-5xl">
          From idea to done, in three steps
        </h2>
      </div>

      <div
        ref={gridRef}
        className="mx-auto mt-16 grid max-w-[78rem] min-[1680px]:max-w-[86rem] grid-cols-1 gap-12 sm:grid-cols-3 sm:gap-6 lg:gap-10"
      >
        {steps.map(({ number, title, description, Visual }) => (
          <div key={number}>
            <Stage>
              <Visual {...frame} />
            </Stage>
            <div className="mt-6 flex items-baseline gap-3">
              <span className="font-display text-2xl text-slate-300">{number}</span>
              <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
            </div>
            <p className="mt-2 text-[15px] leading-relaxed text-slate-600">{description}</p>
          </div>
        ))}
      </div>

      <AgentCluster />
    </section>
  )
}
