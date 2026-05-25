import React, { useState, useRef } from 'react'
import { X, Upload } from 'lucide-react'
import { useAgentStore } from '../../stores/agentStore'

const emojiOptions = ['🤖', '🧠', '💻', '🎨', '🔧', '🐛', '🚀', '📊', '⚡', '🛡️']

export default function AgentCreator({ onClose, onBack }) {
  const addCustomAgent = useAgentStore((s) => s.addCustomAgent)
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [avatar, setAvatar] = useState('🤖')
  const [avatarPreview, setAvatarPreview] = useState(null) // 本地预览 URL
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const avatarFileRef = useRef(null)

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploadingAvatar(true)
    try {
      // 本地预览
      const previewUrl = URL.createObjectURL(file)
      setAvatarPreview(previewUrl)

      // 上传到服务器
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/upload', { method: 'POST', body: formData })
      const data = await resp.json()
      if (data.status === 'uploaded') {
        setAvatar(data.url) // 存储服务器 URL
      }
    } catch {}
    setUploadingAvatar(false)
    if (avatarFileRef.current) avatarFileRef.current.value = ''
  }

  const handleCreate = async () => {
    if (!name.trim()) {
      setError('请输入 Agent 名称')
      return
    }
    setSaving(true)
    setError('')
    try {
      const resp = await fetch('/api/agents/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          avatar: avatar || '🤖',
          role: role.trim(),
          style: 'custom',
          system_prompt: '',
          tools: [],
        }),
      })
      const data = await resp.json()
      if (data.status === 'created') {
        addCustomAgent(data.agent)
        onClose()
      } else {
        setError('创建失败，请重试')
      }
    } catch {
      setError('网络错误，请检查后端是否运行')
    }
    setSaving(false)
  }

  return (
    <div className="agent-creator-overlay" onClick={onClose}>
      <div className="agent-creator" onClick={(e) => e.stopPropagation()}>
        <div className="agent-selector-header">
          <span className="agent-selector-title">创建 Agent</span>
          <button className="agent-selector-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        <div className="agent-create-form" style={{ borderTop: 'none', paddingTop: 0, marginTop: 0 }}>
          <div className="agent-create-field">
            <label className="agent-create-label">名称 *</label>
            <input
              className="agent-create-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="输入 Agent 名称"
              autoFocus
            />
          </div>
          <div className="agent-create-field">
            <label className="agent-create-label">描述</label>
            <textarea
              className="agent-create-textarea"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="描述 Agent 的角色和能力，例如：数据分析专家，擅长 Python 和 SQL"
              rows={1}
            />
          </div>
          <div className="agent-create-field">
            <label className="agent-create-label">头像</label>

            {/* 图片上传预览 */}
            {avatarPreview && (
              <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
                <img
                  src={avatarPreview}
                  alt="头像预览"
                  style={{
                    width: 56, height: 56, borderRadius: 'var(--radius-md)',
                    objectFit: 'cover', border: '2px solid var(--accent)',
                  }}
                />
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                  {uploadingAvatar ? '上传中...' : '已设置自定义头像'}
                </div>
              </div>
            )}

            {/* Emoji 选择（一行） */}
            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
              {emojiOptions.map((emoji) => (
                <button
                  key={emoji}
                  className={`agent-emoji-btn ${avatar === emoji && !avatarPreview ? 'active' : ''}`}
                  onClick={() => { setAvatar(emoji); setAvatarPreview(null) }}
                  type="button"
                >
                  {emoji}
                </button>
              ))}
            </div>

            {/* 本地上传 + 手动输入 */}
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button
                className="agent-create-btn"
                onClick={() => avatarFileRef.current?.click()}
                style={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)' }}
                type="button"
              >
                <Upload size={14} />
                本地上传
              </button>
              <input
                className="agent-create-input"
                value={avatarPreview ? '' : avatar}
                onChange={(e) => { setAvatar(e.target.value); setAvatarPreview(null) }}
                placeholder="或输入 emoji"
                style={{ flex: 1 }}
              />
              <input
                ref={avatarFileRef}
                type="file"
                accept="image/*"
                onChange={handleAvatarUpload}
                style={{ display: 'none' }}
              />
            </div>
          </div>
          {error && <div className="agent-create-error">{error}</div>}
          <div className="agent-create-actions">
            <button className="agent-create-btn primary" onClick={handleCreate} disabled={saving}>
              {saving ? '创建中...' : '创建 Agent'}
            </button>
            <button
              className="agent-create-btn"
              onClick={() => { setError(''); onBack() }}
            >
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
