import { useCallback, useEffect, useState } from 'react'
import { listPages, createPage, deletePage } from '@/api/pages'
import type { EmbeddedPage } from '@/types/page'
import { toast } from '@/store/toastStore'

interface Props {
  onClose?: () => void
  onSelectPage: (page: EmbeddedPage | null) => void
  activePage: EmbeddedPage | null
}

export function PageList({ onClose, onSelectPage, activePage }: Props) {
  const [pages, setPages] = useState<EmbeddedPage[]>([])
  const [showForm, setShowForm] = useState(false)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  const refresh = useCallback(async () => {
    try {
      setPages(await listPages())
    } catch { /* ignore */ }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleCreate = async () => {
    if (!name.trim() || !url.trim()) return
    try {
      const page = await createPage({ name: name.trim(), url: url.trim() })
      setPages((p) => [...p, page])
      setShowForm(false)
      setName('')
      setUrl('')
      onSelectPage(page)
    } catch {
      toast.error('Failed to create page')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deletePage(id)
      setPages((p) => p.filter((x) => x.id !== id))
      if (activePage?.id === id) onSelectPage(null)
      toast.success('Page deleted')
    } catch {
      toast.error('Failed to delete page')
    }
  }

  return (
    <aside className="w-full h-full flex flex-col bg-[#0d1117] border-r border-terminal-border">
      <div className="flex items-center justify-between px-3 py-2 border-b border-terminal-border shrink-0">
        <span className="text-xs font-mono text-terminal-fg/60 uppercase tracking-wider">Pages</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowForm(!showForm)}
            className="text-xs px-2 py-1 rounded bg-terminal-active/20 hover:bg-terminal-active/40 text-terminal-active font-mono"
          >
            + New
          </button>
          {onClose && (
            <button onClick={onClose} className="text-terminal-fg/40 hover:text-terminal-fg p-1 rounded" aria-label="Close">
              ✕
            </button>
          )}
        </div>
      </div>

      {showForm && (
        <div className="px-3 py-2 border-b border-terminal-border/50 space-y-1.5">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Page name"
            className="w-full px-2 py-1 text-xs font-mono bg-terminal-bg border border-terminal-border rounded text-terminal-fg"
          />
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://..."
            className="w-full px-2 py-1 text-xs font-mono bg-terminal-bg border border-terminal-border rounded text-terminal-fg"
          />
          <button
            onClick={handleCreate}
            className="w-full py-1 text-xs font-mono rounded bg-terminal-active/20 text-terminal-active"
          >
            Add Page
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {pages.length === 0 && (
          <p className="px-3 py-4 text-xs font-mono text-terminal-fg/30 text-center">No pages yet</p>
        )}
        {pages.map((page) => (
          <div
            key={page.id}
            className={`px-3 py-2 border-b border-terminal-border/50 cursor-pointer ${
              activePage?.id === page.id ? 'bg-terminal-active/10' : 'hover:bg-white/5'
            }`}
            onClick={() => onSelectPage(page)}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-mono text-terminal-fg truncate">{page.name}</span>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(page.id) }}
                className="text-terminal-fg/30 hover:text-red-400 text-xs ml-1"
              >
                ✕
              </button>
            </div>
            <p className="text-[10px] text-terminal-fg/30 font-mono truncate">{page.url}</p>
          </div>
        ))}
      </div>
    </aside>
  )
}
