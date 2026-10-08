import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { format } from 'date-fns'
import {
  createJob,
  createPublicJob,
  downloadAll,
  downloadPublicAll,
  getJobRecipients,
  getPublicJobRecipients,
} from '../api/certificates'
import { getApiErrorMessage } from '../api/errors'
import { parseRecipientCsv } from '../utils/recipientCsv'
import { useAuthStore } from '../store/authStore'
import { useJobPolling } from '../hooks/useJobPolling'

const DRAFT_KEY = 'bulk-certificate-draft'
const MAX_RECIPIENTS = 10000
const MAX_CSV_BYTES = 20 * 1024 * 1024
const PAGE_SIZE = 100

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
  const jobId = publicAccess ? routeJobId || submittedJobId : submittedJobId
  const [jobTitle, setJobTitle] = useState('')
  const [failedRecipients, setFailedRecipients] = useState([])
  const [failedPage, setFailedPage] = useState(1)
  const [failedTotal, setFailedTotal] = useState(0)
  const [failedLoading, setFailedLoading] = useState(false)
  const [failedLoadError, setFailedLoadError] = useState('')
  const [resultLoading, setResultLoading] = useState(false)
  const submitLock = useRef(false)
  const csvInput = useRef(null)
  const finalizedJob = useRef(null)
  const storageWarningShown = useRef(false)
  const { job, loading: polling } = useJobPolling(jobId, publicAccess)

  useEffect(() => {
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
          const getRecipients = publicAccess ? getPublicJobRecipients : getJobRecipients
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

      if (!cancelled && job.success_count > 0) {
        try {
          const download = publicAccess ? downloadPublicAll : downloadAll
          await download(jobId, jobTitle || job.title)
          if (!cancelled) toast.success(`ZIP downloaded with ${job.success_count} certificate(s).`)
        } catch (error) {
          if (!cancelled) toast.error(getApiErrorMessage(error, 'The job finished, but its ZIP could not be downloaded.'))
        }
      } else if (!cancelled) {
        toast.error('No certificates were generated successfully, so there is no ZIP to download.')
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
      const getRecipients = publicAccess ? getPublicJobRecipients : getJobRecipients
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
      if (amount < count) toast.error(`A batch can contain at most ${MAX_RECIPIENTS.toLocaleString()} recipients.`)
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
    finalizedJob.current = null
    setJobTitle(draft.title.trim())
    try {
      const submitJob = publicAccess ? createPublicJob : createJob
      const response = await submitJob({
        title: draft.title.trim(),
        recipients: draft.recipients.map(recipient => ({
          ...recipient,
          name: recipient.name.trim(),
          email: recipient.email.trim(),
          course_name: recipient.course_name.trim(),
          client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
        })),
      })
      setSubmittedJobId(response.data.job_id)
      if (publicAccess) {
        navigate(`/bulk-certificates/public/${response.data.job_id}`, { replace: true })
      }
      toast.success(`Bulk job queued for ${response.data.valid_recipients} recipient(s).`)
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
              Enter the event details and add as many recipients as needed. One request queues the batch;
              completed PDFs are packaged into a ZIP download.
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
                One submission <span className="text-brand-400">◆</span> Independent recipient validation <span className="text-brand-400">◆</span> PDF certificates in a ZIP <span className="text-brand-400">◆</span>
              </span>
            ))}
          </div>
        </div>

        {publicAccess && (
          <div className="mb-6 border-l-4 border-brand-500 border-y border-r border-primary bg-surface-card p-4 font-body text-sm leading-relaxed text-secondary">
            No account is needed to submit or download. Your private job link grants access to its progress, recipient details, and certificates; keep it private.
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
                <p className="mt-1 text-sm text-secondary">{draft.recipients.length.toLocaleString()} row(s); maximum {MAX_RECIPIENTS.toLocaleString()} per request</p>
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
                  {draft.recipients.map((recipient, index) => (
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
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-border p-5">
              <p className="text-xs text-secondary">Import replaces the current table. CSV headers: name, email, course_name, completion_date. Each participant is validated and processed independently.</p>
              <button type="submit" disabled={busy || jobActive}
                className="btn-primary px-5 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-50">
                {busy ? 'Submitting batch…' : jobActive ? 'Batch is processing…' : 'Generate PDFs and download ZIP'}
              </button>
            </div>
          </section>
        </form>

        {jobId && (
          <section className="mt-6 rounded-2xl border border-surface-border bg-surface-card p-5 sm:p-6" aria-live="polite">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-lg font-semibold text-primary">Batch status: {job?.status || 'PENDING'}</h2>
                <p className="mt-1 text-sm text-secondary">{effectiveJobTitle} · Job ID {jobId}</p>
              </div>
              {(polling || jobActive || resultLoading || failedLoading) && <span className="text-sm text-secondary">{failedLoading || resultLoading ? 'Preparing results and ZIP…' : 'Refreshing progress…'}</span>}
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
              <button type="button" onClick={() => (publicAccess ? downloadPublicAll : downloadAll)(jobId, effectiveJobTitle).catch(error =>
                toast.error(getApiErrorMessage(error, 'Could not download the ZIP.'))
              )} className="btn-secondary mt-5 px-4 py-2 text-sm">
                Download ZIP again
              </button>
            )}
          </section>
        )}

        <footer className="mt-8 text-center text-xs text-secondary">
          {publicAccess
            ? 'No account is required. Keep your private job URL to return to these results.'
            : user ? `Signed in as ${user.email}` : 'Sign in to submit and track account-owned bulk jobs.'}
        </footer>
      </div>
    </main>
  )
}
