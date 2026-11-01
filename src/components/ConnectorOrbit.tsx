import { useEffect, useRef, useState } from 'react'

import { CONNECTORS } from '../lib/connectors'

// Every app Agentis connects to, circling the Agentis mark on two tilted
// elliptical orbits (in opposite directions), with no orbit lines drawn. The
// inner one is like a planet's ring: wider than the mark but not as tall, so
// its logos cross it. Logos in front grow and pass over the mark; those
// behind shrink, fade and pass under it. Each ring's logos ride it like a
// rollercoaster train: they speed up and close ranks as they drop to the
// bottom, then slow down and spread out as they climb back to the top. Drawn
// without tiles, like the Connect page.

type Orbiter = { src: string; name: string; mono: boolean; wide: boolean }

// One of each logo (Zoho CRM and Zoho Desk share Zoho's).
const LOGOS: Orbiter[] = CONNECTORS.filter((c, i) => CONNECTORS.findIndex((o) => o.logo === c.logo) === i).map((c) => ({
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

// How a ring's train rides. Gravity sets its speed from how high its middle
// is on screen: one lap per `slowLap` seconds at the top, one per `fastLap` at
// the bottom. The gap between neighbouring logos, as a share of an even
// spread, goes from `loose` when it's slowest to `tight` when it's fastest.
// With these numbers no logo ever moves backwards as the gaps change.
type Motion = { slowLap: number; fastLap: number; tight: number; loose: number }
const OUTER_MOTION: Motion = { slowLap: 60, fastLap: 9, tight: 0.45, loose: 0.82 }
// The ring is small on phones, so its logos need bigger gaps not to pile up.
const OUTER_MOTION_PHONE: Motion = { ...OUTER_MOTION, tight: 0.6, loose: 0.9 }
const INNER_MOTION: Motion = { slowLap: 40, fastLap: 8, tight: 0.62, loose: 0.92 }

type Ring = { logos: Orbiter[]; rx: number; ry: number; motion: Motion; direction: number }

// The train's speed (radians a second) with its middle at `angle`, and the
// gap between its logos at that speed.
function ride(ring: Ring, angle: number) {
  const { slowLap, fastLap, tight, loose } = ring.motion
  const slow = (2 * Math.PI) / slowLap
  const fast = (2 * Math.PI) / fastLap
  // How far down the ring that is on screen: 0 at the top, 1 at the bottom.
  const a = ring.rx * Math.sin(TILT)
  const b = ring.ry * Math.cos(TILT)
  const height = Math.hypot(a, b)
  const drop = (a * Math.cos(angle) + b * Math.sin(angle) + height) / (2 * height)
  // As on a coaster, the energy it gains grows with how far it has dropped.
  const speed = Math.sqrt(slow * slow + (fast * fast - slow * slow) * drop)
  const even = (2 * Math.PI) / ring.logos.length
  const gap = even * (loose - ((loose - tight) * (speed - slow)) / (fast - slow))
  return { speed, gap }
}

// The two orbits for a stage this wide around a mark of this radius: outer
// clockwise, inner the other way. Both are the same shape (one height to
// width ratio, one centre, one tilt), so they sit symmetrically; the inner one
// is wider than the mark but not as tall, so it passes in front of and behind it.
function ringsFor(width: number, planet: number) {
  const phone = width < 640
  // Rounder on phones, where flat ellipses would crowd the mark.
  const ratio = phone ? 0.4 : 0.3
  const rx = Math.min(width * 0.45, 400)
  const inner = Math.min(planet * 2.2, rx * 0.66)
  const rings: Ring[] = [
    { logos: OUTER, rx, ry: rx * ratio, motion: phone ? OUTER_MOTION_PHONE : OUTER_MOTION, direction: 1 },
    { logos: INNER, rx: inner, ry: inner * ratio, motion: INNER_MOTION, direction: -1 },
  ]
  return rings
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
    // Where each ring's train has its middle. It starts just past the top of
    // the ring, about to drop.
    const middles = rings.map(
      (ring) => Math.atan2(ring.ry * Math.cos(TILT), ring.rx * Math.sin(TILT)) + Math.PI + ring.direction * 0.3,
    )
    // `atRest`: evenly spread, for people who ask for less motion.
    const place = (atRest: boolean) => {
      let n = 0
      rings.forEach((ring, r) => {
        const gap = atRest ? (2 * Math.PI) / ring.logos.length : ride(ring, middles[r]).gap
        const middle = (ring.logos.length - 1) / 2
        ring.logos.forEach((_, i) => {
          const angle = middles[r] + ring.direction * (i - middle) * gap
          const el = itemsRef.current[n++]
          if (!el) return
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
      })
    }

    if (reducedMotion()) {
      place(true)
      return
    }
    let frame = 0
    let visible = true
    let last = performance.now()
    const tick = (now: number) => {
      // Capped, so coming back to the page doesn't throw the trains forward.
      const seconds = Math.min((now - last) / 1000, 0.05)
      last = now
      rings.forEach((ring, r) => {
        middles[r] += ring.direction * ride(ring, middles[r]).speed * seconds
      })
      place(false)
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
