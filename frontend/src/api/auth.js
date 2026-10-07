import api from './axios'
export const register  = (d) => api.post('/api/v1/auth/register', d)
export const login     = (d) => api.post('/api/v1/auth/login', d)
export const getMe     = ()  => api.get('/api/v1/auth/me')
export const updateMe  = (d) => api.patch('/api/v1/auth/me', d)
