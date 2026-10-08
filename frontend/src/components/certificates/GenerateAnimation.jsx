import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useJobPolling } from '../../hooks/useJobPolling'
import { downloadCertificate } from '../../api/certificates'
import { useAuthStore } from '../../store/authStore'
import toast from 'react-hot-toast'

function ConfettiBurst() {
  const colors  = ['#cc0000', '#111111', '#737373']
  const pieces  = Array.from({ length: 20 }, (_, i) => ({
    id: i,
    color: colors[i % colors.length],
    left:  `${10 + Math.random() * 80}%`,
    delay: Math.random() * 0.4,
    size:  6 + Math.random() * 6,
  }))

  return (
    <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-2xl">
      {pieces.map(p => (
        <div key={p.id} className="confetti-piece absolute"
          style={{
            left: p.left, top: '10%',
            width: p.size, height: p.size,
            backgroundColor: p.color,
            borderRadius: Math.random() > 0.5 ? '50%' : '2px',
            animationDelay: `${p.delay}s`,
          }} />
      ))}
    </div>
  )
}

function ProgressBar({ value }) {
  return (
    <div className="w-full bg-surface rounded-full h-2 overflow-hidden">
      <motion.div className="h-full bg-brand-600"
        initial={{ width: 0 }}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.6, ease: 'easeOut' }} />
    </div>
  )
}

function JobSteps({ status, mode }) {
  const currentStep = status === 'PENDING' ? 1 : status === 'PROCESSING' ? 2 : 3
  const labels = ['Preparing details', 'Job added', 'Certificate ready']
  const message = status === 'PENDING'
    ? 'Loading your certificate request.'
    : status === 'PROCESSING'
      ? mode === 'SANDBOX'
        ? 'Job added. Sending it through an isolated sandbox.'
        : 'Job added. Generating securely in the certificate worker.'
      : status === 'FAILED'
        ? 'The job could not be completed.'
        : 'Certificate generated successfully.'

  return (
    <div className="mb-7 text-left">
      <div className="flex items-center gap-2">
        {labels.map((label, index) => {
          const step = index + 1
          const complete = step < currentStep
          const active = step === currentStep
          return (
            <div key={label} className="flex min-w-0 flex-1 items-center gap-2">
              <motion.div
                animate={active ? { scale: [1, 1.12, 1] } : { scale: 1 }}
                transition={active ? { duration: 1.4, repeat: Infinity } : {}}
                className={`flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold
                  ${complete || active ? 'bg-brand-500 text-on-primary' : 'border border-surface-border text-secondary'}`}>
                {complete ? 'OK' : step}
              </motion.div>
              <span className={`truncate text-xs font-bold ${active || complete ? 'text-primary' : 'text-secondary'}`}>
                {label}
              </span>
              {step < labels.length && <span className="h-px flex-1 bg-surface-border" />}
            </div>
          )
        })}
      </div>
      <p className="mt-3 text-sm text-secondary">{message}</p>
    </div>
  )
}

export default function GenerateAnimation({ jobId, recipientId, onClose }) {
  const { job, error } = useJobPolling(jobId)
  const user = useAuthStore(s => s.user)
  const [downloading, setDownloading] = useState(false)
  const notifiedTerminalStatus = useRef(null)

  const pct = job
    ? Math.round((job.processed_count / Math.max(job.total_recipients, 1)) * 100)
    : 0

  const status = job?.status ?? (error?.response?.status === 404 ? 'FAILED' : 'PENDING')
  const mode = job?.processing_mode ?? 'INLINE'
  const done   = ['COMPLETED', 'PARTIALLY_FAILED', 'FAILED'].includes(status)
  const ok     = status === 'COMPLETED' || status === 'PARTIALLY_FAILED'

  useEffect(() => {
    if (!done || !job || notifiedTerminalStatus.current === status) return
    notifiedTerminalStatus.current = status
    if (status === 'COMPLETED') {
      toast.success('Certificate generated successfully.')
    } else if (status === 'PARTIALLY_FAILED') {
      toast(`Certificate job finished with ${job.failed_count} failed recipient(s).`, { icon: '⚠️' })
    } else {
      toast.error('Certificate generation failed.')
    }
  }, [done, job, status])

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await downloadCertificate(jobId, recipientId, user?.full_name || 'certificate')
    } catch (error) {
      toast.error(error.message || 'Could not download the certificate.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 20 }}
        className="hard-shadow-hover relative bg-surface-card border border-primary border-b-4 p-6 sm:p-8
                   w-full max-w-md text-center overflow-hidden">

        <JobSteps status={status} mode={mode} />

        <AnimatePresence mode="wait">

          {/* PENDING */}
          {status === 'PENDING' && (
            <motion.div key="pending" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <div className="w-16 h-16 mx-auto mb-4 rounded-full border-4 border-brand-600/30
                              border-t-brand-400 animate-spin" />
              <h3 className="font-display font-bold text-xl text-white mb-2">Adding your certificate job</h3>
              <div className="flex justify-center gap-1 mt-4">
                {[0,1,2].map(i => (
                  <motion.div key={i} className="w-2 h-2 rounded-full bg-brand-400"
                    animate={{ y: [0, -8, 0] }}
                    transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }} />
                ))}
              </div>
            </motion.div>
          )}

          {/* PROCESSING */}
          {status === 'PROCESSING' && (
            <motion.div key="processing" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <motion.div className="text-5xl mb-4"
                animate={{ rotate: [0, 10, -10, 0] }}
                transition={{ duration: 2, repeat: Infinity }}>
                ⚙️
              </motion.div>
              <h3 className="font-display font-bold text-xl text-white mb-1">Generating your certificate</h3>
              <p className="text-slate-400 text-sm mb-6">
                {mode === 'SANDBOX' ? 'Running in an isolated sandbox' : 'Processing securely'}
              </p>
              <ProgressBar value={pct} />
              <p className="text-brand-400 text-sm font-semibold mt-3">{pct}% complete</p>
              <p className="text-slate-600 text-xs mt-2">
                {job?.success_count ?? 0} done · {job?.failed_count ?? 0} failed
              </p>
            </motion.div>
          )}

          {/* COMPLETED / PARTIALLY_FAILED */}
          {ok && done && (
            <motion.div key="success" initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ type: 'spring', stiffness: 260, damping: 18 }}>
              <ConfettiBurst />
              <motion.div className="text-6xl mb-4"
                animate={{ y: [0, -12, 0] }}
                transition={{ duration: 1.5, repeat: Infinity, ease: 'easeInOut' }}>
                🎓
              </motion.div>
              <h3 className="font-display font-bold text-2xl text-white mb-2">Certificate ready!</h3>
              <p className="text-slate-400 text-sm mb-6">
                {status === 'PARTIALLY_FAILED'
                  ? `Generated with some issues (${job.failed_count} failed)`
                  : 'Your certificate has been generated successfully'}
              </p>
              <div className="flex flex-col gap-3">
                <motion.button whileTap={{ scale: 0.97 }} onClick={handleDownload} disabled={downloading}
                  className="btn-primary w-full py-3 disabled:opacity-50">
                  {downloading ? 'Preparing PDF…' : 'Download Certificate'}
                </motion.button>
                <button onClick={onClose} className="btn-secondary px-4 py-2 text-sm">
                  Close
                </button>
              </div>
            </motion.div>
          )}

          {/* FAILED */}
          {status === 'FAILED' && (
            <motion.div key="failed"
              animate={{ x: [0, -8, 8, -8, 8, 0] }}
              transition={{ duration: 0.4 }}>
              <div className="text-5xl mb-4">❌</div>
              <h3 className="font-display font-bold text-xl text-white mb-2">Generation failed</h3>
              <p className="text-slate-400 text-sm mb-6">
                {typeof error?.response?.data?.detail === 'string'
                  ? error.response.data.detail
                  : error?.message || 'Something went wrong. Please try again.'}
              </p>
              <button onClick={onClose} className="btn-secondary w-full py-3">
                Close
              </button>
            </motion.div>
          )}

        </AnimatePresence>
      </motion.div>
    </motion.div>
  )
}
