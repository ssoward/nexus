interface Props {
  message: string
  onDismiss?: () => void
}

export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="flex items-center justify-between bg-red-900/30 border border-red-700 rounded px-3 py-2 text-sm text-red-300 font-mono">
      <span>{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="ml-4 text-red-400 hover:text-red-200">
          ✕
        </button>
      )}
    </div>
  )
}
