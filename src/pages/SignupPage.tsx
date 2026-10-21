import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import authBgDark from '../assets/auth-bg-signup-dark.webp'
import authBg from '../assets/auth-bg-signup.png'
import AuthLayout from '../components/AuthLayout'
import { useAuth } from '../lib/AuthContext'

export default function SignupPage() {
  const { user, loading, signUp } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [checkEmail, setCheckEmail] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) {
    return <Navigate to="/dashboard" replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)

    const { error, needsEmailConfirmation } = await signUp({
      fullName,
      email,
      password,
    })

    setSubmitting(false)

    if (error) {
      setError(error)
    } else if (needsEmailConfirmation) {
      setCheckEmail(true)
    } else {
      navigate('/dashboard')
    }
  }

  return (
    <AuthLayout
      image={authBg}
      darkImage={authBgDark}
      headline="Run your company with a team that never sleeps."
      subtext="Create your account and put your first AI agent to work today."
    >
      <h1 className="mt-8 text-2xl font-semibold text-slate-900 lg:mt-0">
        Create your account
      </h1>
      <p className="mt-2 text-[15px] text-slate-500">
        Already on Agentis?{' '}
        <Link to="/login" className="font-medium text-sky-600 hover:text-sky-700">
          Log in
        </Link>
      </p>

      {checkEmail ? (
        <div className="mt-8 rounded-xl border border-sky-100 bg-sky-50 dark:border-brand-sky/20 p-5 text-[15px] text-slate-700">
          Almost there! We sent a confirmation link to{' '}
          <span className="font-medium">{email}</span>. Click it to activate
          your account and sign in.
        </div>
      ) : (
        <>
          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            {error && (
              <p className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-600">
                {error}
              </p>
            )}

            <div>
              <label
                htmlFor="full-name"
                className="text-sm font-medium text-slate-700"
              >
                Full name
              </label>
              <input
                id="full-name"
                type="text"
                required
                autoComplete="name"
                placeholder="Alex Morgan"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3.5 py-2.5 text-[15px] text-slate-900 placeholder:text-slate-400 focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20 focus:outline-none"
              />
            </div>

            <div>
              <label
                htmlFor="signup-email"
                className="text-sm font-medium text-slate-700"
              >
                Work email
              </label>
              <input
                id="signup-email"
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
              <label
                htmlFor="signup-password"
                className="text-sm font-medium text-slate-700"
              >
                Password
              </label>
              <input
                id="signup-password"
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                placeholder="At least 8 characters"
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
              {submitting ? 'Creating account...' : 'Create account'}
            </button>

            <p className="text-center text-xs text-slate-400">
              By creating an account, you agree to Agentis's Terms of Service
              and Privacy Policy.
            </p>
          </form>
        </>
      )}
    </AuthLayout>
  )
}
