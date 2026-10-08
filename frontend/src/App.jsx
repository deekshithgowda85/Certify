import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import toast, { Toaster } from 'react-hot-toast'
import { useAuthStore } from './store/authStore'
import { getApiErrorMessage } from './api/errors'
import ProtectedRoute from './components/ProtectedRoute'
import LoginPage      from './pages/LoginPage'
import RegisterPage   from './pages/RegisterPage'
import BulkCertificatesPage from './pages/BulkCertificatesPage'
import DashboardPage  from './pages/DashboardPage'
import ProfilePage    from './components/profile/ProfilePage'
import CertificatesPage from './components/certificates/CertificatesPage'
import MetricsPage     from './pages/MetricsPage'

const qc = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (error.response?.status !== 401) {
        toast.error(getApiErrorMessage(error, 'Could not load the requested data.'))
      }
    },
  }),
  defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
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
            <Route path="/bulk-certificates" element={<BulkCertificatesPage />} />
            <Route path="/bulk-certificates/public/:jobId?" element={<BulkCertificatesPage publicAccess />} />

            <Route path="/dashboard" element={
              <ProtectedRoute><DashboardPage /></ProtectedRoute>
            }>
              <Route index                element={<Navigate to="certificates" replace />} />
              <Route path="profile"       element={<ProfilePage />} />
              <Route path="certificates"  element={<CertificatesPage />} />
              <Route path="bulk-certificates" element={<BulkCertificatesPage />} />
            </Route>

            <Route path="/admin/metrics" element={<MetricsPage />} />

            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </AppInit>
      </BrowserRouter>

      <Toaster
        position="bottom-center"
        containerStyle={{ bottom: 'calc(1.5rem + env(safe-area-inset-bottom))' }}
        toastOptions={{
          style: {
            background: '#f9f9f7',
            color:      '#111111',
            border:     '1px solid #111111',
            borderRadius: '0px',
            fontSize:   '14px',
          },
          success: { iconTheme: { primary: '#cc0000', secondary: '#f9f9f7' } },
          error:   { iconTheme: { primary: '#cc0000', secondary: '#f9f9f7' } },
        }} />
    </QueryClientProvider>
  )
}
