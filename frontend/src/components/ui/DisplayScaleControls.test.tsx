import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DisplayScaleControls } from './DisplayScaleControls'
import {
  useDisplayStore,
  UI_SCALE_MIN,
  UI_SCALE_MAX,
} from '@/store/displayStore'

const get = () => useDisplayStore.getState()
const dec = () => screen.getByLabelText('Decrease display size')
const inc = () => screen.getByLabelText('Increase display size')

describe('DisplayScaleControls', () => {
  beforeEach(() => {
    localStorage.clear()
    get().reset()
  })

  it('shows the current scale as a percentage', () => {
    useDisplayStore.setState({ uiScale: 1.3 })
    render(<DisplayScaleControls />)
    expect(screen.getByText('130%')).toBeInTheDocument()
  })

  it('rounds the readout to a whole percent', () => {
    useDisplayStore.setState({ uiScale: 1.1 })
    render(<DisplayScaleControls />)
    // Guards against "110.00000000000001%" from float accumulation.
    expect(screen.getByText('110%')).toBeInTheDocument()
  })

  it('zooms in and out', () => {
    render(<DisplayScaleControls />)
    fireEvent.click(inc())
    expect(get().uiScale).toBe(1.1)
    expect(screen.getByText('110%')).toBeInTheDocument()

    fireEvent.click(dec())
    expect(get().uiScale).toBe(1)
  })

  it('scales the terminal font along with the interface', () => {
    render(<DisplayScaleControls />)
    fireEvent.click(inc())
    expect(get().terminalFontSize).toBe(15)
  })

  it('resets when the percentage is clicked', () => {
    useDisplayStore.setState({ uiScale: 1.7, terminalFontSize: 22 })
    render(<DisplayScaleControls />)
    fireEvent.click(screen.getByLabelText('Reset display size'))
    expect(get().uiScale).toBe(1)
    expect(get().terminalFontSize).toBe(14)
  })

  it('disables zoom-in at the maximum', () => {
    useDisplayStore.setState({ uiScale: UI_SCALE_MAX })
    render(<DisplayScaleControls />)
    expect(inc()).toBeDisabled()
    expect(dec()).toBeEnabled()
  })

  it('disables zoom-out at the minimum', () => {
    useDisplayStore.setState({ uiScale: UI_SCALE_MIN })
    render(<DisplayScaleControls />)
    expect(dec()).toBeDisabled()
    expect(inc()).toBeEnabled()
  })

  it('hides the percentage in compact (mobile) mode but keeps both buttons', () => {
    render(<DisplayScaleControls compact />)
    expect(screen.queryByLabelText('Reset display size')).not.toBeInTheDocument()
    expect(dec()).toBeInTheDocument()
    expect(inc()).toBeInTheDocument()
  })

  it('is exposed as a labelled group for screen readers', () => {
    render(<DisplayScaleControls />)
    expect(screen.getByRole('group', { name: 'Display size' })).toBeInTheDocument()
  })
})
