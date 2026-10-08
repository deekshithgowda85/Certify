import { motion } from 'framer-motion'
import { format } from 'date-fns'
import { downloadCertificate } from '../../api/certificates'
import { useAuthStore } from '../../store/authStore'
import { useState } from 'react'
import toast from 'react-hot-toast'

export default function CertificateCard({ job }) {
  const user = useAuthStore(s => s.user)
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await downloadCertificate(job.job_id, job.recipient_id, user?.full_name || 'certificate')
    } catch (error) {
      toast.error(error.message || 'Could not download the certificate.')
    } finally {
      setDownloading(false)
    }
  }

  const statusColor = {
    COMPLETED:         'text-secondary bg-surface border-surface-border',
    PARTIALLY_FAILED:  'text-secondary bg-surface border-surface-border',
    FAILED:            'text-brand-600 bg-brand-50 border-brand-200',
    PROCESSING:        'text-brand-400   bg-brand-500/10   border-brand-500/30',
    PENDING:           'text-slate-400   bg-slate-500/10   border-slate-500/30',
  }

  return (
    <motion.div className="hard-shadow-hover bg-surface-card p-5 flex flex-col gap-3">

      <div className="flex items-start justify-between gap-2">
        <h4 className="font-display font-semibold text-white text-sm leading-snug">{job.title}</h4>
        <span className={`border px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider flex-shrink-0
                          ${statusColor[job.status] ?? statusColor.PENDING}`}>
          {job.status}
        </span>
      </div>

      <div className="space-y-1 font-mono text-xs text-slate-500">
        <p>Mode: <span className="text-slate-400">{job.processing_mode ?? '—'}</span></p>
        <p>Generated: <span className="text-slate-400">
          {job.created_at ? format(new Date(job.created_at), 'dd MMM yyyy') : '—'}
        </span></p>
      </div>

      {job.status === 'COMPLETED' && (
        <motion.button whileTap={{ scale: 0.97 }} onClick={handleDownload}
          disabled={downloading || !job.recipient_id}
          title={!job.recipient_id ? 'Certificate recipient is not available' : undefined}
          className="btn-primary w-full text-xs py-2 disabled:opacity-50">
          {downloading ? 'Preparing PDF…' : 'Download PDF'}
        </motion.button>
      )}
    </motion.div>
  )
}
