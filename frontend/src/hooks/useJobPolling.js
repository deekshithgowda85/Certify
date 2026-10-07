import { useEffect, useState } from 'react'
import { getJob } from '../api/certificates'

const TERMINAL = ['COMPLETED', 'FAILED', 'PARTIALLY_FAILED']

export function useJobPolling(jobId) {
  const [job,     setJob]     = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!jobId) return
    setLoading(true)

    const poll = async () => {
      try {
        const res = await getJob(jobId)
        setJob(res.data)
        if (TERMINAL.includes(res.data.status)) {
          clearInterval(timer)
          setLoading(false)
        }
      } catch (e) {
        setError(e)
        clearInterval(timer)
        setLoading(false)
      }
    }

    poll()
    const timer = setInterval(poll, 2000)
    return () => clearInterval(timer)
  }, [jobId])

  return { job, loading, error }
}
