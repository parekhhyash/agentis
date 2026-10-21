import { useSyncExternalStore } from 'react'
import { BACKEND_URL } from './backendApi'

export type BackendStatus = 'checking' | 'waking' | 'ready' | 'unreachable'

// The agent API runs on Render's free plan, which puts it to sleep after 15
// idle minutes and takes about a minute to start again on the next request.
// Pinging it as soon as the site opens means it is usually up by the time
// someone runs an agent.
const ASLEEP_AFTER_MS = 2500 // no answer by then: it was asleep and is starting
const ATTEMPT_MS = 45_000
const RETRY_MS = 3000
const GIVE_UP_MS = 3 * 60_000
const RECHECK_AFTER_MS = 5 * 60_000

let status: BackendStatus = 'checking'
let checking = false
let lastAwake = 0
let started = false
const listeners = new Set<() => void>()

function setStatus(next: BackendStatus) {
  status = next
  listeners.forEach((listener) => listener())
}

async function healthy(): Promise<boolean> {
  try {
    const response = await fetch(`${BACKEND_URL}/health`, {
      cache: 'no-store',
      signal: AbortSignal.timeout(ATTEMPT_MS),
    })
    // While it starts, Render can answer with a page of its own instead.
    const body = await response.json().catch(() => null)
    return response.ok && body?.status === 'ok'
  } catch {
    return false
  }
}

async function check() {
  if (checking) return
  checking = true
  const begin = Date.now()
  setStatus('checking')
  const slow = setTimeout(() => {
    if (status === 'checking') setStatus('waking')
  }, ASLEEP_AFTER_MS)

  let awake = await healthy()
  while (!awake && Date.now() - begin < GIVE_UP_MS) {
    setStatus('waking')
    await new Promise((resolve) => setTimeout(resolve, RETRY_MS))
    awake = await healthy()
  }
  clearTimeout(slow)
  if (awake) lastAwake = Date.now()
  checking = false
  setStatus(awake ? 'ready' : 'unreachable')
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
