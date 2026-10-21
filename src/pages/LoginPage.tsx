import { useState } from 'react'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import authBgDark from '../assets/auth-bg-login-dark.webp'
import authBg from '../assets/auth-bg-login.png'
import AuthLayout from '../components/AuthLayout'
import { useAuth } from '../lib/AuthContext'

export default function LoginPage() {
  const { user, loading, signIn } = useAuth()
  const navigate = useNavigate()
  // Back from the email confirmation link (#/login?confirmed=1).
  const [searchParams] = useSearchParams()
  const confirmed = searchParams.get('confirmed') === '1'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  // An expired or already used confirmation link comes back as ?error_description=...
  const [error, setError] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get('error_description'),
  )
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) {
    return <Navigate to="/dashboard" replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)

    const { error } = await signIn(email, password)

    setSubmitting(false)

    if (error) {
      setError(error)
    } else {
      navigate('/dashboard')
    }
  }

  return (
    <AuthLayout
      image={authBg}
      darkImage={authBgDark}
      headline="Welcome back to your AI workforce."
      subtext="Sign in to check in on every agent running your company."
    >
      <h1 className="mt-8 text-2xl font-semibold text-slate-900 lg:mt-0">
        Log in to Agentis
      </h1>
      <p className="mt-2 text-[15px] text-slate-500">
        New here?{' '}
        <Link to="/signup" className="font-medium text-sky-600 hover:text-sky-700">
          Create an account
        </Link>
      </p>

      {confirmed && !error && (
        <p className="mt-6 rounded-lg bg-emerald-50 px-3.5 py-2.5 text-sm text-emerald-700">
          Your email is confirmed. Log in to continue.
        </p>
      )}

      <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
        {error && (
          <p className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-600">
            {error}
          </p>
        )}

        <div>
          <label
            htmlFor="login-email"
            className="text-sm font-medium text-slate-700"
          >
            Work email
          </label>
          <input
            id="login-email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20 focus:outline-none"
          />
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label
              htmlFor="login-password"
              className="text-sm font-medium text-slate-700"
            >
              Password
            </label>
            <a href="#" className="text-sm font-medium text-sky-600 hover:text-sky-700">
              Forgot password?
            </a>
          </div>
          <input
            id="login-password"
            type="password"
            required
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20 focus:outline-none"
          />
        </div>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-full bg-sky-600 py-2.5 text-[15px] font-semibold text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Logging in...' : 'Log in'}
        </button>
      </form>
    </AuthLayout>
  )
}
