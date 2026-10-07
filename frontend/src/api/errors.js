export function getApiErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail.map(item => item.msg || item.error).filter(Boolean)
    return messages.length ? messages.join('; ') : fallback
  }
  if (detail && typeof detail === 'object') {
    const recipientErrors = Array.isArray(detail.errors)
      ? detail.errors.map(item => item.error).filter(Boolean)
      : []
    const messages = [detail.message, ...recipientErrors].filter(Boolean)
    if (messages.length) return messages.join(': ')
  }
  if (error?.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
  if (!error?.response) return 'Cannot reach the server. Check your connection and try again.'
  return error?.message || fallback
}
