import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { getJob } from '../api/certificates'
import { getApiErrorMessage } from '../api/errors'

const TERMINAL = ['COMPLETED', 'FAILED', 'PARTIALLY_FAILED']

export function useJobPolling(jobId) {
  const [job,     setJob]     = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    let notified = false
    let polling = false
    setLoading(true)
    setError(null)
    setJob(null)

    const poll = async () => {
      if (polling) return
      polling = true
      try {
        const res = await getJob(jobId)
        if (cancelled) return
        setJob(res.data)
        setError(null)
        notified = false
        if (TERMINAL.includes(res.data.status)) {
          clearInterval(timer)
          setLoading(false)
        }
      } catch (e) {
        if (cancelled) return
        setError(e)
        if (e.response?.status === 404) {
          clearInterval(timer)
          setLoading(false)
          toast.error(getApiErrorMessage(e, 'The certificate job could not be found.'))
        } else if (!notified) {
          notified = true
          toast.error('Could not refresh job status. Retrying automatically.')
        }
      } finally {
        polling = false
      }
    }

    poll()
    const timer = setInterval(poll, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [jobId])

  return { job, loading, error }
}
