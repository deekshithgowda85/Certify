import axios from 'axios'
import { getApiErrorMessage } from './errors'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : 'http://localhost:8000'),
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
})

const wait = (milliseconds) => new Promise(resolve => window.setTimeout(resolve, milliseconds))

function canRetry(config) {
  const method = config.method?.toLowerCase()
  if (['get', 'head', 'options'].includes(method)) return true
  const idempotencyKey = config.headers?.get?.('Idempotency-Key')
    || config.headers?.['Idempotency-Key']
    || config.headers?.['idempotency-key']
  return method === 'post'
    && config.url?.startsWith('/api/v1/jobs')
    && Boolean(idempotencyKey)
}

api.interceptors.request.use((config) => {
  const raw = localStorage.getItem('auth')
  if (raw) {
    try {
      const { state } = JSON.parse(raw)
      if (state?.token) config.headers.Authorization = `Bearer ${state.token}`
    } catch (_) {}
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('auth')
      window.location.href = '/login'
    }

    const config = err.config
    const status = err.response?.status
    const transient = !err.response || [408, 425, 502, 503, 504].includes(status)
    if (config && canRetry(config) && transient && (config.__retryCount || 0) < 1) {
      config.__retryCount = (config.__retryCount || 0) + 1
      await wait(300 * config.__retryCount)
      return api.request(config)
    }

    if (status === 429) err.message = getApiErrorMessage(err, 'Too many requests. Please wait and try again.')
    return Promise.reject(err)
  }
)

export default api
