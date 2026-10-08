import { NavLink, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuthStore } from '../store/authStore'

const NAV = [
  { to: '/dashboard/profile',      label: 'Profile' },
  { to: '/dashboard/certificates', label: 'Certificates' },
  { to: '/dashboard/bulk-certificates', label: 'Bulk certificates' },
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
    <aside className="newsprint-inverted fixed inset-x-0 top-0 z-30 flex flex-row items-center justify-between
                      gap-2 border-b border-white/30 px-3 py-3 md:inset-y-0 md:left-0 md:h-screen md:w-60
                      md:flex-col md:items-stretch md:border-b-0 md:border-r md:px-4 md:py-6">
      {/* Logo */}
      <div className="px-1 md:mb-8 md:px-2">
        <h1 className="font-display font-bold text-xl text-white tracking-tight">
          Certify
        </h1>
        <p className="edition-stamp mt-0.5 !text-neutral-400 hidden md:block">Certificate Desk · Vol. 01</p>
      </div>

      {/* User */}
      <div className="hidden items-center gap-3 border-b border-white/30 px-2 pb-6 md:mb-8 md:flex">
        <Initials name={user?.full_name} />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white truncate">{user?.full_name || 'User'}</p>
          <p className="text-xs text-neutral-400 truncate">{user?.email}</p>
        </div>
      </div>

      {/* Nav */}
      <nav aria-label="Dashboard" className="flex min-w-0 flex-1 justify-start gap-1 overflow-x-auto md:flex-col md:justify-start">
        {NAV.map(({ to, label }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) =>
              `flex min-h-[44px] shrink-0 items-center gap-3 border-l-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors duration-150 md:text-sm
               ${isActive
                 ? 'border-brand-400 bg-white/10 text-white'
                 : 'border-transparent text-neutral-300 hover:bg-white/10 hover:text-white'}`
            }>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <motion.button
        whileTap={{ scale: 0.97 }}
        onClick={logout}
        className="btn-secondary ml-0 min-w-[44px] border-white px-2 text-[10px] text-white hover:!bg-white hover:!text-primary md:mt-4 md:justify-start md:px-3 md:text-xs">
        Logout
      </motion.button>
    </aside>
  )
}
