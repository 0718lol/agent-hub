import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import WorkbenchModal from './WorkbenchModal'

describe('WorkbenchModal', () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function showModalMock() {
      this.open = true
    })
    HTMLDialogElement.prototype.close = vi.fn(function closeMock() {
      this.open = false
    })
    global.fetch = vi.fn(async (url, opts) => {
      if (String(url).startsWith('/api/workbench/status')) {
        return {
          ok: true,
          json: async () => ({
            workbench_mode: true,
            home_dir: '/Users/test',
            personal_ai_os: {
              url: 'http://127.0.0.1:8000',
              online: true,
              local_dir: '/Users/test/personal-ai-os',
              mcp_available: true,
              mcp_connected: false,
              projects: [{ id: 'p1', name: '独立开发助手', goal: '打通本地知识与代码执行' }],
            },
          }),
        }
      }
      if (String(url).includes('/workspace') && (!opts || !opts.method)) {
        return {
          ok: true,
          json: async () => ({
            conversation_id: 'conv_pm',
            path: '/Users/test/agenthub_export/conv_pm',
            is_bound: false,
            bound_path: '',
            has_handoff: false,
            git: { is_git: false, branch: '', dirty: false },
            entries: [{ name: 'index.html', is_dir: false, size: 120 }],
          }),
        }
      }
      if (String(url).includes('/workspace') && opts?.method === 'POST') {
        const body = JSON.parse(opts.body)
        return {
          ok: true,
          json: async () => ({
            conversation_id: 'conv_pm',
            path: body.path,
            is_bound: true,
            bound_path: body.path,
            has_handoff: false,
            git: { is_git: true, branch: 'main', dirty: false },
            entries: [{ name: 'src', is_dir: true, size: 0 }],
          }),
        }
      }
      return { ok: true, json: async () => ({}) }
    })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('opens native modal dialog, displays Personal AI OS projects, and binds a local directory', async () => {
    const onClose = vi.fn()
    render(<WorkbenchModal open onClose={onClose} activeConvId="conv_pm" />)

    await waitFor(() => {
      expect(screen.getByText(/独立开发助手/)).toBeInTheDocument()
    })

    const input = screen.getByLabelText(/本机项目文件夹路径/)
    fireEvent.change(input, { target: { value: '/Users/test/Projects/my-app' } })
    fireEvent.click(screen.getByRole('button', { name: '挂载到当前会话' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('/Users/test/Projects/my-app')
    })
  })
})
