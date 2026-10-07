import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { getApiErrorMessage } from '../../api/errors'
import { format } from 'date-fns'
import { getMe, updateMe } from '../../api/auth'
import { getJobs } from '../../api/certificates'
import { useAuthStore } from '../../store/authStore'
import StatsCard from './StatsCard'
import CertificateCard from '../certificates/CertificateCard'

function Avatar({ name, size = 'lg' }) {
  const init = (name || 'U').split(' ').map(p => p[0]?.toUpperCase()).join('').slice(0, 2)
  const sz   = size === 'lg' ? 'w-24 h-24 text-3xl' : 'w-12 h-12 text-lg'
  return (
    <div className={`${sz} rounded-full bg-primary
             flex items-center justify-center text-on-primary font-display font-bold flex-shrink-0`}>
      {init}
    </div>
  )
}

export default function ProfilePage() {
  const queryClient       = useQueryClient()
  const { updateUser }    = useAuthStore()
  const [editing, setEditing] = useState(false)
  const [nameVal, setNameVal] = useState('')

  const { data: me } = useQuery({
    queryKey: ['me'],
    queryFn:  () => getMe().then(r => r.data),
  })

  const { data: jobsData } = useQuery({
    queryKey: ['jobs'],
    queryFn:  () => getJobs().then(r => r.data),
  })

  const jobs = jobsData?.jobs ?? []
  const totalCerts   = jobs.reduce((s, j) => s + (j.success_count ?? 0), 0)
  const processing   = jobs.filter(j => j.status === 'PROCESSING').length
  const totalJobs    = jobs.length

  const mutation = useMutation({
    mutationFn: () => updateMe({ full_name: nameVal }),
    onSuccess: (res) => {
      updateUser(res.data)
      queryClient.invalidateQueries(['me'])
      toast.success('Name updated!')
      setEditing(false)
    },
    onError: (error) => toast.error(getApiErrorMessage(error, 'Update failed')),
  })

  const startEdit = () => {
    setNameVal(me?.full_name || '')
    setEditing(true)
  }

  return (
    <div className="min-h-full w-full p-4 sm:p-6 lg:p-8">
      <h2 className="font-display font-bold text-2xl text-white mb-8">Profile</h2>

      {/* Identity card */}
      <div className="bg-surface-card border border-surface-border rounded-2xl p-8 mb-6">
        <div className="flex items-start gap-6">
          <Avatar name={me?.full_name} />

          <div className="flex-1 min-w-0">
            <AnimatePresence mode="wait">
              {editing ? (
                <motion.div key="edit"
                  initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="flex items-center gap-3 mb-1">
                  <input
                    autoFocus
                    value={nameVal}
                    onChange={e => setNameVal(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && mutation.mutate()}
                    className="bg-surface border border-brand-500 rounded-xl px-4 py-2
                               text-white text-xl font-display font-bold focus:outline-none
                               focus:ring-2 focus:ring-brand-500/50 w-full max-w-sm" />
                  <motion.button whileTap={{ scale: 0.96 }}
                    onClick={() => mutation.mutate()}
                    disabled={mutation.isPending}
                    className="btn-primary text-sm px-4 py-2 flex-shrink-0">
                    {mutation.isPending ? 'Saving…' : 'Save'}
                  </motion.button>
                  <button onClick={() => setEditing(false)}
                    className="btn-secondary text-sm px-3 py-2 flex-shrink-0">
                    Cancel
                  </button>
                </motion.div>
              ) : (
                <motion.div key="view"
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                  className="flex items-center gap-3 mb-1">
                  <h3 className="font-display font-bold text-2xl text-white">
                    {me?.full_name || '—'}
                  </h3>
                  <button onClick={startEdit}
                    className="btn-quiet px-2 py-1 text-sm"
                    title="Edit name">
                    ✏️
                  </button>
                </motion.div>
              )}
            </AnimatePresence>

            <p className="text-slate-400 text-sm mb-1">{me?.email}</p>
            {me?.created_at && (
              <p className="text-slate-600 text-xs">
                Member since {format(new Date(me.created_at), 'MMMM yyyy')}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatsCard icon="📋" label="Total Jobs"            value={totalJobs}   color="brand"  />
        <StatsCard icon="🏆" label="Certificates Generated" value={totalCerts}  color="green"  />
        <StatsCard icon="⏳" label="Currently Processing"   value={processing}  color="yellow" />
      </div>

      <section className="mt-10">
        <div className="flex items-end justify-between gap-4 mb-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-600">Certificate history</p>
            <h3 className="font-display text-xl text-primary mt-1">All certificates</h3>
          </div>
          <span className="text-sm text-secondary">{jobs.length} total</span>
        </div>
        {jobs.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
            {jobs.map(job => <CertificateCard key={job.job_id} job={job} />)}
          </div>
        ) : (
          <div className="bg-surface-card border border-surface-border rounded-md p-6 text-sm text-secondary">
            Your certificate history will appear here after your first job is added.
          </div>
        )}
      </section>
    </div>
  )
}
