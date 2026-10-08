import { motion } from 'framer-motion'

export default function CourseCard({ course, onGenerate, certified, busy, disabled }) {
  return (
    <motion.div whileTap={{ scale: 0.99 }}
      className="hard-shadow-hover bg-surface-card p-5 sm:p-6
                 flex flex-col gap-4 relative overflow-hidden group">

      {/* certified badge */}
      {certified && (
        <span className="absolute right-3 top-3 border border-brand-600 bg-brand-50
             px-2 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider text-brand-600">
          ✓ Certified
        </span>
      )}

      {/* subtle glow on hover */}
      <div className="absolute inset-0 bg-brand-500/5
                      opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

      <div className="flex h-12 w-12 items-center justify-center border border-primary bg-surface group-hover:bg-primary group-hover:text-white transition-colors">
        <img src={course.icon} alt="" className="h-8 w-8 object-contain grayscale transition-all group-hover:sepia-[50%]" />
      </div>

      <div className="flex-1">
        <h3 className="font-display font-bold text-white text-xl leading-snug mb-1">
          {course.name}
        </h3>
        <p className="font-mono text-xs uppercase tracking-wider text-slate-500">{course.duration}</p>
      </div>

      <motion.button
        whileTap={{ scale: 0.96 }}
        onClick={() => onGenerate(course)}
        disabled={busy || disabled}
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
