import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import {
  createBatch,
  createPublicBatch,
  downloadBatchAll,
  downloadPublicBatchAll,
  getBatchRecipients,
  getPublicBatchRecipients,
  regenerateBatch,
  regeneratePublicBatch,
} from '../api/certificates'
import { getApiErrorMessage } from '../api/errors'
import { parseRecipientCsv } from '../utils/recipientCsv'
import { useAuthStore } from '../store/authStore'
import { useJobPolling } from '../hooks/useJobPolling'

const DRAFT_KEY = 'bulk-certificate-draft'
const MAX_RECIPIENTS = 100000
const MAX_CSV_BYTES = 20 * 1024 * 1024
const PAGE_SIZE = 50
const RECIPIENT_PAGE_SIZE = 50
const MAX_SAVED_DRAFT_RECIPIENTS = 5000

function today() {
  return format(new Date(), 'yyyy-MM-dd')
}

function newRecipient() {
  return { name: '', email: '', course_name: '', completion_date: today() }
}

function loadDraft(key) {
  let savedDraft
  try {
    savedDraft = sessionStorage.getItem(key)
  } catch {
    return { title: '', recipients: [newRecipient()] }
  }

  try {
    const draft = JSON.parse(savedDraft || 'null')
    if (draft && Array.isArray(draft.recipients) && draft.recipients.length) {
      return {
        title: typeof draft.title === 'string' ? draft.title : '',
        recipients: draft.recipients.slice(0, MAX_RECIPIENTS).map(row => ({
          name: typeof row.name === 'string' ? row.name : '',
          email: typeof row.email === 'string' ? row.email : '',
          course_name: typeof row.course_name === 'string' ? row.course_name : '',
          completion_date: typeof row.completion_date === 'string' ? row.completion_date : today(),
        })),
      }
    }
  } catch {
    try {
      sessionStorage.removeItem(key)
    } catch {
      return { title: '', recipients: [newRecipient()] }
    }
  }
  return { title: '', recipients: [newRecipient()] }
}

export default function BulkCertificatesPage({ publicAccess = false }) {
  const navigate = useNavigate()
  const { jobId: routeJobId } = useParams()
  const draftKey = publicAccess ? DRAFT_KEY : `${DRAFT_KEY}-account`
  const user = useAuthStore(state => state.user)
  const token = useAuthStore(state => state.token)
  const [draft, setDraft] = useState(() => loadDraft(draftKey))
  const [busy, setBusy] = useState(false)
  const [submittedJobId, setSubmittedJobId] = useState(null)
  const jobId = routeJobId || submittedJobId
  const [jobTitle, setJobTitle] = useState('')
  const [failedRecipients, setFailedRecipients] = useState([])
  const [failedPage, setFailedPage] = useState(1)
  const [failedTotal, setFailedTotal] = useState(0)
  const [failedLoading, setFailedLoading] = useState(false)
  const [failedLoadError, setFailedLoadError] = useState('')
  const [resultLoading, setResultLoading] = useState(false)
  const [downloadLoading, setDownloadLoading] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [certificatesExpired, setCertificatesExpired] = useState(false)
  const [recipientPage, setRecipientPage] = useState(1)
  const submitLock = useRef(false)
  const csvInput = useRef(null)
  const finalizedJob = useRef(null)
  const storageWarningShown = useRef(false)
  const { job, loading: polling, restartPolling } = useJobPolling(jobId, publicAccess, true)
  const recipientPageCount = Math.max(1, Math.ceil(draft.recipients.length / RECIPIENT_PAGE_SIZE))
  const visibleRecipients = draft.recipients.slice(
    (recipientPage - 1) * RECIPIENT_PAGE_SIZE,
    recipientPage * RECIPIENT_PAGE_SIZE
  )

  useEffect(() => {
    if (recipientPage > recipientPageCount) setRecipientPage(recipientPageCount)
  }, [recipientPage, recipientPageCount])

  useEffect(() => {
    setCertificatesExpired(false)
  }, [jobId])

  useEffect(() => {
    if (draft.recipients.length > MAX_SAVED_DRAFT_RECIPIENTS) {
      try {
        sessionStorage.removeItem(draftKey)
      } catch {
        // The draft remains available in memory for the current page session.
      }
      if (!storageWarningShown.current) {
        storageWarningShown.current = true
        toast.error('This large recipient list cannot be saved in browser storage. Keep this tab open until you submit it.')
      }
      return
    }
    try {
      sessionStorage.setItem(draftKey, JSON.stringify(draft))
    } catch {
      if (!storageWarningShown.current) {
        storageWarningShown.current = true
        toast.error('This browser could not save your bulk draft. Keep this tab open until you submit it.')
      }
    }
  }, [draft, draftKey])

  useEffect(() => {
    if (!jobId || !job || !['COMPLETED', 'PARTIALLY_FAILED', 'FAILED'].includes(job.status)) return
    if (finalizedJob.current === jobId) return
    finalizedJob.current = jobId
    let cancelled = false

    const finalize = async () => {
      setResultLoading(true)
      setFailedPage(1)
      setFailedTotal(job.failed_count)
      setFailedLoadError('')
      if (job.failed_count > 0) {
        setFailedLoading(true)
        try {
          const getRecipients = publicAccess ? getPublicBatchRecipients : getBatchRecipients
          const response = await getRecipients(jobId, { status: 'FAILED', page: 1, size: PAGE_SIZE })
          if (!cancelled) setFailedRecipients(response.data.recipients)
        } catch (error) {
          if (!cancelled) {
            setFailedLoadError(getApiErrorMessage(error, 'Failed recipients could not be loaded.'))
            toast.error(getApiErrorMessage(error, 'Failed recipients could not be loaded.'))
          }
        } finally {
          if (!cancelled) setFailedLoading(false)
        }
      } else {
        if (!cancelled) {
          setFailedRecipients([])
        }
      }

      if (!cancelled && job.success_count === 0) {
        toast.error('No certificates were generated successfully, so there is no PDF to download.')
      }
      if (!cancelled) setResultLoading(false)
    }

    finalize()
    return () => {
      cancelled = true
    }
  }, [job, jobId, jobTitle, publicAccess])

  const loadFailedPage = async (page) => {
    setFailedLoading(true)
    setFailedLoadError('')
    try {
      const getRecipients = publicAccess ? getPublicBatchRecipients : getBatchRecipients
      const response = await getRecipients(jobId, { status: 'FAILED', page, size: PAGE_SIZE })
      setFailedRecipients(response.data.recipients)
      setFailedPage(page)
      setFailedTotal(response.data.total)
    } catch (error) {
      const message = getApiErrorMessage(error, 'Failed recipients could not be loaded.')
      setFailedLoadError(message)
      toast.error(message)
    } finally {
      setFailedLoading(false)
    }
  }

  const updateField = (index, field, value) => {
    setDraft(current => ({
      ...current,
      recipients: current.recipients.map((recipient, row) =>
        row === index ? { ...recipient, [field]: value } : recipient
      ),
    }))
  }

  const addRows = (count = 1) => {
    setDraft(current => {
      const available = MAX_RECIPIENTS - current.recipients.length
      const amount = Math.min(count, available)
      if (amount < count) toast.error(`A submission can contain at most ${MAX_RECIPIENTS.toLocaleString()} participants.`)
      return { ...current, recipients: [...current.recipients, ...Array.from({ length: amount }, newRecipient)] }
    })
  }

  const removeRow = (index) => {
    setDraft(current => ({
      ...current,
      recipients: current.recipients.length === 1
        ? [newRecipient()]
        : current.recipients.filter((_, row) => row !== index),
    }))
  }

  const importCsv = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    try {
      if (file.size > MAX_CSV_BYTES) throw new Error('The CSV file must be smaller than 20 MB.')
      const recipients = parseRecipientCsv(await file.text(), MAX_RECIPIENTS)
      setDraft(current => ({ ...current, recipients }))
      setRecipientPage(1)
      toast.success(`Imported ${recipients.length.toLocaleString()} participant(s).`)
    } catch (error) {
      toast.error(error.message || 'Could not import the CSV file.')
    }
  }

  const downloadCsvTemplate = () => {
    const content = 'name,email,course_name,completion_date\r\nAlex Morgan,alex@example.com,Introduction to Engineering,2026-10-01\r\n'
    const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = Object.assign(document.createElement('a'), { href: url, download: 'certificate-recipients-template.csv' })
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  const handleGenerate = async (event) => {
    event.preventDefault()
    if (submitLock.current) return
    if (!publicAccess && !token) {
      toast.error('Sign in or create an account to submit and track a bulk certificate job.')
      navigate('/login', { state: { from: '/bulk-certificates' } })
      return
    }
    if (!draft.title.trim()) {
      toast.error('Enter an event or job title before generating certificates.')
      return
    }
    if (!draft.recipients.length) {
      toast.error('Add at least one recipient before generating certificates.')
      return
    }

    submitLock.current = true
    setBusy(true)
    setFailedRecipients([])
    setFailedTotal(0)
    setFailedLoadError('')
    setSubmittedJobId(null)
    setCertificatesExpired(false)
    finalizedJob.current = null
    setJobTitle(draft.title.trim())
    try {
      const submitBatch = publicAccess ? createPublicBatch : createBatch
      const response = await submitBatch({
        title: draft.title.trim(),
        recipients: draft.recipients.map(recipient => ({
          ...recipient,
          name: recipient.name.trim(),
          email: recipient.email.trim(),
          course_name: recipient.course_name.trim(),
          client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        })),
      })
      setSubmittedJobId(response.data.batch_id)
      if (publicAccess) {
        navigate(`/bulk-certificates/public/${response.data.batch_id}`, { replace: true })
      } else {
        const basePath = window.location.pathname.startsWith('/dashboard/')
          ? '/dashboard/bulk-certificates'
          : '/bulk-certificates'
        navigate(`${basePath}/${response.data.batch_id}`, { replace: true })
      }
      toast.success(
        `Bulk batch queued as ${response.data.job_count} job(s) for ${response.data.valid_recipients} valid recipient(s).`
      )
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Could not submit the bulk certificate job.'))
    } finally {
      submitLock.current = false
      setBusy(false)
    }
  }

  const jobActive = jobId && (!job || !['COMPLETED', 'PARTIALLY_FAILED', 'FAILED'].includes(job.status))
  const signedIn = Boolean(token)
  const effectiveJobTitle = jobTitle || job?.title || 'certificates'
  const publicJobUrl = jobId ? `${window.location.origin}/bulk-certificates/public/${jobId}` : ''
  const downloadCombinedPdf = async () => {
    if (!jobId || downloadLoading) return
    setDownloadLoading(true)
    try {
      const download = publicAccess ? downloadPublicBatchAll : downloadBatchAll
      await download(jobId, effectiveJobTitle)
      toast.success(`Combined PDF downloaded with ${job?.success_count || 0} certificate(s).`)
    } catch (error) {
      if (error.response?.status === 410) setCertificatesExpired(true)
      toast.error(getApiErrorMessage(error, 'Could not download the combined PDF.'))
    } finally {
      setDownloadLoading(false)
    }
  }
  const handleRegenerate = async () => {
    if (!jobId || regenerating) return
    setRegenerating(true)
    try {
      const regenerate = publicAccess ? regeneratePublicBatch : regenerateBatch
      const response = await regenerate(jobId)
      setCertificatesExpired(false)
      finalizedJob.current = null
      setFailedRecipients([])
      setFailedTotal(0)
      setFailedPage(1)
      restartPolling()
      toast.success(
        `Queued ${response.data.recipients_to_regenerate.toLocaleString()} certificate(s) across ${response.data.job_count} job(s).`
      )
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Could not regenerate the certificates.'))
    } finally {
      setRegenerating(false)
    }
  }

  return (
    <main className="newsprint-page min-h-screen bg-surface px-4 py-6 text-primary sm:px-8 sm:py-8">
      <div className="mx-auto max-w-screen-xl">
        <header className="newsprint-masthead mb-6 flex flex-wrap items-end justify-between gap-5 pb-5">
          <div>
            <p className="newsprint-kicker mb-2">
              {publicAccess ? 'No-account bulk generation' : 'Bulk certificate generator'}
            </p>
            <p className="edition-stamp mb-3">Certificate desk · Batch edition · {format(new Date(), 'dd MMM yyyy')}</p>
            <h1 className="font-display text-4xl font-black leading-[0.95] tracking-tight text-primary sm:text-6xl">Generate certificates in bulk</h1>
            <p className="mt-3 max-w-3xl font-body text-sm leading-relaxed text-secondary sm:text-base">
              Submit up to 100,000 participants at once. The app splits them into 10,000-person queue jobs,
              tracks them together, and downloads successful certificates as one combined PDF.
            </p>
          </div>
          <nav className="flex flex-wrap items-center gap-3 text-sm">
            {publicAccess
              ? <Link className="btn-secondary px-4 py-2" to="/bulk-certificates">Account workspace</Link>
              : <Link className="btn-secondary px-4 py-2" to="/bulk-certificates/public">Continue without an account</Link>}
            {signedIn
              ? <Link className="btn-secondary px-4 py-2" to="/dashboard/certificates">Dashboard</Link>
              : !publicAccess && <>
                  <Link className="btn-secondary px-4 py-2" to="/login" state={{ from: '/bulk-certificates' }}>Sign in</Link>
                  <Link className="btn-primary px-4 py-2" to="/register" state={{ from: '/bulk-certificates' }}>Create account</Link>
                </>}
          </nav>
        </header>

        <div className="newsprint-inverted newsprint-ticker mb-6" aria-hidden="true">
          <div className="newsprint-ticker-track" aria-hidden="true">
            {Array.from({ length: 2 }, (_, index) => (
              <span key={index} className="newsprint-ticker-item">
                One submission <span className="text-brand-400">◆</span> Independent recipient validation <span className="text-brand-400">◆</span> One merged PDF <span className="text-brand-400">◆</span>
              </span>
            ))}
          </div>
        </div>

        {publicAccess && (
          <div className="mb-6 border-l-4 border-brand-500 border-y border-r border-primary bg-surface-card p-4 font-body text-sm leading-relaxed text-secondary">
            No account is needed to submit or download. Your private batch link grants access to its progress, failed-recipient details, and combined PDF; keep it private.
          </div>
        )}

        {!publicAccess && !signedIn && (
          <div className="mb-6 border-l-4 border-brand-500 border-y border-r border-primary bg-surface-card p-4 font-body text-sm leading-relaxed text-secondary">
            You can prepare the recipient list without signing in. Sign in or register when you generate;
            this page keeps your draft in this browser during that step.
          </div>
        )}

        <form onSubmit={handleGenerate} className="space-y-6">
          <section className="border border-primary bg-surface-card p-5 sm:p-6">
            <label className="grid max-w-2xl gap-2">
              <span className="text-xs font-bold uppercase tracking-wide text-secondary">Event or job title</span>
              <input
                required
                maxLength={255}
                value={draft.title}
                onChange={event => setDraft(current => ({ ...current, title: event.target.value }))}
                placeholder="Annual Developer Conference 2026"
                className="w-full rounded-lg border border-surface-border bg-surface px-4 py-3 text-primary focus:border-primary focus:outline-none"
              />
            </label>
          </section>

          <section className="overflow-hidden border border-primary bg-surface-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-border p-5">
              <div>
                <h2 className="font-display text-lg font-semibold text-primary">Recipients</h2>
                <p className="mt-1 text-sm text-secondary">{draft.recipients.length.toLocaleString()} participant(s); maximum {MAX_RECIPIENTS.toLocaleString()} per submission, processed in jobs of up to 10,000</p>
              </div>
              <div className="flex gap-2">
                <input
                  ref={csvInput}
                  type="file"
                  accept=".csv,text/csv"
                  onChange={importCsv}
                  className="hidden"
                  aria-label="Import participants from CSV"
                />
                <button type="button" disabled={jobActive || busy} onClick={() => csvInput.current?.click()}
                  className="btn-secondary px-3 py-2 text-sm disabled:opacity-50">Import CSV</button>
                <button type="button" disabled={jobActive || busy} onClick={downloadCsvTemplate}
                  className="btn-secondary px-3 py-2 text-sm disabled:opacity-50">CSV template</button>
                <button type="button" disabled={jobActive || busy} onClick={() => addRows(10)}
                  className="btn-secondary px-3 py-2 text-sm disabled:opacity-50">Add 10 rows</button>
                <button type="button" disabled={jobActive || busy} onClick={() => addRows()}
                  className="btn-primary px-3 py-2 text-sm disabled:opacity-50">+ Add recipient</button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] border-collapse text-left text-sm">
                <thead className="bg-surface">
                  <tr className="text-xs uppercase tracking-wide text-secondary">
                    <th className="px-4 py-3 font-semibold">#</th>
                    <th className="px-4 py-3 font-semibold">Participant name</th>
                    <th className="px-4 py-3 font-semibold">Email</th>
                    <th className="px-4 py-3 font-semibold">Course</th>
                    <th className="px-4 py-3 font-semibold">Completion date</th>
                    <th className="px-4 py-3 font-semibold">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRecipients.map((recipient, rowIndex) => {
                    const index = (recipientPage - 1) * RECIPIENT_PAGE_SIZE + rowIndex
                    return (
                      <tr key={index} className="border-t border-surface-border align-top">
                        <td className="px-4 py-3 text-secondary">{index + 1}</td>
                        {[
                          ['name', 'text', 'Full name'],
                          ['email', 'text', 'name@example.com'],
                          ['course_name', 'text', 'Course or program'],
                          ['completion_date', 'date', ''],
                        ].map(([field, type, placeholder]) => (
                          <td key={field} className="px-2 py-3">
                            <input
                              inputMode={field === 'email' ? 'email' : undefined}
                              maxLength={['name', 'email', 'course_name'].includes(field) ? 255 : undefined}
                              type={type}
                              value={recipient[field]}
                              placeholder={placeholder}
                              disabled={jobActive || busy}
                              onChange={event => updateField(index, field, event.target.value)}
                              aria-label={`${field.replace('_', ' ')} for recipient ${index + 1}`}
                              className="w-full min-w-40 rounded-md border border-surface-border bg-surface px-3 py-2 text-primary focus:border-primary focus:outline-none disabled:opacity-60"
                            />
                          </td>
                        ))}
                        <td className="px-4 py-3">
                          <button type="button" disabled={jobActive || busy} onClick={() => removeRow(index)}
                            className="rounded-md px-2 py-1 text-secondary hover:bg-surface-hover hover:text-primary disabled:opacity-50"
                            aria-label={`Remove recipient ${index + 1}`}>Remove</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {draft.recipients.length > RECIPIENT_PAGE_SIZE && (
              <div className="flex items-center justify-center gap-3 border-t border-surface-border p-3 text-sm text-secondary">
                <button type="button" disabled={recipientPage <= 1}
                  onClick={() => setRecipientPage(page => page - 1)}
                  className="btn-secondary px-3 py-2 disabled:opacity-50">Previous</button>
                <span>Showing {(recipientPage - 1) * RECIPIENT_PAGE_SIZE + 1}–{Math.min(recipientPage * RECIPIENT_PAGE_SIZE, draft.recipients.length)} of {draft.recipients.length.toLocaleString()}</span>
                <button type="button" disabled={recipientPage >= recipientPageCount}
                  onClick={() => setRecipientPage(page => page + 1)}
                  className="btn-secondary px-3 py-2 disabled:opacity-50">Next</button>
              </div>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-border p-5">
              <p className="text-xs text-secondary">Import replaces the current table. CSV headers: name, email, course_name, completion_date. Each participant is validated and processed independently.</p>
              <button type="submit" disabled={busy || jobActive}
                className="btn-primary px-5 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-50">
                {busy ? 'Submitting batch…' : jobActive ? 'Batch is processing…' : 'Generate certificates'}
              </button>
            </div>
          </section>
        </form>

        {jobId && (
          <section className="mt-6 rounded-2xl border border-surface-border bg-surface-card p-5 sm:p-6" aria-live="polite">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-semibold text-primary">Batch status: {job?.status || 'PENDING'}</h2>
                <p className="mt-1 text-sm text-secondary">{effectiveJobTitle} · Batch ID {jobId}</p>
              </div>
              {(polling || jobActive || resultLoading || failedLoading) && <span className="text-sm text-secondary">{failedLoading || resultLoading ? 'Preparing results and combined PDF…' : 'Refreshing progress…'}</span>}
            </div>
            {publicAccess && (
              <button
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(publicJobUrl)
                    toast.success('Private tracking link copied.')
                  } catch {
                    toast.error('Could not copy the tracking link; copy the URL from your browser.')
                  }
                }}
                className="btn-secondary mt-4 px-3 py-2 text-sm">
                Copy private tracking link
              </button>
            )}
            {job && (
              <>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-surface">
                  <div className="h-full bg-primary transition-all" style={{
                    width: `${Math.min(100, Math.round((job.processed_count / Math.max(job.total_recipients, 1)) * 100))}%`,
                  }} />
                </div>
                <p className="mt-2 text-sm text-secondary">
                  {job.processed_count} / {job.total_recipients} processed · {job.success_count} successful · {job.failed_count} failed
                </p>
              </>
            )}
            {failedLoadError && (
              <div className="mt-5 flex flex-wrap items-center gap-3 text-sm text-secondary">
                <span>{failedLoadError}</span>
                <button type="button" disabled={failedLoading} onClick={() => loadFailedPage(failedPage)}
                  className="btn-secondary px-3 py-2 disabled:opacity-50">Retry failed results</button>
              </div>
            )}
            {failedRecipients.length > 0 && (
              <div className="mt-5">
                <h3 className="text-sm font-semibold text-primary">
                  Failed recipient details ({failedTotal.toLocaleString()} total)
                </h3>
                <ul className="mt-2 max-h-64 space-y-2 overflow-y-auto text-sm text-secondary">
                  {failedRecipients.map(recipient => (
                    <li key={recipient.id} className="rounded-md border border-surface-border p-3">
                      <strong className="text-primary">{recipient.name || recipient.email || 'Recipient'}:</strong>{' '}
                      {recipient.error_message || 'Certificate generation failed.'}
                    </li>
                  ))}
                </ul>
                {failedTotal > PAGE_SIZE && (
                  <div className="mt-3 flex items-center gap-3 text-sm text-secondary">
                    <button type="button" disabled={failedLoading || failedPage <= 1}
                      onClick={() => loadFailedPage(failedPage - 1)}
                      className="btn-secondary px-3 py-2 disabled:opacity-50">Previous</button>
                    <span>Page {failedPage} of {Math.ceil(failedTotal / PAGE_SIZE)}</span>
                    <button type="button" disabled={failedLoading || failedPage >= Math.ceil(failedTotal / PAGE_SIZE)}
                      onClick={() => loadFailedPage(failedPage + 1)}
                      className="btn-secondary px-3 py-2 disabled:opacity-50">Next</button>
                  </div>
                )}
              </div>
            )}
            {job?.success_count > 0 && !jobActive && !resultLoading && (
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <button type="button" disabled={downloadLoading || regenerating} onClick={downloadCombinedPdf}
                  className="btn-secondary px-4 py-2 text-sm disabled:opacity-50">
                  {downloadLoading ? 'Preparing combined PDF…' : 'Download combined PDF'}
                </button>
                {certificatesExpired && (
                  <button type="button" disabled={regenerating || downloadLoading} onClick={handleRegenerate}
                    className="btn-primary px-4 py-2 text-sm disabled:opacity-50">
                    {regenerating ? 'Queueing certificates…' : 'Regenerate expired PDFs'}
                  </button>
                )}
                <span className="text-xs text-secondary">PDF files are automatically deleted after 10 minutes to keep storage available.</span>
              </div>
            )}
          </section>
        )}

        <footer className="mt-8 text-center text-xs text-secondary">
          {publicAccess
            ? 'No account is required. Keep your private batch URL to return to these results.'
            : user ? `Signed in as ${user.email}` : 'Sign in to submit and track account-owned bulk jobs.'}
        </footer>
      </div>
    </main>
  )
}
