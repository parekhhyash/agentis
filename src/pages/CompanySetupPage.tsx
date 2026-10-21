import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import CompanyDetailsForm, {
  emptyCompanyDetails,
  type CompanyDetailsValues,
} from '../components/CompanyDetailsForm'
import { useAuth } from '../lib/AuthContext'
import { supabase } from '../lib/supabase'
import { useProfile } from '../lib/useProfile'

export default function CompanySetupPage() {
  const { user } = useAuth()
  const { profile, loading, setProfile } = useProfile()
  const navigate = useNavigate()

  const [values, setValues] = useState<CompanyDetailsValues>(emptyCompanyDetails())
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && profile?.onboarding_completed) {
    return <Navigate to="/dashboard" replace />
  }

  function updateValues(patch: Partial<CompanyDetailsValues>) {
    setValues((prev) => ({ ...prev, ...patch }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!user) return
    setError(null)

    const name = values.companyName.trim()
    if (!name) {
      setError('Company name is required.')
      return
    }

    setSubmitting(true)
    const { data, error: updateError } = await supabase
      .from('profiles')
      .update({
        company_name: name,
        company_website: values.companyWebsite.trim() || null,
        industry: values.industry.trim() || null,
        target_audience_location: values.targetAudienceLocation || null,
        company_description: values.companyDescription.trim() || null,
        onboarding_completed: true,
      })
      .eq('id', user.id)
      .select()
      .single()

    setSubmitting(false)

    if (updateError || !data) {
      setError('Something went wrong saving your details. Please try again.')
      return
    }

    setProfile(data)
    navigate('/dashboard')
  }

  return (
    <div className="flex min-h-[calc(100vh-var(--banner-h))] items-center justify-center bg-slate-50 px-6 py-12">
      <div className="w-full max-w-lg">
        <span className="font-display text-xl text-slate-900">Agentis</span>

        <h1 className="mt-6 font-display text-3xl text-slate-900">Set up your company</h1>
        <p className="mt-2 text-[15px] text-slate-500">
          This context is shared with your agents so their work fits your business - you
          can change it anytime.
        </p>

        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          {error && (
            <p className="rounded-lg bg-red-50 px-3.5 py-2.5 text-sm text-red-600">{error}</p>
          )}

          <CompanyDetailsForm values={values} onChange={updateValues} />

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-full bg-sky-600 py-2.5 text-[15px] font-semibold text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? 'Saving...' : 'Continue to dashboard'}
          </button>
        </form>
      </div>
    </div>
  )
}
