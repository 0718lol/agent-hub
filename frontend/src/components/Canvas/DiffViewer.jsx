import React from 'react'
import { DiffEditor } from '@monaco-editor/react'
import { useCanvasStore } from '../../stores/canvasStore'

export default function DiffViewer() {
  const generatedCode = useCanvasStore((s) => s.generatedCode)
  const previousCode = useCanvasStore((s) => s.previousCode)

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyBetween: 'space-between', gap: 8, marginBottom: 12,
        padding: '8px 12px', background: 'var(--bg-tertiary)', borderRadius: 8, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            padding: '3px 10px', background: 'rgba(99,102,241,0.2)',
            border: '1px solid rgba(99,102,241,0.4)', borderRadius: 6,
            color: '#6366f1', fontSize: 12, fontFamily: 'monospace',
          }}>
            {language}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            代码对比视图 (Monaco Diff Editor)
          </span>
        </div>
        {previousCode ? (
          <span style={{ fontSize: 11, color: '#10b981', display: 'flex', alignItems: 'center', gap: 4 }}>
            ● 已载入历史代码比对
          </span>
        ) : (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            ● 新增文件 (无历史版本)
          </span>
        )}
      </div>

      <div style={{
        flex: 1, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)',
        height: 'calc(100vh - 200px)'
      }}>
        <DiffEditor
          height="100%"
          language={language.toLowerCase() === 'html' ? 'html' : language.toLowerCase() === 'python' ? 'python' : 'javascript'}
          original={previousCode || ''}
          modified={code}
          theme="vs-dark"
          options={{
            readOnly: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            renderSideBySide: true,
            fontSize: 13,
            lineNumbers: 'on',
            scrollbar: {
              verticalScrollbarSize: 6,
              horizontalScrollbarSize: 6,
            }
          }}
        />
      </div>
    </div>
  )
}
