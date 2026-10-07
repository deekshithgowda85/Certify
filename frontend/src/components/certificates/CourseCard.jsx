import { motion } from 'framer-motion'

export default function CourseCard({ course, onGenerate, certified, busy }) {
  return (
    <motion.div whileHover={{ y: -4, scale: 1.02 }} whileTap={{ scale: 0.98 }}
      transition={{ type: 'spring', stiffness: 300, damping: 20 }}
      className="bg-surface-card border border-surface-border rounded-2xl p-6
                 flex flex-col gap-4 relative overflow-hidden group">

      {/* certified badge */}
      {certified && (
        <span className="absolute top-3 right-3 bg-brand-50 border border-brand-200
             text-brand-600 text-xs font-semibold px-2 py-0.5 rounded-full">
          ✓ Certified
        </span>
      )}

      {/* subtle glow on hover */}
      <div className="absolute inset-0 bg-brand-500/5
                      opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      <img src={course.icon} alt="" className="h-12 w-12 object-contain" />

      <div className="flex-1">
        <h3 className="font-display font-semibold text-white text-base leading-snug mb-1">
          {course.name}
        </h3>
        <p className="text-slate-500 text-xs">{course.duration}</p>
      </div>

      <motion.button
        whileTap={{ scale: 0.96 }}
        onClick={() => onGenerate(course)}
        disabled={busy}
        className={`w-full py-2.5 text-sm transition-all
          ${certified
            ? 'btn-secondary'
            : 'btn-primary'
          } disabled:opacity-50`}>
        {busy ? 'Generating…' : certified ? 'Download Again' : 'Generate Certificate'}
      </motion.button>
    </motion.div>
  )
}
