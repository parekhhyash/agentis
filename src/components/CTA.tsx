import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '../lib/AuthContext'
import SectionLink from './SectionLink'

// Fill in real profile URLs; entries with an empty href are not shown.
const socials: { label: string; href: string; icon: ReactNode }[] = [
  {
    label: 'X',
    href: '',
    icon: (
      <path d="M17.75 3h3.07l-6.7 7.66L22 21h-6.17l-4.83-6.32L5.47 21H2.4l7.17-8.2L2 3h6.33l4.37 5.77L17.75 3Zm-1.08 16.17h1.7L7.4 4.74H5.58l11.09 14.43Z" />
    ),
  },
  {
    label: 'LinkedIn',
    href: '',
    icon: (
      <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9.75h4V21H3V9.75Zm6.5 0h3.83v1.54h.06c.53-1 1.84-2.06 3.79-2.06 4.05 0 4.8 2.67 4.8 6.13V21h-4v-4.99c0-1.19-.02-2.72-1.66-2.72-1.66 0-1.92 1.3-1.92 2.63V21h-4V9.75Z" />
    ),
  },
  {
    label: 'YouTube',
    href: '',
    icon: (
      <path d="M23 7.2a3 3 0 0 0-2.1-2.12C19.03 4.58 12 4.58 12 4.58s-7.03 0-8.9.5A3 3 0 0 0 1 7.2 31.3 31.3 0 0 0 .5 12a31.3 31.3 0 0 0 .5 4.8 3 3 0 0 0 2.1 2.12c1.87.5 8.9.5 8.9.5s7.03 0 8.9-.5A3 3 0 0 0 23 16.8a31.3 31.3 0 0 0 .5-4.8 31.3 31.3 0 0 0-.5-4.8ZM9.75 15.02V8.98L15.5 12l-5.75 3.02Z" />
    ),
  },
]

const linkClass = 'text-[15px] text-slate-700 transition-colors hover:text-brand-blue'

function FooterColumn({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="text-sm text-slate-400">{title}</h3>
      <ul className="mt-4 space-y-3">{children}</ul>
    </div>
  )
}

export default function CTA() {
  const { user } = useAuth()
  const visibleSocials = socials.filter((s) => s.href)

  return (
    <section id="get-started" className="relative z-10 px-4 pt-24 sm:px-6 sm:pt-32">
      <div className="mx-auto max-w-3xl text-center">
        <h2 className="font-display text-balance text-5xl leading-[1.05] text-slate-900 sm:text-7xl">
          Describe it.
          <br />
          <span className="text-brand-blue">
            Consider it done.
          </span>
        </h2>
        <Link
          to={user ? '/dashboard' : '/signup'}
          className="group mt-10 inline-flex items-center gap-2 rounded-full bg-brand-blue px-7 py-3.5 text-base font-semibold text-white transition-colors hover:bg-brand-blue/90"
        >
          {user ? 'Go to dashboard' : 'Get started'}
          <svg
            viewBox="0 0 16 16"
            className="h-4 w-4 transition-transform group-hover:translate-x-0.5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path d="M3 8h10M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </Link>
      </div>

      <footer className="mx-auto mt-20 max-w-[78rem] min-[1680px]:max-w-[86rem] pb-12 sm:mt-28">
        <div className="grid gap-12 lg:grid-cols-[1.4fr_3fr]">
          <div>
            <p className="max-w-xs text-[15px] text-slate-500">
              A workforce of AI agents that sells, designs, supports and reports for you.
            </p>
            {visibleSocials.length > 0 && (
              <div className="mt-6 flex items-center gap-5">
                {visibleSocials.map((s) => (
                  <a
                    key={s.label}
                    href={s.href}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={s.label}
                    className="text-slate-900 transition-colors hover:text-brand-blue"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      className="h-5 w-5"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      {s.icon}
                    </svg>
                  </a>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-6">
            <FooterColumn title="Product">
              <li>
                <SectionLink id="features" className={linkClass}>
                  Agents
                </SectionLink>
              </li>
              <li>
                <SectionLink id="how-it-works" className={linkClass}>
                  How it works
                </SectionLink>
              </li>
              <li>
                <SectionLink id="testimonials" className={linkClass}>
                  Testimonials
                </SectionLink>
              </li>
            </FooterColumn>

            <FooterColumn title="Company">
              <li>
                <SectionLink id="about" className={linkClass}>
                  About
                </SectionLink>
              </li>
              <li>
                <SectionLink id="faqs" className={linkClass}>
                  FAQs
                </SectionLink>
              </li>
              <li>
                <a href="/privacy.html" className={linkClass}>
                  Privacy
                </a>
              </li>
              <li>
                <a href="/terms.html" className={linkClass}>
                  Terms
                </a>
              </li>
            </FooterColumn>

            <FooterColumn title="Account">
              {user ? (
                <li>
                  <Link to="/dashboard" className={linkClass}>
                    Dashboard
                  </Link>
                </li>
              ) : (
                <>
                  <li>
                    <Link to="/signup" className={linkClass}>
                      Sign up
                    </Link>
                  </li>
                  <li>
                    <Link to="/login" className={linkClass}>
                      Log in
                    </Link>
                  </li>
                </>
              )}
            </FooterColumn>
          </div>
        </div>

        {/* Giant wordmark sized to the footer width (cqw = 1% of it). */}
        <div className="mt-16 [container-type:inline-size] sm:mt-20" aria-hidden="true">
          <p className="font-display text-center leading-[0.8] tracking-tight whitespace-nowrap text-slate-900 select-none [font-size:33cqw]">
            Agentis
          </p>
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-3 border-t border-slate-200 pt-6 text-sm text-slate-400 sm:mt-20 sm:flex-row sm:items-center">
          <span>© {new Date().getFullYear()} Agentis. All rights reserved.</span>
          <span>Built for teams that would rather ship than wait.</span>
        </div>
      </footer>
    </section>
  )
}
