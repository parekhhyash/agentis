import { Link } from 'react-router-dom'
import type { CSSProperties, ReactNode } from 'react'

import ThemeToggle from './ThemeToggle'

export default function AuthLayout({
  image,
  darkImage,
  headline,
  subtext,
  children,
}: {
  image: string
  // The night version for dark mode, anchored left so its flowers frame the panel.
  darkImage?: string
  headline: string
  subtext: string
  children: ReactNode
}) {
  return (
    <div className="relative flex min-h-screen bg-page">
      <ThemeToggle className="absolute top-5 right-5 z-10 text-slate-500 hover:bg-slate-100" />
      <div
        className={`relative hidden w-1/2 bg-(image:--auth-light) bg-cover bg-center lg:block ${
          darkImage ? 'dark:bg-(image:--auth-dark) dark:bg-left' : ''
        }`}
        style={{ '--auth-light': `url(${image})`, '--auth-dark': `url(${darkImage ?? image})` } as CSSProperties}
      >
        <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-black/5 to-transparent" />

        <Link
          to="/"
          // A soft shadow keeps it readable where it sits over bright flowers.
          className="font-display absolute top-8 left-8 text-2xl text-white [text-shadow:0_1px_12px_rgb(0_0_0/0.6)]"
        >
          Agentis
        </Link>

        <div className="absolute bottom-16 left-8 max-w-md pr-8">
          <h2 className="font-display text-balance text-3xl text-white sm:text-4xl">
            {headline}
          </h2>
          <p className="mt-4 text-lg text-white/85">{subtext}</p>
        </div>
      </div>

      <div className="flex w-full flex-col items-center justify-center px-6 py-12 sm:px-12 lg:w-1/2 lg:px-20">
        <Link
          to="/"
          className="font-display self-start text-2xl text-slate-900 lg:hidden"
        >
          Agentis
        </Link>

        <div className="mx-auto w-full max-w-sm">{children}</div>
      </div>
    </div>
  )
}
