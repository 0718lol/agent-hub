import React from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WebPreview from './WebPreview'
import { useCanvasStore } from '../../stores/canvasStore'
import { useChatStore } from '../../stores/chatStore'


describe('WebPreview', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    useCanvasStore.setState({ previewHtml: null, activeTab: 'preview' })
    useChatStore.setState({ activeConversationId: 'conv-web' })
  })

  afterEach(() => cleanup())

  it('loads the persisted workspace preview instead of a fake localhost URL', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        project_type: 'web',
        web: {
          static_url: '/api/previews/conv-web/files/index.html',
          runtime_url: '', runtime_active: false, can_start_runtime: false,
        },
      }),
    })
    render(<WebPreview />)

    await waitFor(() => expect(screen.getByTitle('项目预览')).toHaveAttribute(
      'src', expect.stringContaining('/api/previews/conv-web/files/index.html'),
    ))
    expect(screen.getByRole('textbox').value).toContain('/api/previews/conv-web/files/index.html')
  })

  it('keeps stream HTML as the fallback before project persistence', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 })
    act(() => useCanvasStore.getState().setPreviewHtml('<h1>stream</h1>'))
    render(<WebPreview />)

    await waitFor(() => expect(screen.getByTitle('项目预览')).toHaveAttribute('srcdoc', '<h1>stream</h1>'))
  })

  it('shows API request debugging when a runtime is online', async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          project_type: 'api', web: {},
          api: { base_url: '/published/job/', docs_url: '/published/job/docs' },
        }),
      })
      .mockResolvedValueOnce({ ok: true, status: 200, text: async () => '{"status":"ok"}' })
    render(<WebPreview />)

    await screen.findByLabelText('API 路径')
    fireEvent.change(screen.getByLabelText('API 路径'), { target: { value: 'health' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))
    await waitFor(() => expect(screen.getByText(/HTTP 200/)).toBeInTheDocument())
    expect(global.fetch).toHaveBeenLastCalledWith('/published/job/health', expect.objectContaining({ method: 'GET' }))
  })
})
