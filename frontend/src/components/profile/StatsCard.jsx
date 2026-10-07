import { motion } from 'framer-motion'

export default function StatsCard({ icon, label, value, color = 'brand' }) {
  const colors = {
    brand:  'bg-white border-brand-500 text-brand-600',
    green:  'bg-white border-surface-border text-primary',
    yellow: 'bg-white border-surface-border text-primary',
  }
  return (
    <motion.div whileHover={{ scale: 1.02 }} transition={{ type: 'spring', stiffness: 300 }}
      className={`${colors[color]} border rounded-2xl p-5 flex flex-col gap-2`}>
      <span className="text-2xl">{icon}</span>
      <p className="text-2xl font-display font-bold text-white">{value ?? '—'}</p>
      <p className="text-xs text-slate-400 font-medium">{label}</p>
    </motion.div>
  )
}
