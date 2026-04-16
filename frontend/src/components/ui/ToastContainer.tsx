import { useToastStore } from '@/store/toastStore'
import type { Toast, ToastType } from '@/store/toastStore'

const ICONS: Record<ToastType, string> = {
  success: '✓',
  error:   '✕',
  warning: '⚠',
  info:    'ℹ',
}

const STYLES: Record<ToastType, string> = {
  success: 'border-green-600  bg-green-950/90  text-green-300',
  error:   'border-red-600    bg-red-950/90    text-red-300',
  warning: 'border-yellow-600 bg-yellow-950/90 text-yellow-300',
  info:    'border-blue-600   bg-blue-950/90   text-blue-300',
}

const ICON_STYLES: Record<ToastType, string> = {
  success: 'text-green-400',
  error:   'text-red-400',
  warning: 'text-yellow-400',
  info:    'text-blue-400',
}

function ToastItem({ toast }: { toast: Toast }) {
  const remove = useToastStore((s) => s.remove)

  return (
    <div
      className={`
        flex items-start gap-3 min-w-[280px] max-w-sm
        rounded border px-4 py-3
        shadow-lg font-mono text-sm
        animate-slide-in
        ${STYLES[toast.type]}
      `}
      role="alert"
    >
      <span className={`shrink-0 font-bold mt-px ${ICON_STYLES[toast.type]}`}>
        {ICONS[toast.type]}
      </span>
      <span className="flex-1 leading-snug">{toast.message}</span>
      <button
        onClick={() => remove(toast.id)}
        className="shrink-0 opacity-50 hover:opacity-100 transition-opacity ml-1 mt-px"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  )
}

export function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 items-end pointer-events-none">
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} />
        </div>
      ))}
    </div>
  )
}
