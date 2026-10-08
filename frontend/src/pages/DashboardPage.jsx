import { Outlet, Navigate } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

export default function DashboardPage() {
  return (
    <div className="newsprint-page flex min-h-screen bg-surface">
      <Sidebar />
      <main className="mt-[76px] min-h-[calc(100vh-76px)] flex-1 overflow-y-auto md:ml-60 md:mt-0 md:min-h-screen">
        <Outlet />
      </main>
    </div>
  )
}
