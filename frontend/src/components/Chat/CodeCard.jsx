import React, { useState } from 'react'
import { Check } from 'lucide-react'

export default function CodeCard({ language, code }) {
  const [copied, setCopied] = useState(false)

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
    </div>
  )
}
