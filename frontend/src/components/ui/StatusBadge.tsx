import { clsx } from 'clsx'
import type { SessionStatus } from '@/types/session'

interface Props {
  status: SessionStatus
}

const config: Record<SessionStatus, { label: string; className: string }> = {
  running:          { label: 'running',  className: 'bg-green-900/40 text-green-400 border-green-700' },
  stopped:          { label: 'stopped',  className: 'bg-gray-900/40 text-gray-400 border-gray-700' },
  pending:          { label: 'pending',  className: 'bg-yellow-900/40 text-yellow-400 border-yellow-700' },
  error:            { label: 'error',    className: 'bg-red-900/40 text-red-400 border-red-700' },
  recovery_pending: { label: 'recovering', className: 'bg-purple-900/40 text-purple-400 border-purple-700' },
}

export function StatusBadge({ status }: Props) {
  const { label, className } = config[status] ?? config.error
  return (
    <span className={clsx('inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-mono', className)}>
      {label}
    </span>
  )
}
