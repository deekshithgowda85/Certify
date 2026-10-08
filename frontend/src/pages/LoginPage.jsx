import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { login } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/authStore'
import AuthQuickLinks from '../components/AuthQuickLinks'

export default function LoginPage() {
  const navigate   = useNavigate()
  const location   = useLocation()
  const loginStore = useAuthStore((s) => s.login)
  const [form, setForm]   = useState({ email: '', password: '' })
  const [busy, setBusy]   = useState(false)
  const [err,  setErr]    = useState('')

  const handle = (e) => setForm(current => ({ ...current, [e.target.name]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setErr('')
    try {
      const res = await login(form)
      loginStore(res.data.access_token, res.data.user)
      toast.success('Welcome back!')
      navigate(location.state?.from || '/dashboard/certificates', { replace: true })
    } catch (e) {
      const message = getApiErrorMessage(e, 'Unable to sign in. Check your email and password and try again.')
      setErr(message)
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
          <p className="newsprint-kicker mb-4">Credentials, clearly delivered</p>
          <h2 className="font-display text-5xl font-black leading-[0.95] tracking-tighter text-primary sm:text-6xl lg:text-8xl">
            Your work,<br />worth printing.
          </h2>
          <p className="mt-6 max-w-xl font-body text-base leading-relaxed text-secondary sm:text-lg">
            Create, track, and download certificates from a single, orderly workspace.
          </p>
          <div className="newsprint-inverted mt-8 grid grid-cols-3 divide-x divide-white/30 border border-primary">
            <div className="p-3 sm:p-4"><span className="newsprint-kicker">01</span><p className="mt-2 text-xs font-semibold uppercase tracking-wider text-white">Create</p></div>
            <div className="p-3 sm:p-4"><span className="newsprint-kicker">02</span><p className="mt-2 text-xs font-semibold uppercase tracking-wider text-white">Track</p></div>
            <div className="p-3 sm:p-4"><span className="newsprint-kicker">03</span><p className="mt-2 text-xs font-semibold uppercase tracking-wider text-white">Deliver</p></div>
          </div>
        </section>

        <section className="lg:col-span-5">
          <div className="mb-5">
            <p className="newsprint-kicker">Member access</p>
            <h3 className="mt-2 font-display text-3xl font-bold text-primary">Sign in</h3>
            <p className="mt-1 font-body text-sm text-secondary">Welcome back to your certificate workspace.</p>
          </div>

        <div className="hard-shadow-hover border border-primary border-b-4 bg-surface-card p-6 sm:p-8">
          <form onSubmit={submit} className="flex flex-col gap-5">

            {err && (
              <div className="bg-brand-50 border border-brand-200 rounded-lg px-4 py-3
                              text-brand-600 text-sm">{err}</div>
            )}

            <div>
              <label className="text-xs font-medium text-slate-400 mb-1.5 block">Email address</label>
              <input name="email" type="email" required value={form.email} onChange={handle}
                placeholder="you@example.com"
                className="w-full bg-surface border border-surface-border rounded-xl px-4 py-3
                           text-white text-sm placeholder-slate-600
                           focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500
                           transition-all" />
            </div>

            <div>
              <label className="text-xs font-medium text-slate-400 mb-1.5 block">Password</label>
              <input name="password" type="password" required value={form.password} onChange={handle}
                placeholder="••••••••"
                className="w-full bg-surface border border-surface-border rounded-xl px-4 py-3
                           text-white text-sm placeholder-slate-600
                           focus:outline-none focus:ring-2 focus:ring-brand-500/50 focus:border-brand-500
                           transition-all" />
            </div>

            <motion.button type="submit" disabled={busy}
              whileTap={{ scale: 0.98 }}
              className="btn-primary w-full disabled:opacity-50 py-3 mt-2">
              {busy ? 'Signing in…' : 'Sign in'}
            </motion.button>
          </form>

          <p className="mt-6 text-center font-body text-sm text-slate-500">
            No account?{' '}
            <Link to="/register" state={location.state} className="text-brand-400 hover:text-brand-300 font-medium">
              Create one
            </Link>
          </p>
        </div>
        <p className="mt-5 text-center font-body text-sm text-slate-500">
          Need to issue certificates for a group?{' '}
          <Link to="/bulk-certificates" state={{ from: '/bulk-certificates' }} className="text-brand-400 hover:text-brand-300 font-medium">
            Open the bulk certificate generator
          </Link>
        </p>
        <p className="mt-2 text-center font-body text-sm text-slate-500">
          <Link to="/bulk-certificates/public" className="text-brand-400 hover:text-brand-300 font-medium">
            Continue without an account
          </Link>
        </p>
        <AuthQuickLinks />
        </section>
      </motion.div>
    </div>
  )
}
