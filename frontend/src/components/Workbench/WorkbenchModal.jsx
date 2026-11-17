import React, { useEffect, useId, useRef, useState } from 'react'
import { FolderGit2, FolderOpen, Link2, Download, Upload, Send, CheckCircle2, X, RefreshCw } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabStore'

export default function WorkbenchModal({ open, onClose, activeConvId }) {
  const dialogRef = useRef(null)
  const fileInputRef = useRef(null)
  const titleId = useId()
  const folderInputId = useId()
  const createCheckboxId = useId()
  const paiosUrlId = useId()
  const projectSelectId = useId()

  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [statusMessage, setStatusMessage] = useState({ kind: '', text: '' })

  const [wbStatus, setWbStatus] = useState(null)
  const [wsInfo, setWsInfo] = useState(null)

  const [folderPath, setFolderPath] = useState('')
  const [createIfMissing, setCreateIfMissing] = useState(true)
  const [paiosUrl, setPaiosUrl] = useState('http://127.0.0.1:8000')
  const [selectedProjectId, setSelectedProjectId] = useState('')

  const convId = activeConvId || 'conv_pm'

  const loadData = async (customUrl) => {
    setLoading(true)
    try {
      const urlParam = customUrl ? `?personal_ai_os_url=${encodeURIComponent(customUrl)}` : ''
      const [wbResp, wsResp] = await Promise.all([
        fetch(`/api/workbench/status${urlParam}`),
        fetch(`/api/conversations/${encodeURIComponent(convId)}/workspace`),
      ])
      if (wbResp.ok) {
        const wb = await wbResp.json()
        setWbStatus(wb)
        if (!customUrl && wb.personal_ai_os?.url) {
          setPaiosUrl(wb.personal_ai_os.url)
        }
        const projs = wb.personal_ai_os?.projects || []
        if (projs.length > 0 && !selectedProjectId) {
          setSelectedProjectId(projs[0].id)
        }
      }
      if (wsResp.ok) {
        const ws = await wsResp.json()
        setWsInfo(ws)
        setFolderPath(ws.bound_path || '')
      }
    } catch (err) {
      setStatusMessage({ kind: 'error', text: `加载工作台状态失败：${err.message}` })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    const handleClose = () => {
      dialog.returnValue = ''
      onClose?.()
    }
    dialog.addEventListener('close', handleClose)

    // Safari / older browser light-dismiss fallback when closedby="any" is unsupported
    let removeLightDismiss = null
    if (typeof HTMLDialogElement !== 'undefined' && !('closedBy' in HTMLDialogElement.prototype)) {
      const handleBackdropClick = (event) => {
        if (event.target !== dialog) return
        const rect = dialog.getBoundingClientRect()
        const inside =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width
        if (!inside) {
          dialog.close()
        }
      }
      dialog.addEventListener('click', handleBackdropClick)
      removeLightDismiss = () => dialog.removeEventListener('click', handleBackdropClick)
    }

    return () => {
      dialog.removeEventListener('close', handleClose)
      if (removeLightDismiss) removeLightDismiss()
    }
  }, [onClose])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open) {
      if (!dialog.open && typeof dialog.showModal === 'function') {
        dialog.showModal()
      }
      setStatusMessage({ kind: '', text: '' })
      loadData()
    } else if (dialog.open && typeof dialog.close === 'function') {
      dialog.close()
    }
  }, [open, convId])

  const handleBindSubmit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      const resp = await fetch(`/api/conversations/${encodeURIComponent(convId)}/workspace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: folderPath.trim(), create: createIfMissing }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '绑定本地目录失败')
      setWsInfo(data)
      setFolderPath(data.bound_path || '')
      window.dispatchEvent(new CustomEvent('agenthub:workspace-updated', { detail: data }))
      setStatusMessage({
        kind: 'ok',
        text: data.is_bound ? `已挂载本地目录：${data.path}` : '已解绑自定义目录，恢复默认隔离工作区',
      })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleUnbind = async () => {
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      const resp = await fetch(`/api/conversations/${encodeURIComponent(convId)}/workspace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: '', create: false }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '解绑失败')
      setWsInfo(data)
      setFolderPath('')
      window.dispatchEvent(new CustomEvent('agenthub:workspace-updated', { detail: data }))
      setStatusMessage({ kind: 'ok', text: '已恢复默认沙盒目录' })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleConnectMCP = async () => {
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      const resp = await fetch('/api/workbench/personal-ai-os/connect-mcp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '连接知序 MCP 失败')
      await loadData(paiosUrl)
      setStatusMessage({
        kind: 'ok',
        text: '已挂载知序（personal-ai-os）只读 MCP 工具：Agent 现可直接检索知识库与 Wiki 页面',
      })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const activateImportedConversation = async (result) => {
    await useChatStore.getState().fetchConversations()
    const target = useChatStore.getState().conversations.find((item) => item.id === result.conversation_id)
    useChatStore.getState().setActiveConversation(result.conversation_id)
    useTabStore.getState().openTab(result.conversation_id, target?.name || '知序交接任务', 'agent_pm')
  }

  const handlePullProject = async (event) => {
    event.preventDefault()
    if (!selectedProjectId) return
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      const resp = await fetch('/api/workbench/personal-ai-os/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: selectedProjectId,
          personal_ai_os_url: paiosUrl.trim(),
          workspace_path: folderPath.trim() || null,
          create_workspace: createIfMissing,
        }),
      })
      const result = await resp.json()
      if (!resp.ok) throw new Error(result.detail || '拉取知序项目任务失败')
      await activateImportedConversation(result)
      setStatusMessage({
        kind: 'ok',
        text: '已从知序拉取项目上下文并打开专属执行标签页',
      })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleImportTaskFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      if (file.size > 1024 * 1024) throw new Error('任务包 JSON 不能超过 1 MB')
      const parsed = JSON.parse(await file.text())
      if (folderPath.trim()) {
        parsed.workspace_path = folderPath.trim()
        parsed.create_workspace = createIfMissing
      }
      const resp = await fetch('/api/handoffs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      })
      const result = await resp.json()
      if (!resp.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '任务包格式无效')
      await activateImportedConversation(result)
      setStatusMessage({ kind: 'ok', text: '已导入知序任务包并打开执行会话' })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
      event.target.value = ''
    }
  }

  const handlePushReceipt = async () => {
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      const resp = await fetch('/api/workbench/personal-ai-os/push-receipt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: convId,
          project_id: wsInfo?.source_project_id || selectedProjectId || null,
          personal_ai_os_url: paiosUrl.trim(),
        }),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '回传执行回执失败')
      setStatusMessage({
        kind: 'ok',
        text: '执行回执已投递至知序「待审执行回执」队列，可回到知序批准沉淀为项目笔记',
      })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const handleDownloadReceipt = async () => {
    setBusy(true)
    setStatusMessage({ kind: '', text: '' })
    try {
      const resp = await fetch(`/api/handoffs/${encodeURIComponent(convId)}/receipt`)
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.detail || '当前会话尚未关联知序任务包')
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `execution-receipt-${data.handoff_id}.json`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setStatusMessage({ kind: 'ok', text: '已下载执行回执 JSON，可在知序项目页导入审核' })
    } catch (err) {
      setStatusMessage({ kind: 'error', text: err.message })
    } finally {
      setBusy(false)
    }
  }

  const paios = wbStatus?.personal_ai_os
  const projects = paios?.projects || []
  const canExportReceipt = Boolean(wsInfo?.has_handoff || convId.startsWith('handoff-'))

  return (
    <dialog
      ref={dialogRef}
      className="workbench-dialog"
      aria-labelledby={titleId}
      {...{ closedby: 'any' }}
    >
      <div className="workbench-dialog-header">
        <div className="workbench-dialog-title-wrap">
          <FolderGit2 size={18} />
          <h2 id={titleId}>本地项目工作区 · 知序（Personal AI OS）联动</h2>
        </div>
        <button
          type="button"
          className="slide-panel-btn"
          onClick={() => dialogRef.current?.close()}
          aria-label="关闭工作台面板"
        >
          <X size={18} />
        </button>
      </div>

      <div className="workbench-dialog-body">
        {statusMessage.text && (
          <div
            role="status"
            aria-live="polite"
            className={`workbench-alert ${statusMessage.kind === 'error' ? 'error' : 'ok'}`}
          >
            {statusMessage.text}
          </div>
        )}

        <section className="workbench-card">
          <div className="workbench-card-head">
            <h3>
              <FolderOpen size={15} /> 当前会话工作目录（{convId}）
            </h3>
            {wsInfo?.git?.is_git && (
              <span className="workbench-pill">
                Git: {wsInfo.git.branch}
                {wsInfo.git.dirty ? ' · 有未提交改动' : ' · 干净'}
              </span>
            )}
          </div>
          <p className="workbench-hint">
            可将当前会话直接绑定到本机真实代码目录（Agent 读写文件与 Git 工具均在该目录下执行，且不会自动污染你的 Git 提交历史）。
          </p>

          <form
            method="post"
            action={`/api/conversations/${encodeURIComponent(convId)}/workspace`}
            onSubmit={handleBindSubmit}
            className="workbench-form"
          >
            <div className="workbench-field">
              <label htmlFor={folderInputId}>本机项目文件夹路径（支持 ~/ 开头）</label>
              <input
                id={folderInputId}
                name="path"
                type="text"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder={wbStatus?.home_dir ? `${wbStatus.home_dir}/Projects/my-app` : '~/Projects/my-app'}
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
                autoFocus
              />
            </div>

            <div className="workbench-checkbox-row">
              <input
                id={createCheckboxId}
                name="create"
                type="checkbox"
                checked={createIfMissing}
                onChange={(e) => setCreateIfMissing(e.target.checked)}
              />
              <label htmlFor={createCheckboxId}>若目标目录尚不存在则自动创建</label>
            </div>

            <div className="workbench-actions">
              <button type="submit" className="workbench-btn primary" disabled={busy}>
                挂载到当前会话
              </button>
              {wsInfo?.is_bound && (
                <button type="button" className="workbench-btn" disabled={busy} onClick={handleUnbind}>
                  解绑并恢复默认沙盒
                </button>
              )}
            </div>
          </form>

          {wsInfo?.path && (
            <div className="workbench-meta-box">
              <div>
                <strong>当前生效路径：</strong>
                <code>{wsInfo.path}</code>
              </div>
              {wsInfo.entries?.length > 0 && (
                <div className="workbench-file-chips">
                  {wsInfo.entries.slice(0, 12).map((entry) => (
                    <span key={entry.name} className="workbench-chip">
                      {entry.is_dir ? '📁' : '📄'} {entry.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>

        <section className="workbench-card">
          <div className="workbench-card-head">
            <h3>
              <Link2 size={15} /> 知序（Personal AI OS）双核联动
            </h3>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span className={`workbench-pill ${paios?.online ? 'online' : ''}`}>
                {paios?.online ? 'HTTP 在线' : paios?.local_dir ? '离线（已识别本地库）' : '未连接'}
              </span>
              <button
                type="button"
                className="workbench-icon-btn"
                onClick={() => loadData(paiosUrl)}
                disabled={loading || busy}
                title="刷新知序连接状态"
                aria-label="刷新知序连接状态"
              >
                <RefreshCw size={14} />
              </button>
            </div>
          </div>

          <div className="workbench-mcp-bar">
            <div>
              <strong>知识库只读 MCP 检索桥：</strong>
              <span>
                {paios?.mcp_connected
                  ? '已连接（Agent 可直接调用 wiki_search / wiki_read_page）'
                  : paios?.mcp_available
                    ? `已检测到 ${paios.local_dir}`
                    : '未检测到同级 personal-ai-os 目录'}
              </span>
            </div>
            {paios?.mcp_available && (
              <button
                type="button"
                className="workbench-btn"
                disabled={busy}
                onClick={handleConnectMCP}
              >
                {paios.mcp_connected ? (
                  <>
                    <CheckCircle2 size={14} /> 重新同步 MCP
                  </>
                ) : (
                  '一键接入知序 MCP'
                )}
              </button>
            )}
          </div>

          <form
            method="post"
            action="/api/workbench/personal-ai-os/pull"
            onSubmit={handlePullProject}
            className="workbench-form"
          >
            <div className="workbench-field">
              <label htmlFor={paiosUrlId}>知序本地服务地址</label>
              <input
                id={paiosUrlId}
                name="personal_ai_os_url"
                type="url"
                value={paiosUrl}
                onChange={(e) => setPaiosUrl(e.target.value)}
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
              />
            </div>

            <div className="workbench-field">
              <label htmlFor={projectSelectId}>选择知序项目（拉取目标、证据与已批准记忆）</label>
              <select
                id={projectSelectId}
                name="project_id"
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
              >
                {projects.length === 0 ? (
                  <option value="">暂无已识别项目（可启动知序或直接导入任务包 JSON）</option>
                ) : (
                  projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} {p.goal ? `— ${p.goal.slice(0, 36)}` : ''}
                    </option>
                  ))
                )}
              </select>
            </div>

            <div className="workbench-actions">
              <button
                type="submit"
                className="workbench-btn primary"
                disabled={busy || !selectedProjectId || !paios?.online}
                title={!paios?.online ? '需先启动 personal-ai-os HTTP 服务，或使用右侧导入任务包 JSON' : ''}
              >
                <Download size={14} /> 一键拉取项目任务
              </button>

              <button
                type="button"
                className="workbench-btn"
                disabled={busy}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={14} /> 导入任务包 JSON
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json"
                hidden
                onChange={handleImportTaskFile}
              />

              {canExportReceipt && (
                <>
                  <button
                    type="button"
                    className="workbench-btn"
                    disabled={busy || !paios?.online}
                    onClick={handlePushReceipt}
                  >
                    <Send size={14} /> 一键回传执行回执
                  </button>
                  <button
                    type="button"
                    className="workbench-btn"
                    disabled={busy}
                    onClick={handleDownloadReceipt}
                  >
                    下载回执 JSON
                  </button>
                </>
              )}
            </div>
          </form>
        </section>
      </div>
    </dialog>
  )
}
