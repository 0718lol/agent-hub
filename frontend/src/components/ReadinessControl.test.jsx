import React from 'react'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import ReadinessControl from './ReadinessControl'

describe('ReadinessControl', () => {
  it('distinguishes service, model and build readiness', () => {
    render(<ReadinessControl readiness={{ service: 'online', model: 'demo', buildServices: 'limited' }} />)
    fireEvent.click(screen.getByRole('button', { name: '运行状态' }))
    expect(screen.getByText('在线')).toBeInTheDocument()
    expect(screen.getByText('演示模式')).toBeInTheDocument()
    expect(screen.getByText('受限')).toBeInTheDocument()
  })
})
