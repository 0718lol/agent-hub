import React from 'react'
import { AlertTriangle, RefreshCw, RotateCcw } from 'lucide-react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('[ErrorBoundary] Caught error:', error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '100vh',
          background: 'var(--bg-primary, #1a1a2e)',
          color: 'var(--text-primary, #e2e8f0)',
          fontFamily: 'var(--font-ui, Inter, sans-serif)',
          padding: 24,
        }}>
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 20,
            maxWidth: 420,
            textAlign: 'center',
          }}>
            <div style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: 'rgba(247,101,96,0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <AlertTriangle size={28} color="var(--red, #F76560)" />
            </div>

            <div>
              <h2 style={{
                margin: '0 0 8px',
                fontSize: 'var(--text-xl, 1.5rem)',
                fontWeight: 600,
              }}>
                页面遇到了问题
              </h2>
              <p style={{
                margin: 0,
                fontSize: 'var(--text-sm, 0.875rem)',
                color: 'var(--text-secondary, #94a3b8)',
                lineHeight: 1.6,
              }}>
                组件渲染时发生异常，你可以尝试重试或刷新页面。
              </p>
            </div>

            {process.env.NODE_ENV === 'development' && this.state.error && (
              <pre style={{
                width: '100%',
                padding: '12px 16px',
                background: 'var(--accent-bg, #1A2D4A)',
                border: '1px solid var(--border, rgba(255,255,255,0.08))',
                borderRadius: 'var(--radius-md, 8px)',
                fontSize: 'var(--text-xs, 0.75rem)',
                color: 'var(--red, #F76560)',
                textAlign: 'left',
                overflow: 'auto',
                maxHeight: 160,
                margin: 0,
                fontFamily: 'var(--font-mono, monospace)',
              }}>
                {this.state.error.toString()}
              </pre>
            )}

            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={this.handleRetry}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '8px 20px',
                  background: 'var(--accent, #3C7CFF)',
                  border: 'none',
                  borderRadius: 'var(--radius-md, 8px)',
                  color: '#fff',
                  fontSize: 'var(--text-sm, 0.875rem)',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-ui)',
                }}
              >
                <RotateCcw size={14} />
                重试
              </button>
              <button
                onClick={this.handleReload}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '8px 20px',
                  background: 'transparent',
                  border: '1px solid var(--border, rgba(255,255,255,0.12))',
                  borderRadius: 'var(--radius-md, 8px)',
                  color: 'var(--text-primary, #e2e8f0)',
                  fontSize: 'var(--text-sm, 0.875rem)',
                  fontWeight: 500,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-ui)',
                }}
              >
                <RefreshCw size={14} />
                刷新页面
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
