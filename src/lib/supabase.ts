import { createClient } from '@supabase/supabase-js'
import type { Database } from './database.types'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY environment variables',
  )
}

// PKCE: the email confirmation link comes back with ?code=... rather than
// tokens in the #fragment, which the HashRouter uses for its routes.
export const supabase = createClient<Database>(supabaseUrl, supabaseAnonKey, {
  auth: { flowType: 'pkce' },
})

// Where Supabase sends the browser back to after an emailed link: a route
// of this app, on whatever host it's served from.
export function authRedirect(route: string): string {
  return `${window.location.origin}${window.location.pathname}#${route}`
}
