import api from './axios'

function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  if (globalThis.crypto?.getRandomValues) {
    return `${Date.now()}-${globalThis.crypto.getRandomValues(new Uint32Array(2)).join('-')}`
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const createJob = (d) => api.post('/api/v1/jobs', d, {
  headers: { 'Idempotency-Key': newIdempotencyKey() },
})
export const getJob    = (id) => api.get(`/api/v1/jobs/${id}`)
export const getJobs   = ()  => api.get('/api/v1/jobs')
export const getJobRecipients = (id, params) => api.get(`/api/v1/jobs/${id}/recipients`, { params })

const downloadBlob = (blob, name) => {
  const url = window.URL.createObjectURL(blob)
  const a = Object.assign(document.createElement('a'), { href: url })
  a.setAttribute('download', name)
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
}

const responseError = async (error) => {
  const data = error.response?.data
  if (data instanceof Blob) {
    try {
      const body = JSON.parse(await data.text())
      if (typeof body.detail === 'string') return body.detail
      if (typeof body.detail?.message === 'string') return body.detail.message
    } catch {
      // Retain the original request error when the response is not JSON.
    }
  } else if (typeof data?.detail === 'string') {
    return data.detail
  }
  return error.message || 'The download request failed.'
}

export const downloadCertificate = async (job_id, recipient_id, name) => {
  if (!job_id || !recipient_id) {
    throw new Error('Certificate details are not available yet. Refresh the certificates list and try again.')
  }
  let response
  try {
    response = await api.get(`/api/v1/jobs/${job_id}/certificates/${recipient_id}`, { responseType: 'blob' })
  } catch (error) {
    throw new Error(await responseError(error), { cause: error })
  }
  const signature = await response.data.slice(0, 5).text()
  if (signature !== '%PDF-') {
    throw new Error('The server response is not a valid PDF. Please try generating the certificate again.')
  }
  downloadBlob(response.data, `${name}_certificate.pdf`)
}

export const downloadAll = async (job_id, title) => {
  let response
  try {
    response = await api.get(`/api/v1/jobs/${job_id}/certificates/download-all`, { responseType: 'blob' })
  } catch (error) {
    throw new Error(await responseError(error), { cause: error })
  }
  const signature = await response.data.slice(0, 2).text()
  if (signature !== 'PK') {
    throw new Error('The server response is not a valid ZIP file.')
  }
  downloadBlob(response.data, `${title}_certificates.zip`)
}
