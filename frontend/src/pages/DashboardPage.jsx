import { Outlet, Navigate } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function DashboardPage() {
  return (
    <div className="flex min-h-screen bg-surface">
      <Sidebar />
      <main className="ml-60 min-h-screen flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
