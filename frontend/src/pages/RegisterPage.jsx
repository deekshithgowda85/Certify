import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { register } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/authStore'
import AuthQuickLinks from '../components/AuthQuickLinks'

function Field({ name, label, type = 'text', placeholder, value, error, onChange }) {
  return (
    <div>
      <label className="text-xs font-medium text-slate-400 mb-1.5 block">{label}</label>
      <input name={name} type={type} value={value} onChange={onChange}
        placeholder={placeholder}
        className={`w-full bg-surface border rounded-xl px-4 py-3 text-white text-sm
                    placeholder-slate-600 focus:outline-none focus:ring-2 transition-all
                    ${error
                      ? 'border-brand-500/60 focus:ring-brand-500/30'
                      : 'border-surface-border focus:ring-brand-500/50 focus:border-brand-500'}`} />
      {error && <p className="text-brand-600 text-xs mt-1">{error}</p>}
    </div>
  )
}

export default function RegisterPage() {
  const navigate   = useNavigate()
  const loginStore = useAuthStore((s) => s.login)
  const [form, setForm] = useState({ full_name: '', email: '', password: '', confirm: '' })
  const [busy, setBusy] = useState(false)
  const [errs, setErrs] = useState({})

  const handle = (e) => setForm(current => ({ ...current, [e.target.name]: e.target.value }))

  const validate = () => {
    const e = {}
    if (!form.full_name.trim())         e.full_name = 'Full name is required'
    if (!form.email.includes('@'))      e.email     = 'Enter a valid email'
    if (form.password.length < 6)       e.password  = 'Password must be at least 6 characters'
    if (form.password !== form.confirm) e.confirm   = 'Passwords do not match'
    return e
  }

  const submit = async (e) => {
    e.preventDefault()
    const v = validate()
    if (Object.keys(v).length) {
      setErrs(v)
      toast.error('Please correct the highlighted sign-up fields.')
      return
    }
    setBusy(true); setErrs({})
    try {
      const res = await register({ full_name: form.full_name, email: form.email, password: form.password })
      loginStore(res.data.access_token, res.data.user)
      toast.success('Account created! Welcome 🎉')
      navigate('/dashboard/certificates', { replace: true })
    } catch (e) {
      const message = getApiErrorMessage(e, 'Registration failed. Try again.')
      setErrs({ api: message })
      toast.error(message)
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md">

        <div className="text-center mb-8">
          <h1 className="font-display font-bold text-3xl text-white mb-2">
            Certify
          </h1>
          <p className="text-slate-400 text-sm">Create your account</p>
        </div>

        <div className="bg-surface-card border border-surface-border rounded-2xl p-8">
          <form onSubmit={submit} className="flex flex-col gap-5">

            {errs.api && (
              <div className="bg-brand-50 border border-brand-200 rounded-lg px-4 py-3
                              text-brand-600 text-sm">{errs.api}</div>
            )}

            <Field name="full_name" label="Full name" placeholder="Deekshith Gowda H. S."
              value={form.full_name} error={errs.full_name} onChange={handle} />
            <Field name="email" label="Email address" type="email" placeholder="you@example.com"
              value={form.email} error={errs.email} onChange={handle} />
            <Field name="password" label="Password" type="password" placeholder="Min 6 characters"
              value={form.password} error={errs.password} onChange={handle} />
            <Field name="confirm" label="Confirm password" type="password" placeholder="Re-enter password"
              value={form.confirm} error={errs.confirm} onChange={handle} />

            <motion.button type="submit" disabled={busy}
              whileTap={{ scale: 0.98 }}
              className="btn-primary w-full disabled:opacity-50 py-3 mt-2">
              {busy ? 'Creating account…' : 'Create account'}
            </motion.button>
          </form>

          <p className="text-center text-sm text-slate-500 mt-6">
            Already have an account?{' '}
            <Link to="/login" className="text-brand-400 hover:text-brand-300 font-medium">
              Sign in
            </Link>
          </p>
        </div>
        <AuthQuickLinks />
      </motion.div>
    </div>
  )
}
