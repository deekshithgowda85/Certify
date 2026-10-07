import api from './axios'

export const getMetrics = () => api.get('/api/v1/admin/metrics')
