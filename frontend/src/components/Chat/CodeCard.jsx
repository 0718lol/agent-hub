import React, { useState } from 'react'
import { Check, Play, Loader } from 'lucide-react'

const RUNNABLE_LANGS = ['python', 'py', 'javascript', 'js', 'typescript', 'ts', 'shell', 'bash', 'sh']

export default function CodeCard({ language, code }) {
  const [copied, setCopied] = useState(false)
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState(null)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = code
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleRun = async () => {
    setRunning(true)
    setRunResult(null)
    try {
      const resp = await fetch('/api/sandbox/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: language || 'python', timeout: 10 }),
      })
      const data = await resp.json()
      setRunResult(data)
    } catch (e) {
      setRunResult({ status: 'error', stderr: '请求失败: ' + e.message })
    }
    setRunning(false)
  }

  const canRun = RUNNABLE_LANGS.includes((language || '').toLowerCase())

  return (
    <div style={{ margin: '8px 0', borderRadius: '8px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 12px',
        background: 'rgba(255,255,255,0.05)',
        fontSize: '12px',
        color: '#94a3b8',
      }}>
        <span>{language || 'code'}</span>
        <div style={{ display: 'flex', gap: 4 }}>
          {canRun && (
            <button
              onClick={handleRun}
              disabled={running}
              style={{
                background: running ? 'transparent' : 'rgba(16,185,129,0.1)',
                border: '1px solid rgba(16,185,129,0.3)',
                color: '#10b981',
                cursor: running ? 'not-allowed' : 'pointer',
                fontSize: '12px',
                padding: '2px 8px',
                borderRadius: '4px',
                display: 'inline-flex', alignItems: 'center', gap: 3,
              }}
            >
              {running ? <><Loader size={11} style={{ animation: 'spin 1s linear infinite' }} /> 运行中</> : <><Play size={11} /> 运行</>}
            </button>
          )}
          <button
            onClick={handleCopy}
            style={{
              background: 'none',
              border: 'none',
              color: copied ? '#10b981' : '#94a3b8',
              cursor: 'pointer',
              fontSize: '12px',
              padding: '2px 8px',
              borderRadius: '4px',
            }}
          >
            {copied ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}><Check size={12} /> 已复制</span> : '复制'}
          </button>
        </div>
      </div>
      <pre style={{
        background: '#0d1117',
        padding: '12px',
        margin: 0,
        overflow: 'auto',
        maxHeight: '300px',
      }}>
        <code style={{
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontSize: '13px',
          color: '#e6edf3',
          lineHeight: '1.5',
        }}>
          {code}
        </code>
      </pre>
      {/* Execution Result */}
      {runResult && (
        <div style={{
          borderTop: '1px solid rgba(255,255,255,0.08)',
          padding: '10px 12px',
          background: runResult.status === 'success' ? 'rgba(16,185,129,0.05)' : 'rgba(239,68,68,0.05)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6, fontSize: 11 }}>
            <span style={{
              padding: '1px 6px', borderRadius: 3, fontSize: 10, fontWeight: 600,
              background: runResult.status === 'success' ? 'rgba(16,185,129,0.15)' : runResult.status === 'timeout' ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)',
              color: runResult.status === 'success' ? '#10b981' : runResult.status === 'timeout' ? '#f59e0b' : '#ef4444',
            }}>
              {runResult.status === 'success' ? '✓ 成功' : runResult.status === 'timeout' ? '⏱ 超时' : '✗ 错误'}
            </span>
            <span style={{ color: '#64748b' }}>{runResult.duration_ms}ms</span>
            {runResult.exit_code !== 0 && <span style={{ color: '#64748b' }}>exit: {runResult.exit_code}</span>}
          </div>
          {runResult.stdout && (
            <pre style={{
              margin: 0, padding: 8, borderRadius: 4,
              background: 'rgba(0,0,0,0.3)', fontSize: 12,
              color: '#a5d6a7', maxHeight: 150, overflow: 'auto',
              fontFamily: "'JetBrains Mono', monospace", whiteSpace: 'pre-wrap',
            }}>{runResult.stdout}</pre>
          )}
          {runResult.stderr && (
            <pre style={{
              margin: runResult.stdout ? '6px 0 0' : 0, padding: 8, borderRadius: 4,
              background: 'rgba(0,0,0,0.3)', fontSize: 12,
              color: '#ef9a9a', maxHeight: 150, overflow: 'auto',
              fontFamily: "'JetBrains Mono', monospace", whiteSpace: 'pre-wrap',
            }}>{runResult.stderr}</pre>
          )}
        </div>
      )}
    </div>
  )
}
