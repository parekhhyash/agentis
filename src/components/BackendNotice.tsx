import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { BACKEND_URL } from '../lib/backendApi'
import { useBackendStatus } from '../lib/backendStatus'
import { CloseIcon, ExternalLinkIcon } from './icons'

const host = BACKEND_URL.replace(/^https?:\/\//, '').replace(/\/$/, '')

function BackendLink({ children }: { children: string }) {
  return (
    <a
      href={BACKEND_URL}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 font-semibold underline underline-offset-2 hover:no-underline"
    >
      {children}
      <ExternalLinkIcon className="size-3.5" />
    </a>
  )
}

// A bar above everything while the agent API is starting up or can't be
// reached, with a link to open it directly. Pages leave room for it through
// --banner-h.
export default function BackendNotice() {
  const status = useBackendStatus()
  const [dismissed, setDismissed] = useState(false)
  const [justWoke, setJustWoke] = useState(false)
  const waited = useRef(false)
  const bar = useRef<HTMLDivElement>(null)

  // After a wait, say briefly that it's ready before the bar goes away.
  useEffect(() => {
    if (status === 'waking' || status === 'unreachable') waited.current = true
    if (status !== 'ready' || !waited.current) return
    waited.current = false
    setJustWoke(true)
    const timer = setTimeout(() => setJustWoke(false), 4000)
    return () => clearTimeout(timer)
  }, [status])

  const ready = justWoke && status === 'ready'
  const visible = !dismissed && (status === 'waking' || status === 'unreachable' || ready)

  useLayoutEffect(() => {
    const el = bar.current
    if (!el) return
    const root = document.documentElement.style
    const fit = () => root.setProperty('--banner-h', `${el.offsetHeight}px`)
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(el)
    return () => {
      observer.disconnect()
      root.setProperty('--banner-h', '0px')
    }
  }, [visible])

  if (!visible) return null
  return (
    <div
      ref={bar}
      role="status"
      className="fixed inset-x-0 top-0 z-40 flex items-center justify-center gap-2 bg-brand-yellow py-2 pr-11 pl-4 text-center text-sm text-ink"
    >
      {status === 'waking' && (
        <>
          <span className="size-3.5 shrink-0 animate-spin rounded-full border-2 border-ink/25 border-t-ink" />
          <span>
            Starting the backend at <BackendLink>{host}</BackendLink>
            <span className="hidden sm:inline">. It sleeps when idle, so this can take a minute.</span>
          </span>
        </>
      )}
      {status === 'unreachable' && (
        <span>
          The backend isn’t answering. Open <BackendLink>{host}</BackendLink> to start it, then come back.
        </span>
      )}
      {ready && <span>The backend is ready.</span>}
      <button
        type="button"
        aria-label="Dismiss"
        onClick={() => setDismissed(true)}
        className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full p-1 hover:bg-ink/10"
      >
        <CloseIcon className="size-4" />
      </button>
    </div>
  )
}
