import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { format } from 'date-fns'
import { getMetrics } from '../api/metrics'

function StatusPill({ value }) {
  const normalized = String(value ?? 'unknown').toLowerCase()
  const healthy = ['ok', 'healthy', 'running', 'available'].includes(normalized)
  const warning = ['idle', 'unknown'].includes(normalized)
  return (
    <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-bold uppercase tracking-wide
      ${healthy ? 'border-surface-border bg-surface text-primary' : warning ? 'border-surface-border bg-surface text-secondary' : 'border-primary/30 bg-surface-hover text-primary'}`}>
      {value ?? 'unknown'}
    </span>
  )
}

const cardMotion = {
  whileHover: {},
}

function MetricCard({ label, value, detail, tone = 'text-primary' }) {
  return (
    <motion.div {...cardMotion} className="hard-shadow-hover border-r border-b border-primary bg-surface-card p-4 sm:p-5">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.14em] text-secondary">{label}</p>
      <p className={`font-mono text-3xl font-bold tabular-nums mt-3 ${tone}`}>{value}</p>
      <p className="mt-1 font-body text-sm text-secondary">{detail}</p>
    </motion.div>
  )
}

function ThroughputChart({ points = [], avg = {} }) {
  const max = Math.max(1, ...points.map(point => (point.inline || 0) + (point.sandbox || 0)))
  const hasActivity = points.some(point => (point.inline || 0) + (point.sandbox || 0) > 0)

  if (!points.length || !hasActivity) {
    return <p className="text-sm text-secondary">No certificate throughput has been recorded in the last 15 minutes.</p>
  }

  return (
    <div>
      <div className="flex h-40 items-end gap-1" role="img" aria-label="Successful certificates per minute over the last 15 minutes">
        {points.map((point, index) => {
          const inlineHeight = ((point.inline || 0) / max) * 100
          const sandboxHeight = ((point.sandbox || 0) / max) * 100
          return (
            <div key={`${point.minute}-${index}`} className="group relative flex h-full min-w-0 flex-1 flex-col justify-end"
              title={`${point.minute}: ${point.inline || 0} inline, ${point.sandbox || 0} sandbox`}>
              <div className="flex h-full flex-col justify-end overflow-hidden rounded-t-sm">
                <div className="bg-surface-border" style={{ height: `${inlineHeight}%` }} />
                <div className="bg-primary" style={{ height: `${sandboxHeight}%` }} />
              </div>
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex justify-between text-xs text-secondary">
        <span>{points[0].minute}</span>
        <span>{points[points.length - 1].minute}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-secondary">
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-surface-border" />Inline</span>
        <span><i className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-primary" />Sandbox</span>
        {Number.isFinite(avg.inline) && <span>Avg inline job: {avg.inline.toFixed(1)}s</span>}
        {Number.isFinite(avg.sandbox) && <span>Avg sandbox job: {avg.sandbox.toFixed(1)}s</span>}
        <span className="ml-auto">
          Total: {points.reduce((total, point) => total + (point.inline || 0) + (point.sandbox || 0), 0)} certificates
        </span>
      </div>
    </div>
  )
}

function JobProgress({ progress }) {
  const active = Boolean(progress && progress.total > 0)
  const processed = active ? progress.processed : 0
  const total = active ? progress.total : 0
  const percent = active ? Math.min(100, Math.max(0, (processed / total) * 100)) : 0
  const radius = 35
  const circumference = 2 * Math.PI * radius
  const ticks = Array.from({ length: 36 }, (_, index) => {
    const angle = (index * 10 * Math.PI) / 180
    return {
      x1: 50 + 42 * Math.cos(angle),
      y1: 50 + 42 * Math.sin(angle),
      x2: 50 + 45 * Math.cos(angle),
      y2: 50 + 45 * Math.sin(angle),
    }
  })

  return (
    <svg viewBox="0 0 100 100" className="h-24 w-24" role="img"
      aria-label={active ? `${processed} of ${total} certificates processed` : 'No active job progress'}>
      {ticks.map((tick, index) => (
        <line key={index} {...tick} stroke="#0d0d0d" strokeWidth="1.5" />
      ))}
      <circle cx="50" cy="50" r={radius} fill="none" stroke="#eeeeee" strokeWidth="8" />
      <circle cx="50" cy="50" r={radius} fill="none" stroke="#0d0d0d"
        strokeWidth="8" strokeLinecap="round" strokeDasharray={`${(percent / 100) * circumference} ${circumference}`}
        transform="rotate(-90 50 50)" />
      <text x="50" y="49" textAnchor="middle" fill="#0d0d0d" className="text-base font-bold">{active ? `${Math.round(percent)}%` : 'Ready'}</text>
      <text x="50" y="63" textAnchor="middle" fill="#6d6d6d" className="text-[8px]">{active ? `${processed}/${total}` : 'No job'}</text>
    </svg>
  )
}

function SandboxSlotCard({ slot }) {
  const isEmpty = !slot.container_id
  const cpu = Number.isFinite(slot.cpu_percent) ? Math.max(0, Math.min(100, slot.cpu_percent)) : null
  const usedMemory = Number.isFinite(slot.mem_used_mb) ? slot.mem_used_mb : null
  const memoryLimit = Number.isFinite(slot.mem_limit_mb) ? slot.mem_limit_mb : null
  const memoryPercent = usedMemory !== null && memoryLimit > 0
    ? Math.min(100, Math.max(0, (usedMemory / memoryLimit) * 100))
    : null
  const jobId = slot.job_id ? String(slot.job_id).slice(0, 8) : null

  return (
    <motion.article {...cardMotion}
      className={`hard-shadow-hover flex min-h-[205px] flex-col items-center gap-1.5 border-b border-r border-primary p-4 text-center text-primary
        ${isEmpty ? 'bg-surface' : 'bg-surface-card'}`}>
      <div className="flex w-full items-start justify-between gap-2 text-left">
        <span className="text-xs text-secondary">Slot {slot.slot}</span>
        <span className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase
          ${slot.health === 'healthy' ? 'border-surface-border text-primary' : ['unhealthy', 'stopped'].includes(slot.health) ? 'border-primary/40 text-primary' : 'border-surface-border text-secondary'}`}>
          <span className={`h-1.5 w-1.5 rounded-full ${slot.health === 'healthy' || slot.health === 'unhealthy' || slot.health === 'stopped' ? 'bg-primary' : 'bg-secondary'}`} />
          {slot.health || 'unknown'}
        </span>
      </div>

      <JobProgress progress={slot.job_progress} />
      <strong className="max-w-full truncate text-xs" title={slot.container_id || undefined}>
        {slot.container_id || (isEmpty ? 'Not running' : 'Container')}
      </strong>
      <span className="text-[11px] text-secondary">
        {jobId ? `Job ${jobId}` : isEmpty ? 'Waiting for pool startup' : 'Warm, no job assigned'}
      </span>

      <div className="mt-1 w-full">
        <div className="h-1.5 overflow-hidden bg-surface-border">
          <div className="h-full bg-brand-500" style={{ width: `${cpu ?? 0}%` }} />
        </div>
        <p className="mt-1 text-[10px] text-secondary">
          CPU {cpu === null ? '—' : `${cpu.toFixed(0)}%`}
          {' | '}
          {usedMemory === null
            ? 'Memory —'
            : `${Math.round(usedMemory)}${memoryLimit === null ? '' : ` / ${Math.round(memoryLimit)}`} MB`}
          {memoryPercent !== null && (
            <span className="sr-only"> ({Math.round(memoryPercent)}% memory used)</span>
          )}
        </p>
      </div>
    </motion.article>
  )
}

function QueueHistory({ points = [] }) {
  const width = 320
  const height = 88
  const max = Math.max(1, ...points)
  const coordinates = points.map((value, index) => ({
    x: points.length > 1 ? (index / (points.length - 1)) * width : width,
    y: height - 8 - (value / max) * (height - 16),
  }))
  const line = coordinates.map(({ x, y }, index) => `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = coordinates.length ? `${line} L${width},${height} L0,${height} Z` : ''

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="h-24 w-full"
        role="img" aria-label={`Queue depth for the last five minutes. Current ${points.at(-1) ?? 0}, peak ${Math.max(0, ...points)}.`}>
        <path d={area} fill="rgba(230, 0, 0, .12)" />
        <path d={line} fill="none" stroke="currentColor" className="text-primary" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-xs text-secondary">
        <span>5 min ago</span>
        <span>Now: {points.at(-1) ?? '—'} queued · Peak: {Math.max(0, ...points)}</span>
      </div>
    </div>
  )
}

function FailureBreakdown({ failures = [] }) {
  if (!failures.length) {
    return <p className="text-sm text-secondary">No failed certificates were recorded in the last 24 hours.</p>
  }
  const highestCount = Math.max(...failures.map(failure => failure.count || 0), 1)

  return (
    <ul className="space-y-4">
      {failures.map((failure, index) => (
        <li key={`${failure.message}-${index}`}>
          <div className="mb-1 flex items-start justify-between gap-3 text-sm">
            <span className="break-words text-secondary">{failure.message}</span>
            <strong className="shrink-0 text-primary">{failure.count}</strong>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-surface">
            <div className="h-full rounded-full bg-primary" style={{ width: `${((failure.count || 0) / highestCount) * 100}%` }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

function JobActivity({ events = [] }) {
  if (!events.length) {
    return <p className="text-sm text-secondary">No job updates have been recorded in the last 24 hours.</p>
  }

  return (
    <ul className="max-h-80 divide-y divide-surface-border overflow-y-auto">
      {events.map((event, index) => (
        <li key={`${event.ts}-${index}`} className="grid grid-cols-[5rem_0.5rem_1fr] items-baseline gap-3 py-3 text-sm">
          <time className="text-xs text-secondary">{event.ts ? format(new Date(event.ts), 'HH:mm:ss') : '—'}</time>
          <span className={`h-2 w-2 rounded-full ${event.level === 'error' ? 'bg-primary' : event.level === 'warn' ? 'bg-secondary' : 'bg-surface-border'}`} aria-label={event.level} />
          <span className="break-words text-primary">{event.text}</span>
        </li>
      ))}
    </ul>
  )
}

function SectionHeading({ eyebrow, title, detail }) {
  return (
    <div className="mb-4">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">{eyebrow}</p>
      <h3 className="font-display text-xl text-primary mt-1">{title}</h3>
      {detail && <p className="text-sm text-secondary mt-1">{detail}</p>}
    </div>
  )
}

function EmptyState({ children }) {
  return (
    <div className="border border-primary p-5 font-body text-sm text-secondary">
      {children}
    </div>
  )
}

export default function MetricsPage() {
  const [queueHistory, setQueueHistory] = useState([])
  const { data, isLoading, isError, isFetching, refetch } = useQuery({
    queryKey: ['admin-metrics'],
    queryFn: () => getMetrics().then(response => response.data),
    refetchInterval: 3000,
  })

  useEffect(() => {
    const depth = data?.queue?.pending
    if (typeof depth === 'number' && depth >= 0) {
      setQueueHistory(history => [...history, depth].slice(-100))
    }
  }, [data?.updated_at])

  if (isLoading) {
    return <div className="p-8 text-sm text-secondary">Loading system metrics...</div>
  }

  if (!data) {
    return (
      <div className="p-8">
        <div role="alert" className="border border-primary border-l-4 border-l-brand-500 bg-surface-card p-5 text-sm text-primary">
          <p>Metrics are currently unavailable. Check the API connection and try again.</p>
          <button type="button" onClick={() => refetch()} disabled={isFetching}
            className="btn-quiet mt-4 px-3 py-2 disabled:opacity-50">
            {isFetching ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      </div>
    )
  }

  const queue = data.queue || {}
  const sandboxes = data.sandboxes || {}
  const slots = sandboxes.slots || []
  const containers = data.containers || []
  const pending = typeof queue.pending === 'number' && queue.pending >= 0 ? queue.pending : '—'
  const failedJobs = queue.failed_24h ?? 0
  const updatedAt = data.updated_at && !Number.isNaN(new Date(data.updated_at).getTime())
    ? format(new Date(data.updated_at), 'HH:mm:ss')
    : '—'
  const services = data.services || {
    api: 'ok',
    db: 'unknown',
    redis: 'unknown',
    dispatcher: data.dispatcher?.status || 'unknown',
  }

  return (
    <div className="newsprint-page mx-auto max-w-screen-xl p-4 sm:p-6 lg:p-8">
      <header className="newsprint-masthead mb-6 flex flex-wrap items-end justify-between gap-4 pb-5">
        <div>
          <p className="newsprint-kicker">Operations desk · Live edition</p>
          <h2 className="font-display text-4xl font-black leading-none tracking-tight text-primary mt-2 sm:text-5xl">System metrics</h2>
          <p className="mt-3 font-body text-sm text-secondary">Live queue, certificate throughput, and worker health.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            {Object.entries(services).map(([service, status]) => (
              <span key={service} className="inline-flex min-h-[40px] items-center gap-2 border border-primary bg-surface-card px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-secondary">
                <span className={`h-2 w-2 ${['ok', 'healthy'].includes(String(status).toLowerCase()) ? 'bg-brand-500' : 'bg-secondary'}`} />
                <span className="capitalize">{service}</span>
                <strong className="font-semibold text-primary">{status}</strong>
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3 text-right text-xs text-secondary">
          <div>
            <StatusPill value={data.status} />
            <p className="mt-2">Updated {updatedAt}</p>
          </div>
          <button type="button" onClick={() => refetch()} disabled={isFetching}
            className="btn-quiet px-3 py-2 disabled:opacity-50" aria-label="Refresh metrics">
            {isFetching ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </header>

      <div className="newsprint-inverted newsprint-ticker mb-8" aria-hidden="true">
        <div className="newsprint-ticker-track" aria-hidden="true">
          {Array.from({ length: 2 }, (_, index) => (
            <span key={index} className="newsprint-ticker-item">
              Queue <span className="text-brand-400">{pending}</span> pending <span className="text-brand-400">◆</span> {sandboxes.active ?? 0} active sandboxes <span className="text-brand-400">◆</span> {failedJobs} failures in 24 hours <span className="text-brand-400">◆</span>
            </span>
          ))}
        </div>
      </div>

      {isError && (
        <div role="alert" className="mb-6 border border-primary border-l-4 border-l-brand-500 bg-surface-card p-4 text-sm text-primary">
          Could not refresh metrics. Showing the most recently received data.
        </div>
      )}

      <section className="mb-8">
        <SectionHeading eyebrow="Queue" title="Certificate jobs" detail={`Queue: ${queue.name || 'unknown'} · completed and failed job totals cover the last 24 hours.`} />
        <div className="grid gap-px border border-primary bg-primary sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <MetricCard label="Queued" value={pending} detail={queue.status || 'Queue depth unavailable'} tone="text-primary" />
          <MetricCard label="Processing" value={queue.processing ?? 0} detail="Jobs currently being processed" />
          <MetricCard label="Active sandboxes" value={sandboxes.active ?? 0} detail={`${sandboxes.capacity ?? 5} total capacity`} />
          <MetricCard label="Idle sandboxes" value={sandboxes.idle ?? 0} detail={`Dispatcher ${data.dispatcher?.status || 'unknown'}`} />
          <MetricCard label="Completed · 24h" value={queue.completed_24h ?? 0} detail="Jobs completed successfully" tone="text-primary" />
          <MetricCard label="Failed · 24h" value={failedJobs} detail="Failed or partially failed jobs"
            tone="text-primary" />
        </div>
        <motion.div {...cardMotion} className="hard-shadow-hover mt-4 border border-primary bg-surface-card p-5">
          <h4 className="mb-3 text-sm font-semibold text-primary">Queue depth · last 5 minutes</h4>
          <QueueHistory points={queueHistory} />
        </motion.div>
      </section>

      <section className="mb-8">
        <SectionHeading eyebrow="Activity" title="Certificate throughput" detail="Successfully generated certificates, grouped by processing mode." />
        <motion.div {...cardMotion} className="hard-shadow-hover border border-primary bg-surface-card p-5">
          <ThroughputChart points={data.throughput} avg={data.avg_seconds} />
        </motion.div>
      </section>

      <section className="mb-8">
        <SectionHeading eyebrow="Workers" title="Container status and health" detail="Live container details reported by the dispatcher." />
        {containers.length ? (
          <div className="overflow-x-auto border border-primary bg-surface-card">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-secondary">
                <tr className="border-b border-surface-border">
                  <th className="px-4 py-3 font-semibold">Container</th>
                  <th className="px-4 py-3 font-semibold">Role</th>
                  <th className="px-4 py-3 font-semibold">Job</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Health</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {containers.map(container => (
                  <tr key={container.id}>
                    <td className="px-4 py-3">
                      <span className="block font-semibold text-primary">{container.name || container.id}</span>
                      <span className="text-xs text-secondary">{container.id}</span>
                    </td>
                    <td className="px-4 py-3 text-secondary">{container.role || '—'}</td>
                    <td className="px-4 py-3 text-secondary">{container.job_id ? String(container.job_id).slice(0, 8) : '—'}</td>
                    <td className="px-4 py-3"><StatusPill value={container.status} /></td>
                    <td className="px-4 py-3"><StatusPill value={container.health} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <EmptyState>No warm sandbox containers are reported. Check dispatcher startup and Docker availability.</EmptyState>}
      </section>

      <section className="mb-8">
        <div className="border border-primary bg-surface-card p-5 sm:p-6">
          <div className="mb-5">
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-primary">Sandbox pool</p>
            <h3 className="mt-1 font-display text-xl text-primary">Sandboxes ({sandboxes.capacity ?? 5})</h3>
            <p className="mt-1 text-sm text-secondary">
              {data.pool?.busy ?? sandboxes.active ?? 0} busy, {data.pool?.idle ?? sandboxes.idle ?? 0} warm and ready.
              {' '}The pool keeps {data.pool?.min_idle ?? 0} warm and never exceeds {data.pool?.max_total ?? sandboxes.capacity ?? 5}.
              {data.pool?.status && data.pool.status !== 'healthy' && (
                <span className="ml-1 font-semibold text-primary" role="status">
                  Pool {data.pool.status}{data.pool.boot_errors ? ` (${data.pool.boot_errors} startup error${data.pool.boot_errors === 1 ? '' : 's'})` : ''}.
                </span>
              )}
            </p>
          </div>
          <div className="grid gap-px border border-primary bg-primary sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
          {slots.map(slot => (
            <SandboxSlotCard key={slot.id || slot.slot} slot={slot} />
          ))}
          </div>
        </div>
      </section>

      <section>
        <SectionHeading eyebrow="Activity" title="Throughput, failures, and job feed" detail="Certificate output by processing mode, common recipient failures, and latest job updates." />
        <div className="grid gap-px border border-primary bg-primary xl:grid-cols-2">
          <motion.div {...cardMotion} className="hard-shadow-hover border-r border-b border-primary bg-surface-card p-5">
            <h4 className="mb-4 text-sm font-semibold text-primary">Top failure reasons · 24h</h4>
            <FailureBreakdown failures={data.failures} />
          </motion.div>
          <motion.div {...cardMotion} className="hard-shadow-hover border-r border-b border-primary bg-surface-card p-5">
            <h4 className="mb-2 text-sm font-semibold text-primary">Recent job activity · 24h</h4>
            <JobActivity events={data.events} />
          </motion.div>
        </div>
      </section>
    </div>
  )
}
