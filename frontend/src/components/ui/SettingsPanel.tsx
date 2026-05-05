import { useState, useEffect, useCallback } from 'react'
import { startRegistration } from '@simplewebauthn/browser'
import {
  changePassword,
  changeEmail,
  deleteAccount,
  registerPasskeyBegin,
  registerPasskeyComplete,
  listPasskeyCredentials,
  deletePasskeyCredential,
  getMe,
} from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { useIsMobile } from '@/hooks/useIsMobile'
import type { PasskeyCredential } from '@/types/auth'

interface Props {
  onClose?: () => void
}

type Section = 'profile' | 'security' | 'passkeys' | 'danger'

function SectionHeader({ label, mobile }: { label: string; mobile: boolean }) {
  return (
    <p className={`${mobile ? 'text-xs' : 'text-[10px]'} font-mono uppercase tracking-widest text-terminal-fg/40 mb-3 mt-5 first:mt-0`}>
      {label}
    </p>
  )
}

function StatusBadge({ label, variant, mobile }: { label: string; variant: 'green' | 'blue' | 'yellow' | 'gray'; mobile: boolean }) {
  const colors = {
    green: 'text-green-400 bg-green-900/20 border-green-800/40',
    blue: 'text-blue-400 bg-blue-900/20 border-blue-800/40',
    yellow: 'text-yellow-400 bg-yellow-900/20 border-yellow-800/40',
    gray: 'text-terminal-fg/40 bg-terminal-border/20 border-terminal-border/40',
  }
  return (
    <span className={`${mobile ? 'text-xs' : 'text-[10px]'} font-mono px-1.5 py-0.5 rounded border ${colors[variant]}`}>
      {label}
    </span>
  )
}

function FieldInput({
  label, type = 'text', value, onChange, placeholder, hint, mobile,
}: {
  label: string; type?: string; value: string; onChange: (v: string) => void
  placeholder?: string; hint?: string; mobile: boolean
}) {
  return (
    <div>
      <label className={`block ${mobile ? 'text-xs' : 'text-[10px]'} font-mono text-terminal-fg/50 mb-1`}>{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className={`w-full bg-terminal-bg border border-terminal-border rounded px-3 py-1.5 ${mobile ? 'text-sm' : 'text-xs'} font-mono text-terminal-fg focus:outline-none focus:border-terminal-active`}
      />
      {hint && <p className={`${mobile ? 'text-xs' : 'text-[10px]'} font-mono text-terminal-fg/30 mt-0.5`}>{hint}</p>}
    </div>
  )
}

export function SettingsPanel({ onClose }: Props) {
  const { user, setUser } = useAuthStore()
  const isMobile = useIsMobile()
  const [activeSection, setActiveSection] = useState<Section>('profile')

  // ── Profile / change-email ─────────────────────────────────────────
  const [newEmail, setNewEmail] = useState('')
  const [emailPw, setEmailPw] = useState('')
  const [emailMsg, setEmailMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [emailLoading, setEmailLoading] = useState(false)

  const handleChangeEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newEmail || !emailPw) return
    setEmailLoading(true); setEmailMsg(null)
    try {
      const res = await changeEmail(emailPw, newEmail)
      const me = await getMe()
      setUser(me)
      setEmailMsg({ ok: true, text: `Email updated to ${res.username}` })
      setNewEmail(''); setEmailPw('')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string }; status?: number } }).response
      if (detail?.status === 409) setEmailMsg({ ok: false, text: 'Email already in use.' })
      else if (detail?.status === 401) setEmailMsg({ ok: false, text: 'Password is incorrect.' })
      else setEmailMsg({ ok: false, text: 'Failed to update email.' })
    } finally { setEmailLoading(false) }
  }

  // ── Change password ────────────────────────────────────────────────
  const [curPw, setCurPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [pwLoading, setPwLoading] = useState(false)

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!curPw || !newPw || !confirmPw) return
    if (newPw !== confirmPw) { setPwMsg({ ok: false, text: 'New passwords do not match.' }); return }
    setPwLoading(true); setPwMsg(null)
    try {
      await changePassword(curPw, newPw)
      setPwMsg({ ok: true, text: 'Password updated successfully.' })
      setCurPw(''); setNewPw(''); setConfirmPw('')
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string }; status?: number } }).response
      if (detail?.status === 401) setPwMsg({ ok: false, text: 'Current password is incorrect.' })
      else if (detail?.status === 422) {
        const d = detail.data?.detail
        if (Array.isArray(d)) setPwMsg({ ok: false, text: d.map((x: { msg?: string }) => x.msg ?? '').join(' ') })
        else setPwMsg({ ok: false, text: typeof d === 'string' ? d : 'Password does not meet requirements.' })
      }
      else setPwMsg({ ok: false, text: 'Failed to update password.' })
    } finally { setPwLoading(false) }
  }

  // ── Passkeys ───────────────────────────────────────────────────────
  const [passkeys, setPasskeys] = useState<PasskeyCredential[]>([])
  const [passkeyName, setPasskeyName] = useState('')
  const [passkeyMsg, setPasskeyMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [passkeyLoading, setPasskeyLoading] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const loadPasskeys = useCallback(async () => {
    try { setPasskeys(await listPasskeyCredentials()) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (activeSection === 'passkeys') loadPasskeys()
  }, [activeSection, loadPasskeys])

  const handleAddPasskey = async () => {
    setPasskeyLoading(true); setPasskeyMsg(null)
    try {
      const options = await registerPasskeyBegin()
      const credential = await startRegistration({ optionsJSON: options })
      await registerPasskeyComplete(credential, passkeyName || undefined)
      setPasskeyMsg({ ok: true, text: 'Passkey registered successfully.' })
      setPasskeyName('')
      await loadPasskeys()
      setUser(await getMe())
    } catch (err: unknown) {
      const name = (err as { name?: string }).name
      if (name === 'NotAllowedError') setPasskeyMsg({ ok: false, text: 'Biometric cancelled or not allowed.' })
      else if (name === 'InvalidStateError') setPasskeyMsg({ ok: false, text: 'This passkey is already registered.' })
      else setPasskeyMsg({ ok: false, text: 'Failed to register passkey. Try again.' })
    } finally { setPasskeyLoading(false) }
  }

  const handleDeletePasskey = async (id: number) => {
    setDeletingId(id); setPasskeyMsg(null)
    try {
      await deletePasskeyCredential(id)
      await loadPasskeys()
      setUser(await getMe())
    } catch {
      setPasskeyMsg({ ok: false, text: 'Failed to delete passkey.' })
    } finally { setDeletingId(null) }
  }

  // ── Delete account ─────────────────────────────────────────────────
  const [deletePw, setDeletePw] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleteMsg, setDeleteMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)

  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    if (deleteConfirm !== 'delete my account') {
      setDeleteMsg({ ok: false, text: 'Type "delete my account" to confirm.' }); return
    }
    setDeleteLoading(true); setDeleteMsg(null)
    try {
      await deleteAccount(deletePw)
      window.location.href = '/login'
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } }).response?.status
      setDeleteMsg({ ok: false, text: status === 401 ? 'Password is incorrect.' : 'Failed to delete account.' })
    } finally { setDeleteLoading(false) }
  }

  const mfaLabel = () => {
    if (!user?.mfa_method) return { label: 'None', variant: 'gray' as const }
    if (user.mfa_method === 'passkey') return { label: 'Passkey / Biometric', variant: 'green' as const }
    if (user.mfa_method === 'totp') return { label: 'Authenticator App', variant: 'blue' as const }
    if (user.mfa_method === 'email_otp') return { label: 'Email OTP', variant: 'yellow' as const }
    return { label: user.mfa_method, variant: 'gray' as const }
  }

  const navItems: { id: Section; label: string }[] = [
    { id: 'profile', label: 'Profile' },
    { id: 'security', label: 'Security' },
    { id: 'passkeys', label: 'Passkeys' },
    { id: 'danger', label: 'Danger Zone' },
  ]

  const msgSz = isMobile ? 'text-xs' : 'text-[10px]'
  const btnSz = isMobile ? 'text-sm' : 'text-xs'
  const bodySz = isMobile ? 'text-sm' : 'text-xs'

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#161b22]">
      {/* Panel header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-terminal-border shrink-0">
        <span className={`${isMobile ? 'text-sm' : 'text-xs'} font-mono text-terminal-fg/60 uppercase tracking-wider`}>
          Account Settings
        </span>
        {onClose && (
          <button onClick={onClose} className={`text-terminal-fg/30 hover:text-terminal-fg ${btnSz} font-mono`}>✕</button>
        )}
      </div>

      {/* Section nav */}
      <div className="flex border-b border-terminal-border shrink-0">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => { setActiveSection(item.id); setEmailMsg(null); setPwMsg(null); setPasskeyMsg(null); setDeleteMsg(null) }}
            className={`flex-1 py-1.5 ${isMobile ? 'text-[11px]' : 'text-[9px]'} font-mono uppercase tracking-wider transition-colors ${
              activeSection === item.id
                ? item.id === 'danger'
                  ? 'text-red-400 border-b border-red-500'
                  : 'text-terminal-active border-b border-terminal-active'
                : item.id === 'danger'
                  ? 'text-red-400/50 hover:text-red-400'
                  : 'text-terminal-fg/40 hover:text-terminal-fg'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">

        {/* ── Profile ── */}
        {activeSection === 'profile' && (
          <div>
            <SectionHeader label="Account Info" mobile={isMobile} />
            <div className="space-y-1 mb-4">
              <p className={`${msgSz} font-mono text-terminal-fg/40`}>Current email</p>
              <p className={`${bodySz} font-mono text-terminal-fg`}>{user?.username ?? '—'}</p>
            </div>

            <SectionHeader label="Change Email" mobile={isMobile} />
            <form onSubmit={handleChangeEmail} className="space-y-2">
              <FieldInput label="New email" type="email" value={newEmail} onChange={setNewEmail} placeholder="new@example.com" mobile={isMobile} />
              <FieldInput label="Current password" type="password" value={emailPw} onChange={setEmailPw} mobile={isMobile} />
              {emailMsg && (
                <p className={`${msgSz} font-mono ${emailMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{emailMsg.text}</p>
              )}
              <button
                type="submit"
                disabled={emailLoading || !newEmail || !emailPw}
                className={`w-full py-2 rounded border border-terminal-border text-terminal-fg/80 font-mono ${btnSz} hover:border-terminal-active hover:text-terminal-fg disabled:opacity-40`}
              >
                {emailLoading ? 'Updating…' : 'Update Email'}
              </button>
            </form>
          </div>
        )}

        {/* ── Security ── */}
        {activeSection === 'security' && (
          <div>
            <SectionHeader label="Two-Factor Authentication" mobile={isMobile} />
            <div className="flex items-center gap-2 mb-4">
              <span className={`${bodySz} font-mono text-terminal-fg/60`}>Method:</span>
              <StatusBadge {...mfaLabel()} mobile={isMobile} />
            </div>

            <SectionHeader label="Change Password" mobile={isMobile} />
            <form onSubmit={handleChangePassword} className="space-y-2">
              <FieldInput label="Current password" type="password" value={curPw} onChange={setCurPw} mobile={isMobile} />
              <FieldInput
                label="New password"
                type="password"
                value={newPw}
                onChange={setNewPw}
                hint="16+ chars, upper, lower, digit, special"
                mobile={isMobile}
              />
              <FieldInput label="Confirm new password" type="password" value={confirmPw} onChange={setConfirmPw} mobile={isMobile} />
              {pwMsg && (
                <p className={`${msgSz} font-mono ${pwMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{pwMsg.text}</p>
              )}
              <button
                type="submit"
                disabled={pwLoading || !curPw || !newPw || !confirmPw}
                className={`w-full py-2 rounded border border-terminal-border text-terminal-fg/80 font-mono ${btnSz} hover:border-terminal-active hover:text-terminal-fg disabled:opacity-40`}
              >
                {pwLoading ? 'Updating…' : 'Change Password'}
              </button>
            </form>
          </div>
        )}

        {/* ── Passkeys ── */}
        {activeSection === 'passkeys' && (
          <div>
            <SectionHeader label="Registered Passkeys" mobile={isMobile} />
            {passkeys.length === 0 ? (
              <p className={`${msgSz} font-mono text-terminal-fg/30 mb-4`}>
                No passkeys registered. Add one below to enable biometric login.
              </p>
            ) : (
              <div className="space-y-2 mb-4">
                {passkeys.map((pk) => (
                  <div key={pk.id} className="flex items-start justify-between gap-2 p-2 rounded border border-terminal-border bg-terminal-bg">
                    <div className="min-w-0">
                      <p className={`${bodySz} font-mono text-terminal-fg truncate`}>{pk.name || 'Unnamed passkey'}</p>
                      <p className={`${msgSz} font-mono text-terminal-fg/30`}>
                        Added {new Date(pk.created_at).toLocaleDateString()}
                        {pk.last_used_at && ` · Used ${new Date(pk.last_used_at).toLocaleDateString()}`}
                      </p>
                    </div>
                    <button
                      onClick={() => handleDeletePasskey(pk.id)}
                      disabled={deletingId === pk.id}
                      className={`${msgSz} font-mono text-red-400/60 hover:text-red-400 shrink-0 disabled:opacity-40`}
                    >
                      {deletingId === pk.id ? '…' : 'Remove'}
                    </button>
                  </div>
                ))}
              </div>
            )}

            <SectionHeader label="Add Passkey" mobile={isMobile} />
            <div className="space-y-2">
              <FieldInput
                label="Nickname (optional)"
                value={passkeyName}
                onChange={setPasskeyName}
                placeholder="e.g. MacBook Touch ID"
                mobile={isMobile}
              />
              {passkeyMsg && (
                <p className={`${msgSz} font-mono ${passkeyMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{passkeyMsg.text}</p>
              )}
              <button
                type="button"
                onClick={handleAddPasskey}
                disabled={passkeyLoading}
                className={`w-full py-2 rounded bg-terminal-active text-white font-mono ${btnSz} hover:bg-blue-600 disabled:opacity-40 flex items-center justify-center gap-1.5`}
              >
                <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                  <path d="M8 1a2 2 0 0 1 2 2v4H6V3a2 2 0 0 1 2-2zm3 6V3a3 3 0 0 0-6 0v4a2 2 0 0 0-2 2v5a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z"/>
                </svg>
                {passkeyLoading ? 'Waiting for biometric…' : 'Register Passkey'}
              </button>
            </div>
          </div>
        )}

        {/* ── Danger Zone ── */}
        {activeSection === 'danger' && (
          <div>
            <SectionHeader label="Delete Account" mobile={isMobile} />
            <p className={`${msgSz} font-mono text-terminal-fg/40 mb-3`}>
              This permanently deletes your account, all sessions, and all passkeys. This cannot be undone.
            </p>
            <form onSubmit={handleDeleteAccount} className="space-y-2">
              <FieldInput label="Password" type="password" value={deletePw} onChange={setDeletePw} mobile={isMobile} />
              <FieldInput
                label='Type "delete my account" to confirm'
                value={deleteConfirm}
                onChange={setDeleteConfirm}
                placeholder="delete my account"
                mobile={isMobile}
              />
              {deleteMsg && (
                <p className={`${msgSz} font-mono ${deleteMsg.ok ? 'text-green-400' : 'text-red-400'}`}>{deleteMsg.text}</p>
              )}
              <button
                type="submit"
                disabled={deleteLoading || !deletePw || deleteConfirm !== 'delete my account'}
                className={`w-full py-2 rounded border border-red-800 text-red-400 font-mono ${btnSz} hover:bg-red-900/20 disabled:opacity-40`}
              >
                {deleteLoading ? 'Deleting…' : 'Delete My Account'}
              </button>
            </form>
          </div>
        )}

      </div>
    </div>
  )
}
