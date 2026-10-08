import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
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
  const location   = useLocation()
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
      navigate(location.state?.from || '/dashboard/certificates', { replace: true })
    } catch (e) {
      const message = getApiErrorMessage(e, 'Registration failed. Try again.')
      setErrs({ api: message })
      toast.error(message)
    } finally { setBusy(false) }
  }

  return (
    <div className="newsprint-page flex min-h-screen items-center justify-center bg-surface px-4 py-8 sm:px-8">
      <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="grid w-full max-w-6xl grid-cols-1 items-center gap-8 lg:grid-cols-12 lg:gap-12">
        <section className="newsprint-texture border-y-4 border-primary py-8 lg:col-span-7 lg:border-y-0 lg:border-r lg:py-12 lg:pr-12">
          <div className="newsprint-masthead mb-6 flex items-end justify-between gap-4">
            <h1 className="font-display text-3xl font-black tracking-tight text-white sm:text-4xl">Certify</h1>
            <p className="edition-stamp text-right">The Certificate Desk<br />Vol. 01 · Digital Edition</p>
          </div>
          <p className="newsprint-kicker mb-4">A new chapter in recognition</p>
          <h2 className="font-display text-5xl font-black leading-[0.95] tracking-tighter text-primary sm:text-6xl lg:text-8xl">
            Make every<br />milestone count.
          </h2>
          <p className="mt-6 max-w-xl font-body text-base leading-relaxed text-secondary sm:text-lg">
            Open a workspace to issue certificates, follow every job, and keep your records together.
          </p>
          <div className="newsprint-inverted mt-8 grid grid-cols-3 divide-x divide-white/30 border border-primary">
            <div className="p-3 sm:p-4"><span className="newsprint-kicker">01</span><p className="mt-2 text-xs font-semibold uppercase tracking-wider text-white">Create</p></div>
            <div className="p-3 sm:p-4"><span className="newsprint-kicker">02</span><p className="mt-2 text-xs font-semibold uppercase tracking-wider text-white">Track</p></div>
            <div className="p-3 sm:p-4"><span className="newsprint-kicker">03</span><p className="mt-2 text-xs font-semibold uppercase tracking-wider text-white">Deliver</p></div>
          </div>
        </section>

        <section className="lg:col-span-5">
          <div className="mb-5">
            <p className="newsprint-kicker">Create an account</p>
            <h3 className="mt-2 font-display text-3xl font-bold text-primary">Join Certify</h3>
            <p className="mt-1 font-body text-sm text-secondary">Set up your certificate workspace.</p>
          </div>

        <div className="hard-shadow-hover border border-primary border-b-4 bg-surface-card p-6 sm:p-8">
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

          <p className="mt-6 text-center font-body text-sm text-slate-500">
            Already have an account?{' '}
            <Link to="/login" state={location.state} className="text-brand-400 hover:text-brand-300 font-medium">
              Sign in
            </Link>
          </p>
        </div>
        <p className="mt-5 text-center text-sm text-slate-500">
          Generating certificates for a group?{' '}
          <Link to="/bulk-certificates/public" className="text-brand-400 hover:text-brand-300 font-medium">
            Generate without an account
          </Link>
        </p>
        <AuthQuickLinks />
        </section>
      </motion.div>
    </div>
  )
}
