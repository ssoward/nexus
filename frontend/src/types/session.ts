export type SessionStatus = 'pending' | 'running' | 'stopped' | 'error' | 'recovery_pending'

export interface Session {
  id: string
  name: string
  image: string
  status: SessionStatus
  cols: number
  rows: number
  created_at: string
  last_active_at: string
}

export interface CreateSessionRequest {
  name: string
  image: string
  cols?: number
  rows?: number
}

export const PRESET_COMMANDS = [
  { value: 'bash',   label: 'Bash Shell',  description: 'Login shell with your full dotfiles and environment' },
  { value: 'zsh',    label: 'Zsh Shell',   description: 'Zsh login shell — use if zsh is your default shell' },
  { value: 'claude', label: 'Claude Code', description: 'Claude Code AI assistant CLI — orchestratable via Mastermind' },
  { value: 'python', label: 'Python 3',    description: 'Python 3 interactive REPL' },
] as const
