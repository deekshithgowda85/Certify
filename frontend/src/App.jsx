import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from './store/authStore'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage      from './pages/LoginPage'
import RegisterPage   from './pages/RegisterPage'
import DashboardPage  from './pages/DashboardPage'
import ProfilePage    from './components/profile/ProfilePage'
import CertificatesPage from './components/certificates/CertificatesPage'
import MetricsPage     from './pages/MetricsPage'

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } }
})

function AppInit({ children }) {
  const initialize = useAuthStore(s => s.initialize)
  useEffect(() => { initialize() }, [])
  return children
}

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <AppInit>
          <Routes>
            <Route path="/"         element={<Navigate to="/login" replace />} />
            <Route path="/login"    element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            <Route path="/dashboard" element={
              <ProtectedRoute><DashboardPage /></ProtectedRoute>
            }>
              <Route index                element={<Navigate to="certificates" replace />} />
              <Route path="profile"       element={<ProfilePage />} />
              <Route path="certificates"  element={<CertificatesPage />} />
            </Route>

            <Route path="/admin/metrics" element={<MetricsPage />} />

            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </AppInit>
      </BrowserRouter>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#ffffff',
            color:      '#0d0d0d',
            border:     '1px solid #d0d0d0',
            borderRadius: '6px',
            fontSize:   '14px',
          },
          success: { iconTheme: { primary: '#e60000', secondary: '#ffffff' } },
          error:   { iconTheme: { primary: '#e60000', secondary: '#ffffff' } },
        }} />
    </QueryClientProvider>
  )
}
