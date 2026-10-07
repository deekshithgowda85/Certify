import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuthStore } from '../store/authStore'

const NAV = [
  { to: '/dashboard/profile',      label: 'Profile' },
  { to: '/dashboard/certificates', label: 'Certificates' },
]

function Initials({ name }) {
  const parts = (name || 'U').split(' ')
  const init  = parts.map((p) => p[0]?.toUpperCase()).join('').slice(0, 2)
  return (
    <div className="w-10 h-10 rounded-full bg-primary
            flex items-center justify-center text-on-primary font-display font-bold text-sm flex-shrink-0">
      {init}
    </div>
  )
}

export default function Sidebar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  return (
    <aside className="fixed inset-y-0 left-0 z-30 h-screen w-60 bg-surface-card border-r border-surface-border
                      flex flex-col py-6 px-4 flex-shrink-0">
      {/* Logo */}
      <div className="mb-8 px-2">
        <h1 className="font-display font-bold text-xl text-white tracking-tight">
          Certify
        </h1>
        <p className="text-xs text-slate-500 mt-0.5">Certificate Generator</p>
      </div>

      {/* User */}
      <div className="flex items-center gap-3 px-2 mb-8 pb-6 border-b border-surface-border">
        <Initials name={user?.full_name} />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white truncate">{user?.full_name || 'User'}</p>
          <p className="text-xs text-slate-500 truncate">{user?.email}</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 flex-1">
        {NAV.map(({ to, label }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150
               ${isActive
                 ? 'bg-surface-hover text-primary border-l-2 border-primary pl-[10px]'
                 : 'text-slate-400 hover:bg-primary hover:text-on-primary'}`
            }>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <motion.button
        whileTap={{ scale: 0.97 }}
        onClick={logout}
        className="btn-secondary flex items-center gap-3 px-3 py-2.5 text-sm mt-4">
        Logout
      </motion.button>
    </aside>
  )
}
