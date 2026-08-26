import React from 'react'
import { Check, ExternalLink, Loader } from 'lucide-react'
import IconAvatar from '../IconAvatar'
import AvatarUploadField from './AvatarUploadField'

export default function AdaptersTab({
  adapterMsg, ADAPTER_META, adapters, adapterEditing, setAdapterEditing,
  adapterForm, setAdapterForm, proxyRunning, proxyLoading, handleStartProxy,
  handleStopProxy, handleSaveAdapter, handleTestAdapter, testingAdapter,
}) {
  return (
    <>
      <div style={{ padding: '12px 14px', borderRadius: 8, marginBottom: 20, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', fontSize: 12, color: 'var(--accent)', lineHeight: 1.8 }}>
        外部 Agent 可以通过平台 API 或本机 CLI 接入。<br />
        「Agent 回复」— 调用 Agent 平台 API（如 Claude Code、Coze），具备工具调用、多轮推理等完整能力，需 Agent 平台 Key。<br />
        「LLM 回复」— 调用通用大模型 API（如 DeepSeek、Qwen），仅做纯文本对话，需模型 Key。<br />
        「自动探测」— 根据模型名和地址自动判断。
      </div>

      {adapterMsg && (
        <div style={{
          padding: '10px 14px', borderRadius: 8, marginBottom: 16, fontSize: 13,
          background: adapterMsg.startsWith('✅') ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
          border: `1px solid ${adapterMsg.startsWith('✅') ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
          color: adapterMsg.startsWith('✅') ? 'var(--green)' : 'var(--red)',
        }}>{adapterMsg}</div>
      )}

      {Object.entries(ADAPTER_META).map(([agentId, meta]) => {
        const adapter = adapters.find((a) => a.agent_id === agentId)
        const isConfigured = adapter?.configured ?? false
        const isEditing = adapterEditing === agentId

        return (
          <div key={agentId} style={{
            border: '1px solid var(--border)', borderRadius: 12, marginBottom: 16,
            overflow: 'hidden',
          }}>
            {/* 头部 */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px',
              background: isConfigured ? 'rgba(16, 185, 129, 0.06)' : 'var(--bg-secondary)',
              borderBottom: isEditing ? '1px solid var(--border)' : 'none',
            }}>
              <div style={{
                width: 36, height: 36, borderRadius: 8,
                background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                overflow: 'hidden', flexShrink: 0,
              }}>
                <IconAvatar agentId={agentId} size={20} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{meta.name}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 1 }}>{meta.description}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                {isConfigured ? (
                  <span style={{ fontSize: 11, color: 'var(--green)', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Check size={12} /> {agentId === 'codex' ? '已连接' : '已配置'}
                  </span>
                ) : (
                  <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>未配置</span>
                )}
                {agentId === 'self_deployed' && (
                  <button
                    onClick={() => proxyRunning ? handleStopProxy() : handleStartProxy()}
                    disabled={proxyLoading}
                    style={{
                      padding: '4px 10px', borderRadius: 6, fontSize: 11,
                      background: proxyRunning ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                      border: `1px solid ${proxyRunning ? 'rgba(239, 68, 68, 0.3)' : 'rgba(16, 185, 129, 0.3)'}`,
                      color: proxyRunning ? 'var(--red, #ef4444)' : 'var(--green)',
                      cursor: proxyLoading ? 'default' : 'pointer',
                      fontWeight: 500,
                    }}
                  >
                    {proxyLoading ? '处理中...' : proxyRunning ? '停止代理' : '启动代理'}
                  </button>
                )}
                <button
                  onClick={() => {
                    if (isEditing) {
                      setAdapterEditing(null)
                      setAdapterForm({ api_key: '', api_url: '', model: '', tool_mode: 'agent', bot_id: '', user_id: '', platform: 'opencode', codex_path: '', workspace: '', sandbox: 'workspace-write', display_name: '', display_avatar: '', display_desc: '' })
                    } else {
                      setAdapterEditing(agentId)
                      setAdapterForm({
                        api_key: '',
                        api_url: '',
                        model: adapter?.model || '',
                        tool_mode: adapter?.tool_mode || 'agent',
                        bot_id: adapter?.extra?.bot_id || '',
                        user_id: adapter?.extra?.user_id || '',
                        platform: adapter?.extra?.platform || 'opencode',
                        codex_path: adapter?.extra?.codex_path || '',
                        workspace: adapter?.extra?.workspace || '',
                        sandbox: adapter?.extra?.sandbox || 'workspace-write',
                        display_name: adapter?.display_name || '',
                        display_avatar: adapter?.display_avatar || '',
                        display_desc: adapter?.display_desc || '',
                      })
                    }
                  }}
                  style={{
                    padding: '5px 12px', borderRadius: 6, fontSize: 12,
                    background: isEditing ? 'var(--bg-tertiary)' : 'var(--accent)',
                    border: isEditing ? '1px solid var(--border)' : '1px solid var(--accent)',
                    color: isEditing ? 'var(--text-secondary)' : 'white',
                    cursor: 'pointer', fontWeight: 500,
                  }}
                >
                  {isEditing ? '取消' : isConfigured ? '修改' : agentId === 'codex' ? '连接' : '配置'}
                </button>
              </div>
            </div>

            {/* 编辑表单 */}
            {isEditing && (
              <div style={{ padding: '16px', background: 'var(--bg-primary)' }}>
                {meta.fields.map((field) => (
                  <div key={field.key} style={{ marginBottom: 12 }}>
                    <label style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4, display: 'block', fontWeight: 500 }}>
                      {field.label}
                    </label>
                    {field.key === 'display_avatar' && (agentId === 'self_deployed' || agentId.startsWith('local_agent_')) ? (
                      <AvatarUploadField
                        value={adapterForm.display_avatar}
                        onChange={(val) => setAdapterForm({ ...adapterForm, display_avatar: val })}
                      />
                    ) : field.type === 'select' ? (
                      <select
                        value={adapterForm[field.key] || field.options[0]?.value || ''}
                        onChange={(e) => setAdapterForm({ ...adapterForm, [field.key]: e.target.value })}
                        style={{
                          width: '100%', padding: '9px 12px',
                          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                          borderRadius: 8, fontSize: 13, color: 'var(--text-primary)',
                          outline: 'none', fontFamily: 'inherit',
                        }}
                      >
                        {field.options.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={field.type}
                        value={adapterForm[field.key] || ''}
                        onChange={(e) => setAdapterForm({ ...adapterForm, [field.key]: e.target.value })}
                        placeholder={field.placeholder}
                        style={{
                          width: '100%', padding: '9px 12px',
                          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                          borderRadius: 8, fontSize: 13, color: 'var(--text-primary)',
                          outline: 'none', fontFamily: 'inherit',
                        }}
                      />
                    )}
                  </div>
                ))}
                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                  <button
                    onClick={() => handleSaveAdapter(agentId)}
                    style={{
                      padding: '8px 20px', borderRadius: 8, fontSize: 13,
                      background: 'var(--accent)', border: 'none', color: 'white',
                      cursor: 'pointer', fontWeight: 600,
                    }}
                  >
                    {agentId === 'codex' ? '连接 Codex' : '保存配置'}
                  </button>
                  {isConfigured && (
                    <button
                      onClick={() => handleTestAdapter(agentId)}
                      disabled={testingAdapter === agentId}
                      style={{
                        padding: '8px 16px', borderRadius: 8, fontSize: 13,
                        background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.25)',
                        color: 'var(--green)', cursor: 'pointer', fontWeight: 500,
                        display: 'flex', alignItems: 'center', gap: 4,
                      }}
                    >
                      {testingAdapter === agentId ? (
                        <><Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> 测试中...</>
                      ) : agentId === 'codex' ? '检查连接' : '测试连接'}
                    </button>
                  )}
                  {meta.helpUrl && <a
                    href={meta.helpUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      padding: '8px 16px', borderRadius: 8, fontSize: 13,
                      background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                      color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500,
                      textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    <ExternalLink size={12} /> {meta.helpLabel || '获取 Key'}
                  </a>}
                  {meta.docUrl && (
                    <a
                      href={meta.docUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        padding: '8px 16px', borderRadius: 8, fontSize: 13,
                        background: 'var(--bg-tertiary)', border: '1px solid var(--border)',
                        color: 'var(--text-secondary)', cursor: 'pointer', fontWeight: 500,
                        textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4,
                      }}
                    >
                      <ExternalLink size={12} /> 配置文档
                    </a>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </>
  )
}
