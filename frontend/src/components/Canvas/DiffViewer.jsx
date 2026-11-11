import React, { useEffect, useState } from 'react'
import { DiffEditor, Editor } from '@monaco-editor/react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useThemeStore } from '../../stores/themeStore'

export default function DiffViewer() {
  const generatedCode = useCanvasStore((s) => s.generatedCode)
  const previousCode = useCanvasStore((s) => s.previousCode)
  const theme = useThemeStore((s) => s.theme)
  const artifact = useCanvasStore((s) => s.artifact)
  const artifacts = useCanvasStore((s) => s.artifacts)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { setEditing(false); setDraft(artifact?.code || ''); setMessage('') }, [artifact?.id])
  const save = async () => {
    setBusy(true)
    try {
      const response = await fetch('/api/artifacts/' + artifact.id + '/versions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: draft }) })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || '保存失败')
      useCanvasStore.getState().selectArtifact(result, true)
      await useCanvasStore.getState().loadArtifacts(useCanvasStore.getState().artifactConversation)
      setEditing(false)
      setMessage('已保存为新版本')
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  const validate = async () => {
    setBusy(true)
    try {
      const response = await fetch('/api/artifacts/' + artifact.id + '/validate', { method: 'POST' })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || '验证失败')
      useCanvasStore.getState().selectArtifact(result, true)
      setMessage(result.sandbox_output || result.sandbox_status)
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }

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
    readOnly: !editing,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 13,
    lineNumbers: 'on',
    scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {artifact && <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: 8 }}>
        <select aria-label="产物版本" value={artifact.id} onChange={(event) => useCanvasStore.getState().selectArtifact(artifacts.find(item => item.id === Number(event.target.value)), true)}>
          {!artifacts.some(item => item.id === artifact.id) && <option value={artifact.id}>{artifact.name} v{artifact.version}</option>}
          {artifacts.map(item => <option key={item.id} value={item.id}>{item.name} v{item.version}</option>)}
        </select>
        <span>{artifact.content_hash?.slice(0, 12)} · {artifact.sandbox_status === 'success' ? '沙箱运行通过' : artifact.sandbox_status === 'error' || artifact.sandbox_status === 'timeout' ? '验证失败' : '未验证'}</span>
        <button disabled={busy} onClick={() => { setDraft(code); setEditing(!editing) }}>{editing ? '取消编辑' : '编辑'}</button>
        {editing && <button disabled={busy} onClick={save}>保存新版本</button>}
        {!editing && ['python','py','javascript','js'].includes(language.toLowerCase()) && <button disabled={busy} onClick={validate}>{busy ? '正在验证…' : '沙箱验证'}</button>}
      </div>}
      {message && <pre role="status" style={{ whiteSpace: 'pre-wrap', maxHeight: 160, overflow: 'auto', padding: 8 }}>{message}</pre>}
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
        {previousCode && !editing ? (
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
            value={editing ? draft : code}
            onChange={(value) => setDraft(value || '')}
            theme={monacoTheme}
            options={commonOptions}
          />
        )}
      </div>
    </div>
  )
}
