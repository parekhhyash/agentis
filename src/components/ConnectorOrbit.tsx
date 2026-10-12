import { useEffect, useRef, useState } from 'react'

import { CONNECTORS } from '../lib/connectors'

// Every app Agentis connects to, circling the Agentis mark on two tilted
// elliptical orbits (in opposite directions), with no orbit lines drawn. The
// inner one is like a planet's ring: wider than the mark but not as tall, so
// its logos cross it. Logos in front grow and pass over the mark; those
// behind shrink, fade and pass under it. Drawn without tiles, like the
// Connect page.

type Orbiter = { src: string; name: string; mono: boolean; wide: boolean }

const LOGOS: Orbiter[] = CONNECTORS.map((c) => ({
  src: c.logo,
  name: c.name.replace(' (Twitter)', ''),
  mono: Boolean(c.monochrome),
  wide: c.id === 'zoho' || c.id === 'salesforce',
}))
// Google Sheets, X and Slack go round the mark; the rest on the outer orbit.
const INNER_NAMES = new Set(['Google Sheets', 'X', 'Slack'])
const OUTER = LOGOS.filter((l) => !INNER_NAMES.has(l.name))
const INNER = LOGOS.filter((l) => INNER_NAMES.has(l.name))

const TILT = (-14 * Math.PI) / 180
// Seconds per lap.
const OUTER_LAP = 48
const INNER_LAP = 36

// The two orbits for a stage this wide around a mark of this radius: outer
// clockwise, inner the other way. Both are the same shape (one height to
// width ratio, one centre, one tilt), so they sit symmetrically; the inner one
// is wider than the mark but not as tall, so it passes in front of and behind it.
function ringsFor(width: number, planet: number) {
  // Rounder on phones, where flat ellipses would crowd the mark.
  const ratio = width < 640 ? 0.4 : 0.3
  const rx = Math.min(width * 0.45, 400)
  const inner = Math.min(planet * 2.2, rx * 0.66)
  return [
    { logos: OUTER, rx, ry: rx * ratio, lap: OUTER_LAP, direction: 1 },
    { logos: INNER, rx: inner, ry: inner * ratio, lap: INNER_LAP, direction: -1 },
  ]
}

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export default function ConnectorOrbit() {
  const stageRef = useRef<HTMLDivElement>(null)
  const planetRef = useRef<HTMLSpanElement>(null)
  const itemsRef = useRef<(HTMLSpanElement | null)[]>([])
  // Stage width and height, and the mark's radius (it changes at the sm breakpoint).
  const [size, setSize] = useState({ w: 0, h: 0, r: 0 })

  useEffect(() => {
    const el = stageRef.current
    if (!el) return
    const observer = new ResizeObserver(([entry]) =>
      setSize({ w: entry.contentRect.width, h: entry.contentRect.height, r: (planetRef.current?.offsetWidth ?? 128) / 2 }),
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const rings = ringsFor(size.w, size.r)

  useEffect(() => {
    if (!size.w) return
    const rings = ringsFor(size.w, size.r)
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
  }, [size.w, size.r])

  let n = 0
  return (
    <section id="integrations" className="relative z-10 overflow-x-clip px-4 py-24 sm:px-6 sm:py-32">
      {/* The label is centred at the top, like every section's. */}
      <p className="text-center text-sm font-semibold tracking-[0.2em] text-brand-blue uppercase">Integrations</p>

      {/* Stacked and centred on smaller screens; text left, orbit right on laptops. */}
      <div className="mx-auto mt-4 grid max-w-[78rem] items-center gap-10 sm:gap-14 lg:mt-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-8 min-[1680px]:max-w-[86rem]">
        <div className="mx-auto max-w-2xl text-center lg:mx-0 lg:max-w-md lg:text-left">
          <h2 className="font-display text-4xl text-slate-900 sm:text-5xl">Your tools, one team of agents</h2>
          <p className="mt-5 text-lg leading-relaxed text-slate-600">
            Connect Gmail, Sheets, your CRM and your social accounts once. Every agent can then read, draft and act in
            them, and nothing goes out until you approve it.
          </p>
        </div>

        <div ref={stageRef} aria-hidden="true" className="relative mx-auto h-[20rem] w-full max-w-5xl sm:h-[28rem] lg:h-[30rem]">
          {/* Agentis, the planet the inner ring goes round. */}
          <span
            ref={planetRef}
            className="absolute top-1/2 left-1/2 z-20 flex h-24 w-24 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-surface shadow-lg ring-1 ring-slate-200 sm:h-32 sm:w-32"
          >
            <span className="font-display text-xl leading-none text-slate-900 sm:text-3xl">Agentis</span>
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
      </div>
      <p className="sr-only">Works with {LOGOS.map((l) => l.name).join(', ')}.</p>
    </section>
  )
}
