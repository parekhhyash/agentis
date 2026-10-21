import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import heroBgDark from '../assets/hero-bg-dark.webp'
import heroBg from '../assets/hero-bg.png'
import { createAgentRequest, RUNNABLE_AGENTS, startAgentRun } from '../lib/agentRuns'
import { createConversation } from '../lib/conversations'
import { AGENT_TYPES, type AgentType } from '../lib/agentTypes'
import { useAuth } from '../lib/AuthContext'
import { useTheme } from '../lib/theme'
import { useProfile } from '../lib/useProfile'
import { ArrowUpIcon, ChevronDownIcon, CloseIcon, MenuIcon, MoonIcon, SunIcon } from './icons'
import SectionLink from './SectionLink'
import ThemeToggle from './ThemeToggle'

const navLinks = [
  { label: 'Features', id: 'features' },
  { label: 'How it works', id: 'how-it-works' },
  { label: 'Testimonials', id: 'testimonials' },
  { label: 'FAQs', id: 'faqs' },
]

// Full-width "Dark mode" row with an on/off switch, for the mobile menu.
function MenuThemeSwitch() {
  const { theme, toggle } = useTheme()
  const on = theme === 'dark'
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={toggle}
      className="flex w-full items-center justify-between rounded-xl px-3 py-3 text-[15px] font-semibold text-slate-800 hover:bg-slate-50"
    >
      <span className="flex items-center gap-2.5">
        {on ? <SunIcon className="text-slate-500" /> : <MoonIcon className="text-slate-500" />}
        Dark mode
      </span>
      <span className={`relative h-6 w-10 rounded-full transition-colors ${on ? 'bg-brand-blue' : 'bg-slate-300'}`}>
        <span
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
            on ? 'translate-x-4' : 'translate-x-0'
          }`}
        />
      </span>
    </button>
  )
}

function Navbar({ dark }: { dark: boolean }) {
  const { user } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

  // Close the mobile menu if the viewport grows past the breakpoint.
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)')
    const close = () => mq.matches && setMenuOpen(false)
    mq.addEventListener('change', close)
    return () => mq.removeEventListener('change', close)
  }, [])

  // At the very top of the hero the bar has no background at all (just the
  // links over the image); the glass panel appears as soon as the page is
  // scrolled, and turns solid once past the hero.
  const [scrolled, setScrolled] = useState(() => window.scrollY > 4)
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // The open menu always sits on a white panel, so use dark text then.
  const solid = dark || menuOpen
  const panel = solid
    ? 'border-slate-300 bg-surface/90 shadow-[0_8px_32px_rgba(0,0,0,0.12)] backdrop-blur-2xl'
    : scrolled
      ? 'border-white/40 bg-white/25 shadow-[0_8px_32px_rgba(0,0,0,0.12)] backdrop-blur-2xl'
      : 'border-transparent bg-transparent shadow-none'

  return (
    <nav
      className={`fixed top-[calc(var(--banner-h)+1.5rem)] left-1/2 z-20 w-[95%] max-w-3xl -translate-x-1/2 border transition-[background-color,border-color,box-shadow] duration-300 ${
        menuOpen ? 'rounded-3xl' : 'rounded-full'
      } ${panel}`}
    >
      <div className="flex items-center justify-between gap-4 px-3 py-2 pl-6">
        <span
          className={`font-display text-xl transition-colors duration-300 ${solid ? 'text-slate-900' : 'text-white'}`}
        >
          Agentis
        </span>

        <div
          className={`hidden items-center gap-6 text-[15px] font-semibold whitespace-nowrap transition-colors duration-300 md:flex lg:gap-8 ${
            dark ? 'text-slate-700' : 'text-white'
          }`}
        >
          {navLinks.map((link) => (
            <SectionLink
              key={link.label}
              id={link.id}
              className={`transition-colors ${dark ? 'hover:text-slate-950' : 'hover:text-white/80'}`}
            >
              {link.label}
            </SectionLink>
          ))}
        </div>

        <div className="flex items-center gap-1">
          {/* On phones the theme switch lives in the menu instead. */}
          <ThemeToggle
            className={`hidden md:block ${solid ? 'text-slate-800 hover:bg-slate-100' : 'text-white hover:bg-white/15'}`}
          />
          <Link
            to={user ? '/dashboard' : '/signup'}
            className={`rounded-full px-5 py-2.5 text-[15px] font-medium whitespace-nowrap shadow-sm transition-colors duration-300 ${
              solid ? 'bg-brand-blue text-white hover:bg-brand-blue/90' : 'bg-white text-blue-500 hover:opacity-90'
            }`}
          >
            {user ? 'Dashboard' : 'Get started'}
          </Link>
          <button
            type="button"
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => setMenuOpen((open) => !open)}
            className={`rounded-full p-2.5 transition-colors md:hidden ${
              solid ? 'text-slate-800 hover:bg-slate-100' : 'text-white hover:bg-white/15'
            }`}
          >
            {menuOpen ? <CloseIcon /> : <MenuIcon />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div id="mobile-nav" className="border-t border-slate-100 px-3 pt-2 pb-3 md:hidden">
          {navLinks.map((link) => (
            <SectionLink
              key={link.label}
              id={link.id}
              onClick={() => setMenuOpen(false)}
              className="block rounded-xl px-3 py-3 text-[15px] font-semibold text-slate-800 hover:bg-slate-50"
            >
              {link.label}
            </SectionLink>
          ))}
          <div className="mt-1 border-t border-slate-100 pt-1">
            <MenuThemeSwitch />
          </div>
        </div>
      )}
    </nav>
  )
}

// Grows the composer with content, but caps it so a very long paste doesn't
// push the rest of the page around - it scrolls internally past this. Kept
// in sync with the dashboard's TaskComposer.
const MAX_TEXTAREA_HEIGHT = 200

function autoResize(el: HTMLTextAreaElement | null) {
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
}

function PromptBox() {
  const { user } = useAuth()
  const { profile } = useProfile()
  const navigate = useNavigate()

  const [value, setValue] = useState('')
  const [agentType, setAgentType] = useState<AgentType>('general')
  const [menuOpen, setMenuOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const selectedAgent = AGENT_TYPES.find((a) => a.value === agentType) ?? AGENT_TYPES[0]
  const SelectedIcon = selectedAgent.icon

  async function submit() {
    const prompt = value.trim()
    if (!prompt || submitting) return

    if (!user) {
      navigate('/signup')
      return
    }

    setSubmitting(true)
    const chat = await createConversation(user.id, prompt)
    const data = chat ? await createAgentRequest(user.id, agentType, prompt, chat.id) : null
    setSubmitting(false)

    if (!chat || !data) return

    // Fire-and-forget: this keeps running after we navigate away, since
    // the abort-controller registry in lib/agentRuns.ts is a module-level
    // singleton, not tied to this component's lifecycle. Agents without a
    // backend yet just sit in the queue.
    void startAgentRun(data, {
      companyContext: {
        company_name: profile?.company_name,
        company_website: profile?.company_website,
        industry: profile?.industry,
        target_audience_location: profile?.target_audience_location,
        company_description: profile?.company_description,
      },
      senderName: profile?.full_name,
    })

    // The dashboard opens on a new chat by default; pass this chat so it
    // opens on the run that was just started instead.
    navigate('/dashboard', { state: { openConversationId: chat.id } })
  }

  return (
    <div className="w-full max-w-2xl rounded-2xl border border-black/5 bg-surface p-4 dark:border-white/10 shadow-[0_20px_60px_rgba(0,0,0,0.45)] sm:p-5">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          autoResize(e.target)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        placeholder="Describe what you want to do..."
        style={{ maxHeight: MAX_TEXTAREA_HEIGHT }}
        className="w-full resize-none overflow-y-auto bg-transparent text-[17px] text-slate-800 placeholder:text-slate-400 focus:outline-none"
      />

      <div className="mt-4 flex items-center justify-between">
        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((open) => !open)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[15px] font-medium text-slate-800 transition-colors hover:bg-slate-100"
          >
            <SelectedIcon />
            {selectedAgent.label}
            <ChevronDownIcon />
          </button>

          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute bottom-full left-0 z-20 mb-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-surface py-1.5 shadow-lg">
                {AGENT_TYPES.map((agent) => (
                  <button
                    key={agent.value}
                    type="button"
                    onClick={() => {
                      setAgentType(agent.value)
                      setMenuOpen(false)
                    }}
                    className={`flex w-full items-center gap-2.5 px-3.5 py-2 text-left text-sm transition-colors hover:bg-slate-50 ${
                      agent.value === agentType ? 'text-sky-600' : 'text-slate-700'
                    }`}
                  >
                    <agent.icon className="shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{agent.label}</span>
                    {!RUNNABLE_AGENTS.includes(agent.value) && (
                      <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
                        Soon
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        <button
          type="button"
          aria-label="Submit"
          onClick={submit}
          disabled={submitting || value.trim().length === 0}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 border-sky-400 text-sky-500 transition-colors hover:bg-sky-50 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowUpIcon />
        </button>
      </div>
    </div>
  )
}

export default function Hero() {
  const heroRef = useRef<HTMLDivElement>(null)
  const [scrolledPastHero, setScrolledPastHero] = useState(false)

  useEffect(() => {
    const el = heroRef.current
    if (!el) return

    const observer = new IntersectionObserver(([entry]) => setScrolledPastHero(!entry.isIntersecting), {
      rootMargin: '-88px 0px 0px 0px',
      threshold: 0,
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // The image sits as a rounded card inset from the page edges, so it reads as
  // a framed panel rather than a full-bleed photo that stops abruptly. Its
  // height is the viewport minus that inset.
  return (
    <div className="p-2 sm:p-3">
      <div
        ref={heroRef}
        // Daytime meadow in light mode, the night version in dark mode.
        className="relative min-h-[calc(100svh-1rem)] rounded-[1.75rem] bg-(image:--hero-light) bg-cover bg-center bg-no-repeat sm:min-h-[calc(100svh-1.5rem)] sm:rounded-[2.5rem] dark:bg-(image:--hero-dark)"
        style={{ '--hero-light': `url(${heroBg})`, '--hero-dark': `url(${heroBgDark})` } as CSSProperties}
      >
        <Navbar dark={scrolledPastHero} />

        <main className="relative flex min-h-[calc(100svh-1rem)] flex-col items-center justify-center px-4 pt-24 pb-16 sm:min-h-[calc(100svh-1.5rem)]">
          <h1 className="font-display max-w-4xl text-center text-5xl leading-[1.05] text-balance text-white sm:text-6xl 2xl:text-7xl">
            Less busywork.
            <br />
            More business.
          </h1>

          <p className="mt-5 max-w-2xl text-center text-lg font-medium text-balance text-white/85 sm:text-xl">
            Turn sales, marketing, design, finance, and operations into AI-powered agents.
          </p>

          <div className="mt-10 w-full max-w-2xl">
            <PromptBox />
          </div>
        </main>
      </div>
    </div>
  )
}
