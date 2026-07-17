import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { DiffEditor, Editor } from '@monaco-editor/react'
import { AlertCircle, FileCode2, GitCommit, History, RefreshCw, RotateCcw } from 'lucide-react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useChatStore } from '../../stores/chatStore'
import { useThemeStore } from '../../stores/themeStore'

const LANGUAGE_MAP = {
  html: 'html', htm: 'html', css: 'css',
  javascript: 'javascript', js: 'javascript', jsx: 'javascript',
  typescript: 'typescript', ts: 'typescript', tsx: 'typescript',
  python: 'python', py: 'python', json: 'json', yaml: 'yaml', yml: 'yaml',
  kotlin: 'kotlin', java: 'java', xml: 'xml', sql: 'sql',
  dockerfile: 'dockerfile', bash: 'shell', sh: 'shell',
}

function monacoLanguage(language = '') {
  return LANGUAGE_MAP[language.toLowerCase()] || 'plaintext'
}

function formatSnapshotTime(timestamp) {
  if (!timestamp) return ''
  return new Date(timestamp * 1000).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

export default function DiffViewer() {
  const generatedCode = useCanvasStore((state) => state.generatedCode)
  const previousCode = useCanvasStore((state) => state.previousCode)
  const activeConversationId = useChatStore((state) => state.activeConversationId)
  const theme = useThemeStore((state) => state.theme)
  const [project, setProject] = useState(null)
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedFile, setSelectedFile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [restoring, setRestoring] = useState('')
  const [projectRevision, setProjectRevision] = useState(0)

  const fetchProject = useCallback(async () => {
    if (!activeConversationId) return
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(activeConversationId)}`)
      if (!response.ok) throw new Error(`工程信息请求失败 (${response.status})`)
      const data = await response.json()
      if (!data || !Array.isArray(data.files) || !Array.isArray(data.snapshots)) {
        throw new Error('工程信息格式无效')
      }
      setProject(data)
      setProjectRevision((revision) => revision + 1)
      setSelectedPath((currentPath) => {
        if (currentPath && data.files.some((file) => file.path === currentPath)) return currentPath
        const preferred = data.files.find((file) => file.path === 'index.html') || data.files[0]
        return preferred?.path || ''
      })
      setError('')
    } catch (loadError) {
      setError(loadError.message || '工程加载失败')
    } finally {
      setLoading(false)
    }
  }, [activeConversationId])

  useEffect(() => {
    setLoading(true)
    setProject(null)
    setSelectedPath('')
    setSelectedFile(null)
    fetchProject()
  }, [activeConversationId, fetchProject])

  useEffect(() => {
    if (generatedCode?.code) fetchProject()
  }, [generatedCode?.code, fetchProject])

  useEffect(() => {
    if (!selectedPath || !activeConversationId) {
      setSelectedFile(null)
      return undefined
    }
    const controller = new AbortController()
    const loadFile = async () => {
      try {
        const query = new URLSearchParams({ path: selectedPath })
        const response = await fetch(
          `/api/projects/${encodeURIComponent(activeConversationId)}/files?${query}`,
          { signal: controller.signal },
        )
        if (!response.ok) throw new Error(`文件读取失败 (${response.status})`)
        const data = await response.json()
        setSelectedFile(data)
        setError('')
      } catch (loadError) {
        if (loadError.name !== 'AbortError') setError(loadError.message || '文件读取失败')
      }
    }
    loadFile()
    return () => controller.abort()
  }, [activeConversationId, selectedPath, projectRevision])

  const restoreSnapshot = async (snapshot) => {
    if (!window.confirm(`确认恢复到版本 ${snapshot.hash.slice(0, 8)}？当前未提交修改会被替换。`)) return
    setRestoring(snapshot.hash)
    try {
      const response = await fetch(
        `/api/projects/${encodeURIComponent(activeConversationId)}/snapshots/${snapshot.hash}/restore`,
        { method: 'POST' },
      )
      if (!response.ok) throw new Error(`版本恢复失败 (${response.status})`)
      setHistoryOpen(false)
      await fetchProject()
    } catch (restoreError) {
      setError(restoreError.message || '版本恢复失败')
    } finally {
      setRestoring('')
    }
  }

  const hasProjectFiles = Boolean(project?.exists && project.files.length)
  const displayed = selectedFile || generatedCode
  const language = displayed?.language || 'text'
  const code = selectedFile?.content ?? generatedCode?.code ?? ''
  const showDiff = !selectedFile && Boolean(previousCode)
  const monacoTheme = theme === 'light' ? 'vs' : 'vs-dark'
  const commonOptions = useMemo(() => ({
    readOnly: true,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    fontSize: 13,
    lineNumbers: 'on',
    scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
  }), [])

  if (loading && !displayed) {
    return <div style={{ padding: 24, color: 'var(--text-muted)' }}>正在加载工程...</div>
  }

  if (!displayed && !hasProjectFiles) {
    return (
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        height: '100%', color: 'var(--text-muted)', gap: 12,
      }}>
        {error ? <AlertCircle size={30} color="#f87171" /> : <FileCode2 size={34} opacity={0.45} />}
        <div style={{ fontSize: 13 }}>{error || 'Agent 生成的工程文件会显示在这里'}</div>
        {error && (
          <button
            type="button"
            onClick={() => {
              setLoading(true)
              fetchProject()
            }}
            style={retryButtonStyle}
          >
            <RefreshCw size={13} />
            重新加载
          </button>
        )}
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', height: '100%', minWidth: 0, position: 'relative' }}>
      {hasProjectFiles && (
        <aside style={{
          width: 210, minWidth: 170, maxWidth: '32%', borderRight: '1px solid var(--border)',
          background: 'var(--bg-secondary)', display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          <div style={{
            height: 38, padding: '0 10px', display: 'flex', alignItems: 'center',
            borderBottom: '1px solid var(--border)', fontSize: 11, fontWeight: 600,
            color: 'var(--text-secondary)',
          }}>
            项目文件
            <span style={{ marginLeft: 'auto', color: 'var(--text-muted)', fontWeight: 400 }}>
              {project.files.length}
            </span>
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: '5px 0' }}>
            {project.files.map((file) => (
              <button
                type="button"
                key={file.path}
                title={file.path}
                onClick={() => setSelectedPath(file.path)}
                style={{
                  width: '100%', minHeight: 30, padding: `5px 8px 5px ${8 + Math.min(file.path.split('/').length - 1, 4) * 10}px`,
                  border: 'none', borderLeft: selectedPath === file.path ? '2px solid var(--accent)' : '2px solid transparent',
                  background: selectedPath === file.path ? 'var(--accent-bg)' : 'transparent',
                  color: selectedPath === file.path ? 'var(--text-primary)' : 'var(--text-secondary)',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, textAlign: 'left',
                }}
              >
                <FileCode2 size={13} style={{ flexShrink: 0 }} />
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11 }}>
                  {file.name}
                </span>
              </button>
            ))}
          </div>
        </aside>
      )}

      <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{
          height: 38, padding: '0 10px', display: 'flex', alignItems: 'center', gap: 8,
          borderBottom: '1px solid var(--border)', background: 'var(--bg-tertiary)', flexShrink: 0,
        }}>
          <span style={{
            padding: '2px 7px', background: 'var(--accent-bg)', border: '1px solid var(--accent)',
            borderRadius: 4, color: 'var(--accent)', fontSize: 11, fontFamily: 'monospace',
          }}>
            {language}
          </span>
          <span title={selectedPath} style={{
            minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            color: 'var(--text-muted)', fontSize: 11,
          }}>
            {selectedPath || (showDiff ? '即时代码对比' : '即时代码预览')}
          </span>
          {project?.snapshots?.length > 0 && (
            <button
              type="button"
              title="版本快照"
              aria-label="版本快照"
              onClick={() => setHistoryOpen((open) => !open)}
              style={{ ...iconButtonStyle, marginLeft: 'auto' }}
            >
              <History size={15} />
            </button>
          )}
        </div>

        {error && (
          <div style={{
            minHeight: 32, padding: '6px 10px', display: 'flex', alignItems: 'center', gap: 7,
            borderBottom: '1px solid rgba(239,68,68,0.25)', color: '#fca5a5',
            background: 'rgba(239,68,68,0.08)', fontSize: 11,
          }}>
            <AlertCircle size={13} />
            {error}
          </div>
        )}

        <div style={{ flex: 1, minHeight: 0 }}>
          {showDiff ? (
            <DiffEditor
              height="100%"
              language={monacoLanguage(language)}
              original={previousCode}
              modified={code}
              theme={monacoTheme}
              options={{ ...commonOptions, renderSideBySide: false }}
            />
          ) : (
            <Editor
              height="100%"
              language={monacoLanguage(language)}
              value={code}
              theme={monacoTheme}
              options={commonOptions}
            />
          )}
        </div>
      </section>

      {historyOpen && (
        <div style={{
          position: 'absolute', top: 38, right: 8, zIndex: 10, width: 300, maxHeight: '70%',
          overflow: 'auto', background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          borderRadius: 6, boxShadow: '0 10px 28px rgba(0,0,0,0.28)',
        }}>
          <div style={{
            height: 36, padding: '0 10px', display: 'flex', alignItems: 'center', gap: 7,
            borderBottom: '1px solid var(--border)', fontSize: 12, fontWeight: 600,
          }}>
            <GitCommit size={14} />
            版本快照
          </div>
          {project.snapshots.map((snapshot) => (
            <div key={snapshot.hash} style={{
              minHeight: 48, padding: '7px 8px 7px 10px', borderBottom: '1px solid var(--border)',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 11 }}>
                  {snapshot.message}
                </div>
                <div style={{ marginTop: 3, color: 'var(--text-muted)', fontSize: 10 }}>
                  {snapshot.hash.slice(0, 8)} · {formatSnapshotTime(snapshot.timestamp)}
                </div>
              </div>
              <button
                type="button"
                title="恢复此版本"
                aria-label="恢复此版本"
                disabled={Boolean(restoring)}
                onClick={() => restoreSnapshot(snapshot)}
                style={iconButtonStyle}
              >
                <RotateCcw size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const iconButtonStyle = {
  width: 28, height: 28, border: '1px solid var(--border)', borderRadius: 4,
  background: 'var(--bg-secondary)', color: 'var(--text-secondary)', cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
}

const retryButtonStyle = {
  height: 30, padding: '0 10px', border: '1px solid var(--border)', borderRadius: 4,
  background: 'var(--bg-secondary)', color: 'var(--text-primary)', cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', gap: 6,
}
