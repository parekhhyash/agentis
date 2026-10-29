import { useSyncExternalStore } from 'react'
import { BACKEND_URL } from './backendUrl'

export type BackendStatus = 'checking' | 'waking' | 'ready' | 'unreachable'

// The agent API runs on Render's free plan, which puts it to sleep after 15
// idle minutes and takes about a minute to start again on the next request.
// Pinging it as soon as the site opens means it is usually up by the time
// someone runs an agent.
const ASLEEP_AFTER_MS = 2500 // no answer by then: it was asleep and is starting
const ATTEMPT_MS = 30_000
const RETRY_MS = 3000
const GIVE_UP_MS = 3 * 60_000
const RECHECK_AFTER_MS = 5 * 60_000

let status: BackendStatus = 'checking'
let checking = false
let lastAwake = 0
let started = false
const listeners = new Set<() => void>()

function setStatus(next: BackendStatus) {
  if (next === status) return
  status = next
  listeners.forEach((listener) => listener())
}

// The API answered (this check or any other request), so it is up.
export function noteBackendAwake() {
  lastAwake = Date.now()
  setStatus('ready')
}

async function pinged(): Promise<boolean> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), ATTEMPT_MS)
  try {
    // Its own path rather than /health (Render's health check), and a new URL
    // each time so nothing on the way can answer from a cache.
    const response = await fetch(`${BACKEND_URL}/ping?t=${Date.now()}`, {
      cache: 'no-store',
      signal: controller.signal,
    })
    // While it starts, Render can answer with a page of its own instead.
    const body = await response.json().catch(() => null)
    return response.ok && body?.status === 'ok'
  } catch {
    return false
  } finally {
    clearTimeout(timer)
  }
}

// A function, so a change made by another request during an await is seen.
const isReady = () => status === 'ready'

async function check() {
  if (checking) return
  checking = true
  const begin = Date.now()
  setStatus('checking')
  const slow = setTimeout(() => {
    if (status === 'checking') setStatus('waking')
  }, ASLEEP_AFTER_MS)

  while (!isReady() && Date.now() - begin < GIVE_UP_MS) {
    if (await pinged()) {
      noteBackendAwake()
      break
    }
    if (isReady()) break
    setStatus('waking')
    await new Promise((resolve) => setTimeout(resolve, RETRY_MS))
  }
  clearTimeout(slow)
  checking = false
  if (!isReady()) setStatus('unreachable')
}

// Starts the API if it is asleep. Checks again when the tab comes back after
// a while, since it may have gone back to sleep, or when it couldn't be
// reached before (the visitor may have opened it themselves).
export function wakeBackend() {
  if (started) return
  started = true
  void check()
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return
    if (status === 'unreachable' || (status === 'ready' && Date.now() - lastAwake > RECHECK_AFTER_MS)) void check()
  })
}

export function useBackendStatus(): BackendStatus {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => {
        listeners.delete(listener)
      }
    },
    () => status,
  )
}
