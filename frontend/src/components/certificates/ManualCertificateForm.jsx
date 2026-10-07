import { useState } from 'react'
import { motion } from 'framer-motion'
import { format } from 'date-fns'
import toast from 'react-hot-toast'

const initialForm = {
  title: '',
  name: '',
  email: '',
  course_name: '',
  completion_date: '',
}

export default function ManualCertificateForm({ user, busy, onClose, onSubmit }) {
  const [form, setForm] = useState(() => ({
    ...initialForm,
    completion_date: format(new Date(), 'yyyy-MM-dd'),
    name: user?.full_name || '',
    email: user?.email || '',
  }))
  const [error, setError] = useState('')

  const updateField = (event) => {
    const { name, value } = event.target
    setForm(current => ({ ...current, [name]: value }))
  }

  const submit = async (event) => {
    event.preventDefault()
    if (!Object.values(form).every(value => value.trim())) {
      setError('Complete every field before adding the job.')
      toast.error('Complete every field before adding the job.')
      return
    }
    setError('')
    await onSubmit(form)
  }

  const fields = [
    { name: 'title', label: 'Job title', placeholder: 'Spring completion cohort' },
    { name: 'name', label: 'Recipient name', placeholder: 'Avery Morgan' },
    { name: 'email', label: 'Recipient email', type: 'email', placeholder: 'avery@example.com' },
    { name: 'course_name', label: 'Course or program', placeholder: 'Advanced React' },
  ]

  return (
    <motion.div
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={event => event.target === event.currentTarget && onClose()}>
      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-lg max-h-[calc(100vh-2rem)] overflow-y-auto bg-surface-card border border-surface-border rounded-2xl p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4 mb-6">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-600">New certificate</p>
            <p className="text-sm text-secondary mt-2">Enter the recipient and completion details yourself.</p>
          </div>
          <button type="button" onClick={onClose} className="btn-quiet px-2 py-1 text-sm" aria-label="Close form">
            X
          </button>
        </div>

        <form onSubmit={submit} className="grid gap-4">
          {fields.map(field => (
            <label key={field.name} className="grid gap-1.5">
              <span className="text-xs font-bold uppercase tracking-[0.12em] text-secondary">{field.label}</span>
              <input
                name={field.name}
                type={field.type || 'text'}
                value={form[field.name]}
                onChange={updateField}
                placeholder={field.placeholder}
                className="w-full bg-surface border border-surface-border rounded-md px-3 py-2.5 text-primary text-sm focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
              />
            </label>
          ))}
          <label className="grid gap-1.5">
            <span className="text-xs font-bold uppercase tracking-[0.12em] text-secondary">Completion date</span>
            <input
              name="completion_date"
              type="date"
              value={form.completion_date}
              onChange={updateField}
              className="w-full bg-surface border border-surface-border rounded-md px-3 py-2.5 text-primary text-sm focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
            />
          </label>
          {error && <p className="text-brand-600 text-sm">{error}</p>}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary px-4 py-2 text-sm">Cancel</button>
            <button type="submit" disabled={busy} className="btn-primary px-4 py-2 text-sm disabled:opacity-50">
              {busy ? 'Adding job...' : 'Generating Certificate'}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  )
}
