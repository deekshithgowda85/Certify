import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import { login } from '../api/auth'
import { getApiErrorMessage } from '../api/errors'
import { useAuthStore } from '../store/authStore'
import AuthQuickLinks from '../components/AuthQuickLinks'

export default function LoginPage() {
  const navigate   = useNavigate()
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
      navigate('/dashboard/certificates', { replace: true })
    } catch (e) {
      const message = getApiErrorMessage(e, 'Unable to sign in. Check your email and password and try again.')
      setErr(message)
      toast.error(message)
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen bg-surface flex items-center justify-center p-4">
      <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md">

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="font-display font-bold text-3xl text-white mb-2">
            Certify
          </h1>
          <p className="text-slate-400 text-sm">Sign in to your account</p>
        </div>

        <div className="bg-surface-card border border-surface-border rounded-2xl p-8">
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

          <p className="text-center text-sm text-slate-500 mt-6">
            No account?{' '}
            <Link to="/register" className="text-brand-400 hover:text-brand-300 font-medium">
              Create one
            </Link>
          </p>
        </div>
        <AuthQuickLinks />
      </motion.div>
    </div>
  )
}
