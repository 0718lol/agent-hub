import React from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import { CodeHiddenNotice } from './MessageBubble'
import MessageBubble from './MessageBubble'

describe('CodeHiddenNotice', () => {
  afterEach(() => {
    vi.useRealTimers()
    cleanup()
  })

  it('rotates streaming status text while code is being generated', () => {
    vi.useFakeTimers()

    render(<CodeHiddenNotice streaming />)

    expect(screen.getByText('正在生成代码 · 正在搭骨架')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1200)
    })

    expect(screen.getByText('正在生成代码 · 正在补样式')).toBeInTheDocument()
  })

  it('shows a finished state when streaming stops', () => {
    render(<CodeHiddenNotice streaming={false} />)

    expect(screen.getByText('代码已生成')).toBeInTheDocument()
    expect(screen.getByText('已同步到右侧预览和代码面板')).toBeInTheDocument()
  })

  it('hides internal retry noise messages', () => {
    const { container } = render(
      <MessageBubble
        conversationId="conv_test"
        message={{
          id: 'm1',
          sender: 'system',
          content: { text: '⚠️ 输出格式不符合要求（format: missing expected content for agent_frontend），正在重新生成...' },
          streaming: false,
        }}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })
})
