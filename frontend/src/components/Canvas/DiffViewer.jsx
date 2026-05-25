import React from 'react'
import { DiffEditor, Editor } from '@monaco-editor/react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useThemeStore } from '../../stores/themeStore'

export default function DiffViewer() {
  const generatedCode = useCanvasStore((s) => s.generatedCode)
  const previousCode = useCanvasStore((s) => s.previousCode)
  const theme = useThemeStore((s) => s.theme)

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
  const monacoTheme = theme === 'light' ? 'vs' : 'vs-dark'
  const monacoLang = language.toLowerCase() === 'html' ? 'html' : language.toLowerCase() === 'python' ? 'python' : 'javascript'

  const commonOptions = {
    readOnly: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 13,
    lineNumbers: 'on',
    scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyBetween: 'space-between', gap: 8, marginBottom: 12,
        padding: '8px 12px', background: 'var(--bg-tertiary)', borderRadius: 8, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            padding: '3px 10px', background: 'var(--accent-bg)',
            border: '1px solid var(--accent)', borderRadius: 6,
            color: 'var(--accent)', fontSize: 12, fontFamily: 'monospace',
          }}>
            {language}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {previousCode ? '代码对比视图' : '代码预览'}
          </span>
        </div>
        {previousCode ? (
          <span style={{ fontSize: 11, color: 'var(--green)', display: 'flex', alignItems: 'center', gap: 4 }}>
            ● 已载入历史代码比对
          </span>
        ) : (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            ● 新增文件
          </span>
        )}
      </div>

      <div style={{
        flex: 1, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--border)',
      }}>
        {previousCode ? (
          <DiffEditor
            height="100%"
            language={monacoLang}
            original={previousCode}
            modified={code}
            theme={monacoTheme}
            options={{ ...commonOptions, renderSideBySide: false }}
          />
        ) : (
          <Editor
            height="100%"
            language={monacoLang}
            value={code}
            theme={monacoTheme}
            options={commonOptions}
          />
        )}
      </div>
    </div>
  )
}
