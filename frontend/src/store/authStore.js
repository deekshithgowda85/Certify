import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { getMe } from '../api/auth'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user:            null,
      token:           null,
      isAuthenticated: false,

      login: (token, user) =>
        set({ token, user, isAuthenticated: true }),

      logout: () => {
        set({ token: null, user: null, isAuthenticated: false })
        window.location.href = '/login'
      },

      updateUser: (user) => set({ user }),

      initialize: async () => {
        const { token, logout, updateUser } = get()
        if (!token) return
        try {
          const res = await getMe()
          updateUser(res.data)
        } catch {
          logout()
        }
      },
    }),
    { name: 'auth', partialize: (s) => ({ token: s.token, user: s.user, isAuthenticated: s.isAuthenticated }) }
  )
)
