import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import GoalSnapshot from './GoalSnapshot'
import { useChatStore } from '../../stores/chatStore'

describe('GoalSnapshot', () => {
  afterEach(cleanup)

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({ status: 'ok' }) }))
    useChatStore.setState({
      conversations: [{
        id: 'conv_goal', name: 'Goal', messages: [],
        goal: { objective: 'Build a dashboard', stage: 'planning', nextAction: 'Draft UI' },
      }],
    })
  })

  it('shows the current objective and readiness preflight', () => {
    render(<GoalSnapshot conversationId="conv_goal" isFirstTask readiness={{ loading: false, service: 'online', model: 'demo', buildServices: 'limited' }} />)
    expect(screen.getByText('Build a dashboard')).toBeInTheDocument()
    expect(screen.getByText('演示模式')).toBeInTheDocument()
    expect(screen.getByText('规划中')).toBeInTheDocument()
  })

  it('edits and persists the goal without leaving chat', async () => {
    render(<GoalSnapshot conversationId="conv_goal" isFirstTask={false} readiness={null} />)
    fireEvent.click(screen.getByRole('button', { name: '编辑目标' }))
    const objective = screen.getByLabelText('目标')
    fireEvent.change(objective, { target: { value: 'Ship the dashboard' } })
    fireEvent.click(screen.getByRole('button', { name: '保存目标' }))

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(useChatStore.getState().conversations[0].goal.objective).toBe('Ship the dashboard')
  })
})
