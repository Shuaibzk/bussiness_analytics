import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const login = vi.fn()
let notice = ''
vi.mock('../lib/auth', () => ({ useAuth: () => ({ login, notice }) }))
vi.mock('../lib/api', () => ({
  api: {
    demoAccounts: () => Promise.resolve([
      { username: 'admin', name: 'Amina Admin', password: 'admin123', role: 'admin', role_label: 'Administrator', scope: null },
      { username: 'asia.manager', name: 'Aiko Tanaka', password: 'manager123', role: 'regional_manager', role_label: 'Regional Manager', scope: 'Asia' },
    ]),
  },
}))
vi.mock('../components/FluidBackground', () => ({ default: () => null })) // WebGL is not available in jsdom

import Login from './Login'

describe('Login', () => {
  beforeEach(() => { login.mockReset(); notice = '' })

  it('keeps the submit button disabled until both fields are filled', () => {
    render(<Login />)
    const btn = screen.getByRole('button', { name: 'Sign in' })
    expect(btn).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'ops' } })
    expect(btn).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'ops123' } })
    expect(btn).toBeEnabled()
  })

  it('submits the typed credentials', async () => {
    login.mockResolvedValue({})
    render(<Login />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'ops' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'ops123' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('ops', 'ops123'))
  })

  it('shows the server error when sign-in fails', async () => {
    login.mockRejectedValue(new Error('Invalid username or password'))
    render(<Login />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'y' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password')
  })

  it('signs in with one click on a demo account', async () => {
    login.mockResolvedValue({})
    render(<Login />)
    fireEvent.click(await screen.findByRole('button', { name: /Asia manager|Aiko Tanaka/ }))
    await waitFor(() => expect(login).toHaveBeenCalledWith('asia.manager', 'manager123'))
  })

  it('tells the user when their session ended', () => {
    notice = 'Your session ended. Please sign in again.'
    render(<Login />)
    expect(screen.getByRole('alert')).toHaveTextContent('session ended')
  })
})
