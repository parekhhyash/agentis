import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'

import { AGENTS, arcPath, HUB, NODES, STAGE_H, STAGE_W } from '../lib/agentNetwork'

// The agent network drawn in "How it works" and, live, in the dashboard while
// an agent runs: a hub with the six agents around it, each with its own
// "working" animation. Drawn on a fixed 320 x 288 canvas scaled to fit.

export function Stage({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setScale(entry.contentRect.width / STAGE_W))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} aria-hidden="true" className="relative aspect-[10/9] overflow-hidden rounded-3xl bg-zinc-100">
      <div
        className="absolute top-0 left-0"
        style={{ width: STAGE_W, height: STAGE_H, transform: `scale(${scale})`, transformOrigin: 'top left' }}
      >
        {children}
      </div>
    </div>
  )
}

export function CheckIcon({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="m3.5 8.5 3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function AgentBadge({ agent, className = '' }: { agent: number; className?: string }) {
  const { icon: Icon, tile } = AGENTS[agent]
  return (
    <span className={`flex items-center justify-center rounded-full ${tile} ${className}`}>
      <Icon className="h-3.5 w-3.5" />
    </span>
  )
}

// Unit vector from the hub out to a node: satellites (bubbles, envelopes)
// sit on the outside of the circle so they don't cross the routing lines.
function outward(i: number) {
  const dx = NODES[i].x - HUB.x
  const dy = NODES[i].y - HUB.y
  const len = Math.hypot(dx, dy)
  return { x: dx / len, y: dy / len }
}

function Envelope({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 12" className={className} aria-hidden="true">
      <rect x="0.75" y="0.75" width="14.5" height="10.5" rx="2" className="fill-surface stroke-brand-violet" strokeWidth="1.5" />
      <path d="m1.5 1.8 6.5 4.7 6.5-4.7" fill="none" className="stroke-brand-violet" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

// What each agent looks like while it's busy, drawn around its node.
export function AgentWork({ agent }: { agent: number }) {
  const node = NODES[agent]
  const out = outward(agent)
  const at = (distance: number, size: number) => ({ left: node.x + out.x * distance - size / 2, top: node.y + out.y * distance - size / 2 })

  switch (agent) {
    case 0: // Lead Research: radar sweep, companies popping up as they're found
      return (
        <>
          {[0, 0.8].map((delay) => (
            <span
              key={delay}
              className="absolute h-10 w-10 animate-radar rounded-xl border-2 border-brand-blue"
              style={{ left: node.x - 20, top: node.y - 20, animationDelay: `${delay}s` }}
            />
          ))}
          {[
            [-46, -6, 0],
            [46, 2, 0.8],
            [-38, 22, 1.6],
          ].map(([dx, dy, delay]) => (
            <span
              key={delay}
              className="absolute flex h-4 w-4 animate-pop items-center justify-center rounded-md bg-surface text-[8px] font-bold text-brand-blue shadow ring-1 ring-brand-blue/30"
              style={{ left: node.x + dx - 8, top: node.y + dy - 8, animationDelay: `${delay}s` }}
            >
              ✓
            </span>
          ))}
        </>
      )
    case 1: // Sales & Outreach: emails flying out
      return (
        <>
          {[-0.5, 0, 0.5].map((spread, k) => {
            const angle = Math.atan2(out.y, out.x) + spread
            return (
              <span
                key={k}
                className="absolute animate-fly"
                style={
                  {
                    ...at(18, 14),
                    '--dx': `${Math.cos(angle) * 40}px`,
                    '--dy': `${Math.sin(angle) * 40}px`,
                    animationDelay: `${k * 0.45}s`,
                  } as CSSProperties
                }
              >
                <Envelope className="h-3 w-3.5" />
              </span>
            )
          })}
        </>
      )
    case 2: // Customer Support: a reply being typed
      return (
        <span
          className="absolute flex h-5 items-center gap-0.5 rounded-full rounded-bl-sm bg-surface px-2 shadow ring-1 ring-brand-sky/40"
          style={{ left: node.x + 14, top: node.y - 34 }}
        >
          {[0, 1, 2].map((d) => (
            <span key={d} className="h-1 w-1 animate-bounce rounded-full bg-brand-sky" style={{ animationDelay: `${d * 120}ms` }} />
          ))}
        </span>
      )
    case 3: // Data & Reporting: a chart building
      return (
        <span className="absolute flex h-6 items-end gap-0.5" style={{ left: node.x + 28, top: node.y - 14 }}>
          {[0, 0.2, 0.4, 0.1].map((delay, k) => (
            <span
              key={k}
              className="h-full w-1.5 origin-bottom animate-bars rounded-sm bg-brand-yellow"
              style={{ animationDelay: `${delay}s` }}
            />
          ))}
        </span>
      )
    case 4: // Content & Copy: a page filling with lines
      return (
        <span
          className="absolute flex w-9 flex-col gap-1 rounded-md bg-surface p-1.5 shadow ring-1 ring-brand-pink/60"
          style={at(42, 36)}
        >
          {[1, 0.8, 0.9, 0.55].map((w, k) => (
            <span
              key={k}
              className="block h-0.5 origin-left animate-write rounded-full bg-brand-pink"
              style={{ width: `${w * 100}%`, animationDelay: `${k * 0.25}s` }}
            />
          ))}
        </span>
      )
    default: // Operations: the gear turns, a task orbits it
      return (
        <span
          className="absolute h-16 w-16 animate-[spin_2.4s_linear_infinite] motion-reduce:animate-none"
          style={{ left: node.x - 32, top: node.y - 32 }}
        >
          <span className="absolute top-0 left-1/2 h-2.5 w-2.5 -translate-x-1/2 rounded-full bg-brand-orchid ring-2 ring-surface" />
        </span>
      )
  }
}


// The dashboard's live version: the agent running the request works at its
// node, fed from the hub; when it's using another agent's output (e.g.
// Outreach writing to Lead Research's leads), that hand-off flows between
// the two. `agent` null means the Manager, working from the hub.
export function LiveAgentNetwork({
  agent,
  status,
  handoffFrom,
  carry,
}: {
  agent: number | null
  status: string
  handoffFrom?: number | null
  carry?: string
}) {
  const from = handoffFrom ?? null
  return (
    <Stage>
      <div className="absolute inset-0">
        <svg viewBox={`0 0 ${STAGE_W} ${STAGE_H}`} className="absolute inset-0 h-full w-full">
          <circle
            cx={HUB.x}
            cy={HUB.y}
            r={88}
            fill="none"
            strokeWidth="1.5"
            strokeDasharray="2 7"
            strokeLinecap="round"
            className="origin-center animate-[spin_40s_linear_infinite] stroke-slate-300 [transform-box:fill-box] motion-reduce:animate-none"
          />
          {NODES.map((n, i) => {
            const active = i === agent
            return (
              <line
                key={i}
                x1={HUB.x}
                y1={HUB.y}
                x2={n.x}
                y2={n.y}
                strokeLinecap="round"
                className={active ? `${AGENTS[i].line} animate-dash-flow stroke-current motion-reduce:animate-none` : 'stroke-slate-300'}
                strokeWidth={active ? 2.5 : 1.5}
                strokeDasharray={active ? '6 6' : '2 5'}
              />
            )
          })}
          {/* The hand-off runs along the ring between the two agents. */}
          {from !== null && agent !== null && (
            <path
              d={arcPath(from, agent)}
              fill="none"
              strokeLinecap="round"
              strokeWidth="2.5"
              strokeDasharray="6 6"
              className={`${AGENTS[agent].line} animate-dash-flow stroke-current motion-reduce:animate-none`}
            />
          )}
        </svg>

        {agent !== null && <AgentWork agent={agent} />}

        {NODES.map((n, i) => {
          const { icon: Icon, tile } = AGENTS[i]
          const busy = i === agent
          const helping = i === from
          return (
            <span
              key={i}
              className={`absolute flex h-10 w-10 items-center justify-center rounded-xl shadow-sm transition duration-500 ${tile} ${
                busy ? 'scale-125 shadow-lg' : helping ? 'scale-110' : 'scale-90 opacity-40'
              }`}
              style={{ left: n.x - 20, top: n.y - 20 }}
            >
              <Icon className={`h-4 w-4 ${i === 5 && busy ? 'animate-[spin_3s_linear_infinite] motion-reduce:animate-none' : ''}`} />
            </span>
          )
        })}

        {from !== null && agent !== null && (
          <span
            className="absolute top-0 left-0 z-10 inline-flex animate-travel items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold whitespace-nowrap text-slate-700 shadow-md ring-1 ring-slate-200 motion-reduce:animate-none"
            style={{ offsetPath: `path('${arcPath(from, agent)}')`, offsetRotate: '0deg' }}
          >
            <AgentBadge agent={from} className="h-3.5 w-3.5 [&_svg]:h-2 [&_svg]:w-2" />
            {carry}
          </span>
        )}

        <span
          className="absolute flex h-14 w-14 items-center justify-center rounded-full bg-surface shadow-md ring-1 ring-slate-200"
          style={{ left: HUB.x - 28, top: HUB.y - 28 }}
        >
          <span className="absolute inset-0 animate-ping rounded-full bg-brand-blue/20 motion-reduce:animate-none" />
          <span className="font-display relative text-[26px] leading-none text-slate-900">A</span>
        </span>

        {/* The General agent thinking at the hub: brand-coloured dots circling it. */}
        {agent === null && (
          <span
            className="absolute h-24 w-24 animate-[spin_2.2s_linear_infinite] motion-reduce:animate-none"
            style={{ left: HUB.x - 48, top: HUB.y - 48 }}
          >
            {['bg-brand-blue', 'bg-brand-pink', 'bg-brand-yellow'].map((color, i) => {
              const angle = (i / 3) * Math.PI * 2
              return (
                <span
                  key={color}
                  className={`absolute h-2.5 w-2.5 rounded-full ring-2 ring-surface ${color}`}
                  style={{ left: 48 + Math.cos(angle) * 40 - 5, top: 48 + Math.sin(angle) * 40 - 5 }}
                />
              )
            })}
          </span>
        )}

        <span className="absolute inset-x-0 bottom-4 flex justify-center">
          <span className="inline-flex max-w-[90%] items-center gap-1.5 rounded-full bg-surface px-3 py-1.5 text-[11px] font-semibold whitespace-nowrap text-slate-700 shadow-sm ring-1 ring-slate-200">
            {agent !== null ? (
              <AgentBadge agent={agent} className="h-4 w-4 shrink-0 [&_svg]:h-2.5 [&_svg]:w-2.5" />
            ) : (
              <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brand-blue" />
            )}
            <span className="truncate">{status}</span>
          </span>
        </span>
      </div>
    </Stage>
  )
}
