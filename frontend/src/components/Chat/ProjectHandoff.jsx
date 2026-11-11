import React, { useRef, useState } from 'react'
import { useChatStore } from '../../stores/chatStore'
import { useTabStore } from '../../stores/tabStore'

export default function ProjectHandoff({ conversationId }) {
  const fileInput = useRef(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const importTask = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true)
    try {
      if (file.size > 512000) throw new Error('任务文件超过 512 KB')
      const response = await fetch('/api/handoffs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(JSON.parse(await file.text())) })
      const result = await response.json()
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '任务文件格式无效')
      await useChatStore.getState().fetchConversations()
      const conv = useChatStore.getState().conversations.find(item => item.id === result.conversation_id)
      useChatStore.getState().setActiveConversation(result.conversation_id)
      useTabStore.getState().openTab(result.conversation_id, conv?.name || '项目任务', 'agent_pm')
      setMessage('项目材料已导入，可在聊天中开始执行')
    } catch (error) { setMessage(error.message) } finally { setBusy(false); event.target.value = '' }
  }
  const exportReceipt = async () => {
    setBusy(true)
    try {
      const response = await fetch('/api/handoffs/' + conversationId + '/receipt')
      const result = await response.json()
      if (!response.ok) throw new Error('请先导入 personal-ai-os 项目任务')
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url; link.download = 'execution-receipt-' + result.handoff_id + '.json'; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setMessage('回执已导出，可回到原项目审核导入')
    } catch (error) { setMessage(error.message) } finally { setBusy(false) }
  }
  return <div style={{ padding: '6px 16px', fontSize: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
    <button disabled={busy} onClick={() => fileInput.current.click()}>导入项目任务</button>
    <input ref={fileInput} type="file" accept=".json" hidden onChange={importTask} />
    {conversationId?.startsWith('handoff-') && <button disabled={busy} onClick={exportReceipt}>导出执行回执</button>}
    {message && <span role="status">{message}</span>}
  </div>
}
