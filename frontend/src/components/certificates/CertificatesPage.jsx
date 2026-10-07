import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getApiErrorMessage } from '../../api/errors'
import { createJob, getJobs } from '../../api/certificates'
import { useAuthStore } from '../../store/authStore'
import CourseCard from './CourseCard'
import CertificateCard from './CertificateCard'
import GenerateAnimation from './GenerateAnimation'
import ManualCertificateForm from './ManualCertificateForm'
import { format } from 'date-fns'

const COURSES = [
  { id: 1, name: 'Python Bootcamp',         icon: '/Python.svg',       duration: '8 weeks'  },
  { id: 2, name: 'AWS Cloud Fundamentals',  icon: '/AWS.svg',          duration: '6 weeks'  },
  { id: 3, name: 'React for Beginners',     icon: '/React.svg',        duration: '4 weeks'  },
  { id: 4, name: 'Docker & DevOps',         icon: '/Docker.svg',       duration: '5 weeks'  },
  { id: 5, name: 'Machine Learning Basics', icon: '/scikit-learn.svg', duration: '10 weeks' },
  { id: 6, name: 'Java Spring Boot',        icon: '/Spring.svg',       duration: '7 weeks'  },
  { id: 7, name: 'Kubernetes Mastery',      icon: '/Kubernetes.svg',   duration: '6 weeks'  },
  { id: 8, name: 'Data Structures & Algo',  icon: '/Python.svg',       duration: '12 weeks' },
]

export default function CertificatesPage() {
  const user = useAuthStore(s => s.user)

  const [activeJobId,      setActiveJobId]      = useState(null)
  const [activeRecipientId, setActiveRecipientId] = useState(null)
  const [busyCourse,       setBusyCourse]       = useState(null)
  const [manualOpen,       setManualOpen]       = useState(false)
  const [manualBusy,       setManualBusy]       = useState(false)
  const [generationLocked, setGenerationLocked] = useState(false)
  const generationLockRef = useRef(false)

  const acquireGenerationLock = () => {
    if (generationLockRef.current) return false
    generationLockRef.current = true
    setGenerationLocked(true)
    return true
  }

  const releaseGenerationLock = () => {
    generationLockRef.current = false
    setGenerationLocked(false)
  }

  const { data: jobsData, refetch } = useQuery({
    queryKey: ['jobs'],
    queryFn:  () => getJobs().then(r => r.data),
    refetchInterval: activeJobId ? 3000 : false,
  })

  const jobs = jobsData?.jobs ?? []

  // Which courses have completed certs
  const certifiedCourses = new Set(
    jobs
      .filter(j => j.status === 'COMPLETED')
      .map(j => j.title)
  )

  const handleGenerate = async (course) => {
    if (!user || !acquireGenerationLock()) return
    setBusyCourse(course.id)
    try {
      const today = format(new Date(), 'yyyy-MM-dd')
      const res = await createJob({
        title: course.name,
        recipients: [{
          name:            user.full_name,
          email:           user.email,
          course_name:     course.name,
          completion_date: today,
          client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        }],
      })
      const jobId = res.data.job_id
      toast.success('Certificate request queued.')
      // grab recipient id from the first recipient (API should return it)
      const recipientId = res.data.recipient_id ?? null
      setActiveJobId(jobId)
      setActiveRecipientId(recipientId)
    } catch (e) {
      toast.error(getApiErrorMessage(e, 'Failed to start job'))
      setBusyCourse(null)
      releaseGenerationLock()
    }
  }

  const handleClose = () => {
    setActiveJobId(null)
    setActiveRecipientId(null)
    setBusyCourse(null)
    releaseGenerationLock()
    refetch()
  }

  const handleManualSubmit = async (form) => {
    if (!acquireGenerationLock()) return
    setManualBusy(true)
    let jobStarted = false
    try {
      const res = await createJob({
        title: form.title,
        recipients: [{
          name: form.name,
          email: form.email,
          course_name: form.course_name,
          completion_date: form.completion_date,
          client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        }],
      })
      setManualOpen(false)
      setActiveJobId(res.data.job_id)
      setActiveRecipientId(res.data.recipient_id ?? null)
      toast.success('Certificate request queued.')
      jobStarted = true
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Could not add certificate job'))
    } finally {
      setManualBusy(false)
      if (!jobStarted) releaseGenerationLock()
    }
  }

  const container = {
    hidden: {},
    show:   { transition: { staggerChildren: 0.07 } },
  }
  const item = {
    hidden: { opacity: 0, y: 20 },
    show:   { opacity: 1,  y: 0, transition: { type: 'spring', stiffness: 260, damping: 22 } },
  }

  return (
    <div className="p-8">

      {/* Header */}
      <div className="mb-10 flex items-end justify-between gap-4">
        <div>
          <h2 className="font-display font-bold text-2xl text-white mb-1">Certificates</h2>
          <p className="text-slate-400 text-sm">Choose a course or add a fully custom certificate job.</p>
        </div>
        <button type="button" onClick={() => setManualOpen(true)} disabled={generationLocked} className="btn-primary px-4 py-2.5 text-sm whitespace-nowrap disabled:opacity-50">
          + New certificate
        </button>
      </div>

      {/* Course grid */}
      <section className="mb-12">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-5">
          Available Courses
        </h3>
        <motion.div variants={container} initial="hidden" animate="show"
          className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {COURSES.map(course => (
            <motion.div key={course.id} variants={item}>
              <CourseCard
                course={course}
                certified={certifiedCourses.has(course.name)}
                busy={busyCourse === course.id}
                disabled={generationLocked}
                onGenerate={handleGenerate} />
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* Past certificates */}
      {jobs.length > 0 && (
        <section>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-5">
            Your Certificates
          </h3>
          <motion.div variants={container} initial="hidden" animate="show"
            className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {jobs.map(job => (
              <motion.div key={job.job_id} variants={item}>
                <CertificateCard job={job} />
              </motion.div>
            ))}
          </motion.div>
        </section>
      )}

      {/* Animation overlay */}
      {activeJobId && (
        <GenerateAnimation
          jobId={activeJobId}
          recipientId={activeRecipientId}
          onClose={handleClose} />
      )}

      <AnimatePresence>
        {manualOpen && (
          <ManualCertificateForm
            user={user}
            busy={manualBusy}
            onClose={() => {
              if (!generationLockRef.current) setManualOpen(false)
            }}
            onSubmit={handleManualSubmit} />
        )}
      </AnimatePresence>
    </div>
  )
}
