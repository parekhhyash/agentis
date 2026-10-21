import { useEffect, useRef, useState } from 'react'

import { useTheme } from '../lib/theme'

const text =
  "Agentis isn't another tool you have to learn. It's a team that already knows how to sell, design, support, and report, ready the moment you describe what you need. You stay in control. The work just gets done."

const words = text.split(' ')

// Words fade from a faint grey to full text colour; the pair depends on theme.
const COLORS = {
  light: { from: [203, 213, 225], to: [15, 23, 42] }, // slate-300 -> slate-900
  dark: { from: [71, 71, 71], to: [242, 242, 242] }, // dark-theme slate-300 -> slate-900
}

function wordColor(t: number, { from, to }: { from: number[]; to: number[] }) {
  const clamped = Math.min(1, Math.max(0, t))
  const rgb = from.map((f, i) => Math.round(f + (to[i] - f) * clamped))
  return `rgb(${rgb.join(',')})`
}

export default function ScrollReveal() {
  const sectionRef = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)
  const colors = COLORS[useTheme().theme]

  useEffect(() => {
    let raf = 0

    const measure = () => {
      const el = sectionRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const scrollable = rect.height - window.innerHeight
      const scrolled = -rect.top
      const p = scrollable > 0 ? scrolled / scrollable : 0
      setProgress(Math.min(1, Math.max(0, p)))
    }

    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(measure)
    }

    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  return (
    <section ref={sectionRef} className="relative bg-page" style={{ height: '250vh' }}>
      <div className="sticky top-(--banner-h) flex h-[calc(100vh-var(--banner-h))] items-center justify-center overflow-x-clip px-6">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-brand-sky/10 blur-3xl"
        />
        <p className="font-display relative max-w-4xl text-center text-3xl leading-snug text-balance sm:text-4xl md:text-5xl">
          {words.map((word, i) => (
            <span
              key={i}
              style={{ color: wordColor(progress * words.length - i, colors) }}
            >
              {word}{' '}
            </span>
          ))}
        </p>
      </div>
    </section>
  )
}
