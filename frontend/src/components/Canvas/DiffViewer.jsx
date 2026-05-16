import React from 'react'
import { useCanvasStore } from '../../stores/canvasStore'

function highlightCode(code, language) {
  if (!code) return ''

  // Simple syntax highlighting
  let html = code
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // HTML tags
  html = html.replace(/(&lt;\/?)([\w-]+)/g, '$1<span style="color:#ef4444">$2</span>')
  html = html.replace(/([\w-]+)(=)/g, '<span style="color:#f59e0b">$1</span>$2')
  html = html.replace(/(".*?")/g, '<span style="color:#10b981">$1</span>')

  // CSS properties
  html = html.replace(/([\w-]+)(\s*:)/g, '<span style="color:#22d3ee">$1</span>$2')

  // JS keywords
  const keywords = ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'class', 'import', 'export', 'from', 'async', 'await', 'new', 'this']
  keywords.forEach(kw => {
    html = html.replace(new RegExp(`\\b(${kw})\\b`, 'g'), `<span style="color:#c084fc">$1</span>`)
  })

  // Strings
  html = html.replace(/('.*?')/g, '<span style="color:#10b981">$1</span>')

  // Comments
  html = html.replace(/(\/\/.*$)/gm, '<span style="color:#64748b">$1</span>')
  html = html.replace(/(\/\*[\s\S]*?\*\/)/g, '<span style="color:#64748b">$1</span>')

  return html
}

export default function DiffViewer() {
  const generatedCode = useCanvasStore((s) => s.generatedCode)

  if (!generatedCode) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        height: '100%', color: 'var(--text-muted)', gap: 12,
      }}>
        <div style={{ fontSize: 40, opacity: 0.4 }}>{'{ }'}</div>
        <div style={{ fontSize: 13 }}>Agent 生成的代码会显示在这里</div>
      </div>
    )
  }

  const { language, code } = generatedCode
  const lines = code.split('\n')

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
        padding: '8px 12px', background: 'var(--bg-tertiary)', borderRadius: 8,
      }}>
        <span style={{
          padding: '3px 10px', background: 'rgba(99,102,241,0.2)',
          border: '1px solid rgba(99,102,241,0.4)', borderRadius: 6,
          color: '#6366f1', fontSize: 12, fontFamily: 'monospace',
        }}>
          {language}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {lines.length} 行
        </span>
      </div>

      <div className="diff-viewer" style={{ maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>
        {lines.map((line, i) => (
          <div key={i} style={{
            display: 'flex', padding: '1px 0', lineHeight: 1.6,
          }}>
            <span style={{
              display: 'inline-block', width: 40, textAlign: 'right',
              paddingRight: 12, color: '#475569', userSelect: 'none',
              fontSize: 12, flexShrink: 0,
            }}>
              {i + 1}
            </span>
            <span
              style={{ flex: 1, fontSize: 13 }}
              dangerouslySetInnerHTML={{ __html: highlightCode(line, language) || '&nbsp;' }}
            />
          </div>
        ))}
      </div>
    </div>
  )
}
