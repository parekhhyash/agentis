import type { Session, User } from '@supabase/supabase-js'
import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import { authRedirect, supabase } from './supabase'

type SignUpDetails = {
  email: string
  password: string
  fullName: string
}

type AuthContextValue = {
  user: User | null
  session: Session | null
  loading: boolean
  signUp: (
    details: SignUpDetails,
  ) => Promise<{ error: string | null; needsEmailConfirmation: boolean }>
  signIn: (
    email: string,
    password: string,
  ) => Promise<{ error: string | null }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession)
      setLoading(false)
    })

    return () => subscription.unsubscribe()
  }, [])

  async function signUp({ email, password, fullName }: SignUpDetails) {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: fullName },
        // The confirmation link comes back to the login page of this app.
        emailRedirectTo: authRedirect('/login?confirmed=1'),
      },
    })
    return {
      error: error?.message ?? null,
      needsEmailConfirmation: !error && !data.session,
    }
  }

  async function signIn(email: string, password: string) {
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    })
    return { error: error?.message ?? null }
  }

  async function signOut() {
    await supabase.auth.signOut()
  }

  return (
    <AuthContext.Provider
      value={{
        user: session?.user ?? null,
        session,
        loading,
        signUp,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
