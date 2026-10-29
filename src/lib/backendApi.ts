import { BACKEND_URL } from './backendUrl'
import { noteBackendAwake } from './backendStatus'
import { supabase } from './supabase'

export class BackendApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

// Calls the agent API as the signed-in user. Endpoints that touch the user's
// own data (their Google account, their drafts) check this token server-side.
export async function authedFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  if (!token) throw new BackendApiError('Sign in again to continue.', 401)

  let response: Response
  try {
    response = await fetch(`${BACKEND_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
        ...init.headers,
      },
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new BackendApiError(`Could not reach the agent API at ${BACKEND_URL}.`, 0)
  }
  noteBackendAwake()

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = typeof body?.detail === 'string' ? body.detail : response.statusText
    throw new BackendApiError(detail || 'Request failed', response.status)
  }
  return response.json() as Promise<T>
}
