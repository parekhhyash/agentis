import { useEffect, useRef, useState } from 'react'

import { CONNECTORS } from '../lib/connectors'

// Every app Agentis connects to, circling the Agentis mark on two tilted
// elliptical orbits (in opposite directions). Logos in front of the mark
// grow and pass over it; those behind shrink, fade and pass under it, so the
// rings read as a ring around a planet. Drawn without tiles, like the Connect page.

type Orbiter = { src: string; name: string; mono: boolean; wide: boolean }

const LOGOS: Orbiter[] = CONNECTORS.flatMap((c) =>
  c.logos.map((src, i) => ({
    src,
    // "Gmail & Google Calendar" is two logos.
    name: c.id === 'google' ? (i === 0 ? 'Gmail' : 'Google Calendar') : c.name.replace(' (Twitter)', ''),
    mono: Boolean(c.monochrome),
    wide: c.id === 'zoho' || c.id === 'salesforce',
  })),
)
const OUTER = LOGOS.filter((_, i) => i % 5 !== 2)
const INNER = LOGOS.filter((_, i) => i % 5 === 2)

const TILT = (-14 * Math.PI) / 180
// Seconds per lap.
const OUTER_LAP = 48
const INNER_LAP = 36

// The two orbits for a stage this wide: outer clockwise, inner the other way.
function ringsFor(width: number) {
  const rx = Math.min(width * 0.45, 400)
  // Rounder on phones, where a flat ellipse would crowd the mark.
  const ry = rx * (width < 640 ? 0.62 : 0.34)
  return [
    { logos: OUTER, rx, ry, lap: OUTER_LAP, direction: 1 },
    { logos: INNER, rx: rx * 0.6, ry: ry * 0.6, lap: INNER_LAP, direction: -1 },
  ]
}

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function ConnectorOrbit() {
  const stageRef = useRef<HTMLDivElement>(null)
  const itemsRef = useRef<(HTMLSpanElement | null)[]>([])
  const [size, setSize] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const el = stageRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const rings = ringsFor(size.w)

  useEffect(() => {
    if (!size.w) return
    const rings = ringsFor(size.w)
    const place = (seconds: number) => {
      let n = 0
      for (const ring of rings) {
        ring.logos.forEach((_, i) => {
          const el = itemsRef.current[n++]
          if (!el) return
          const angle = (i / ring.logos.length) * Math.PI * 2 + ring.direction * (seconds / ring.lap) * Math.PI * 2
          const x = Math.cos(angle) * ring.rx
          const y = Math.sin(angle) * ring.ry
          // Tilt the ellipse; sin(angle) > 0 is the near side.
          const tx = x * Math.cos(TILT) - y * Math.sin(TILT)
          const ty = x * Math.sin(TILT) + y * Math.cos(TILT)
          const near = (Math.sin(angle) + 1) / 2
          el.style.transform = `translate(-50%, -50%) translate(${tx}px, ${ty}px) scale(${0.62 + near * 0.5})`
          el.style.opacity = String(0.45 + near * 0.55)
          el.style.zIndex = near > 0.5 ? '30' : '10'
        })
      }
    }

    if (reducedMotion()) {
      place(0)
      return
    }
    let frame = 0
    let visible = true
    const start = performance.now()
    const tick = (now: number) => {
      place((now - start) / 1000)
      frame = visible ? requestAnimationFrame(tick) : 0
    }
    // Only animate while the section is on screen.
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      if (visible && !frame) frame = requestAnimationFrame(tick)
    })
    if (stageRef.current) observer.observe(stageRef.current)
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [size.w])

  let n = 0
  return (
    <section id="integrations" className="relative z-10 overflow-x-clip px-4 py-24 sm:px-6 sm:py-32">
      <div className="mx-auto max-w-2xl text-center">
        <span className="text-sm font-semibold tracking-[0.2em] text-brand-blue uppercase">Integrations</span>
        <h2 className="font-display mt-4 text-4xl text-slate-900 sm:text-5xl">Your tools, one team of agents</h2>
        <p className="mt-5 text-lg leading-relaxed text-slate-600">
          Connect Gmail, Sheets, your CRM and your social accounts once. Every agent can then read, draft and act in
          them, and nothing goes out until you approve it.
        </p>
      </div>

      <div ref={stageRef} aria-hidden="true" className="relative mx-auto mt-10 h-[20rem] max-w-5xl sm:mt-14 sm:h-[28rem]">
        <svg className="absolute inset-0 h-full w-full overflow-visible">
          {size.w > 0 &&
            rings.map((ring, i) => (
              <ellipse
                key={i}
                cx={size.w / 2}
                cy={size.h / 2}
                rx={ring.rx}
                ry={ring.ry}
                transform={`rotate(${(TILT * 180) / Math.PI} ${size.w / 2} ${size.h / 2})`}
                fill="none"
                strokeWidth="1.5"
                strokeDasharray="2 8"
                strokeLinecap="round"
                className="stroke-slate-300"
              />
            ))}
        </svg>

        {/* The Agentis mark, between the two halves of the rings. */}
        <span className="absolute top-1/2 left-1/2 z-20 flex h-20 w-20 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-surface shadow-lg ring-1 ring-slate-200 sm:h-28 sm:w-28">
          <span className="absolute -inset-3 rounded-full bg-brand-blue/10 sm:-inset-4" />
          <span className="absolute -inset-6 rounded-full bg-brand-blue/5 sm:-inset-9" />
          <span className="absolute inset-0 animate-ping rounded-full bg-brand-blue/15 [animation-duration:2.4s] motion-reduce:animate-none" />
          <span className="absolute inset-0 rounded-full bg-surface ring-1 ring-slate-200" />
          <span className="font-display relative text-4xl leading-none text-slate-900 sm:text-6xl">A</span>
        </span>

        {size.w > 0 &&
          rings.flatMap((ring) =>
            ring.logos.map((logo) => {
              const index = n++
              return (
                <span
                  key={`${logo.name}-${index}`}
                  ref={(el) => {
                    itemsRef.current[index] = el
                  }}
                  className="absolute top-1/2 left-1/2 flex h-8 w-10 items-center justify-center will-change-transform sm:h-12 sm:w-14"
                >
                  <img
                    src={logo.src}
                    alt=""
                    className={`max-h-full object-contain ${logo.wide ? 'w-full' : 'h-7 w-7 sm:h-10 sm:w-10'} ${logo.mono ? 'dark:invert' : ''}`}
                  />
                </span>
              )
            }),
          )}
      </div>
      <p className="sr-only">Works with {LOGOS.map((l) => l.name).join(', ')}.</p>
    </section>
  )
}
