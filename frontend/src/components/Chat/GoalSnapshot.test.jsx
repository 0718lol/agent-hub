import React from 'react'
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import GoalSnapshot from './GoalSnapshot'

describe('GoalSnapshot', () => {
  afterEach(cleanup)

  it('shows model readiness without goal metadata', () => {
    render(<GoalSnapshot readiness={{ loading: false, service: 'online', model: 'connected', buildServices: 'ready' }} />)
    expect(screen.getByText('模型已连接')).toBeInTheDocument()
    expect(screen.getByText('构建服务已就绪')).toBeInTheDocument()
    expect(screen.queryByText(/产物：/)).not.toBeInTheDocument()
    expect(screen.queryByText(/下一步：/)).not.toBeInTheDocument()
    expect(screen.queryByText('验证中')).not.toBeInTheDocument()
  })

  it('keeps model readiness visible after refresh', () => {
    render(<GoalSnapshot readiness={{ loading: false, service: 'online', model: 'connected', buildServices: 'ready' }} />)
    expect(screen.getByText('模型已连接')).toBeInTheDocument()
    expect(screen.queryByText(/产物：/)).not.toBeInTheDocument()
    expect(screen.queryByText(/下一步：/)).not.toBeInTheDocument()
  })
})
