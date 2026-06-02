import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useThemeStore } from './themeStore'

describe('themeStore', () => {
  beforeEach(() => {
    // Reset Zustand store state before each test
    useThemeStore.setState({ theme: 'light' })
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue('light'),
      setItem: vi.fn(),
    })
  })

  it('should initialize with light theme by default', () => {
    const state = useThemeStore.getState()
    expect(state.theme).toBe('light')
  })

  it('should toggle theme from light to dark', () => {
    const store = useThemeStore.getState()
    store.toggleTheme()
    
    const updatedState = useThemeStore.getState()
    expect(updatedState.theme).toBe('dark')
    expect(localStorage.setItem).toHaveBeenCalledWith('agent-hub-theme', 'dark')
  })

  it('should toggle theme from dark back to light', () => {
    useThemeStore.setState({ theme: 'dark' })
    const store = useThemeStore.getState()
    store.toggleTheme()
    
    const updatedState = useThemeStore.getState()
    expect(updatedState.theme).toBe('light')
    expect(localStorage.setItem).toHaveBeenCalledWith('agent-hub-theme', 'light')
  })
})
