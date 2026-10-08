import { motion } from 'framer-motion'

export default function StatsCard({ icon, label, value, color = 'brand' }) {
  const colors = {
    brand:  'bg-surface-card border-primary text-primary',
    green:  'bg-surface-card border-primary text-primary',
    yellow: 'bg-surface-card border-primary text-primary',
  }
  return (
    <motion.div className={`hard-shadow-hover ${colors[color]} border-b-4 p-5 flex flex-col gap-2`}>
      <span className="text-xs font-bold uppercase tracking-widest" aria-hidden="true">{icon}</span>
      <p className="font-mono text-3xl font-bold text-white tabular-nums">{value ?? '—'}</p>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
    </motion.div>
  )
}
