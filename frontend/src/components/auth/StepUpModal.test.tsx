import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { StepUpModal } from './StepUpModal'

vi.mock('@/api/auth', () => ({
  stepUp: vi.fn(),
  stepUpPasskeyBegin: vi.fn(),
  stepUpSendEmailCode: vi.fn(),
}))

vi.mock('@simplewebauthn/browser', () => ({
  startAuthentication: vi.fn(),
}))

describe('StepUpModal', () => {
  beforeEach(() => vi.clearAllMocks())

  it('offers a choice when several factors are enrolled', () => {
    render(<StepUpModal methods={['passkey', 'totp']} onSuccess={() => {}} onCancel={() => {}} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /passkey/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /authenticator app code/i })).toBeInTheDocument()
  })

  it('verifies a TOTP code and reports success', async () => {
    const { stepUp } = await import('@/api/auth')
    vi.mocked(stepUp).mockResolvedValueOnce(undefined)
    const onSuccess = vi.fn()

    render(<StepUpModal methods={['totp']} onSuccess={onSuccess} onCancel={() => {}} />)
    await userEvent.type(screen.getByLabelText(/authenticator code/i), '123456')
    await userEvent.click(screen.getByRole('button', { name: /^verify$/i }))

    await waitFor(() => expect(stepUp).toHaveBeenCalledWith('totp', '123456'))
    expect(onSuccess).toHaveBeenCalled()
  })

  it('shows an error on a wrong code and does not call onSuccess', async () => {
    const { stepUp } = await import('@/api/auth')
    vi.mocked(stepUp).mockRejectedValueOnce({ response: { status: 401 } })
    const onSuccess = vi.fn()

    render(<StepUpModal methods={['totp']} onSuccess={onSuccess} onCancel={() => {}} />)
    await userEvent.type(screen.getByLabelText(/authenticator code/i), '000000')
    await userEvent.click(screen.getByRole('button', { name: /^verify$/i }))

    expect(await screen.findByText(/incorrect code/i)).toBeInTheDocument()
    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('sends an e-mail code automatically when e-mail is the only method', async () => {
    const { stepUpSendEmailCode } = await import('@/api/auth')
    vi.mocked(stepUpSendEmailCode).mockResolvedValueOnce(undefined)
    render(<StepUpModal methods={['email_otp']} onSuccess={() => {}} onCancel={() => {}} />)
    await waitFor(() => expect(stepUpSendEmailCode).toHaveBeenCalled())
    expect(await screen.findByLabelText(/code from your e-mail/i)).toBeInTheDocument()
  })

  it('cancel calls onCancel', async () => {
    const onCancel = vi.fn()
    render(<StepUpModal methods={['totp']} onSuccess={() => {}} onCancel={onCancel} />)
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    expect(onCancel).toHaveBeenCalled()
  })
})
