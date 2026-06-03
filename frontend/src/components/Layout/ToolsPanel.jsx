import React, { useState, useEffect } from 'react'
import { Wrench, Play, ChevronRight, Loader } from 'lucide-react'

export default function ToolsPanel({ onClose }) {
  const [tools, setTools] = useState([])
  const [loading, setLoading] = useState(false)
  const [testName, setTestName] = useState('')
  const [testParams, setTestParams] = useState('{}')
  const [testResult, setTestResult] = useState(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch('/api/runtime-tools')
      .then((r) => r.json())
      .then((data) => setTools(Array.isArray(data) ? data : []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleToggle = async (toolName) => {
    try {
      await fetch(`/api/runtime-tools/${toolName}/toggle`, { method: 'POST' })
      setTools((prev) => prev.map((t) =>
        t.name === toolName ? { ...t, enabled: !t.enabled } : t
      ))
    } catch {}
  }

  const handleTest = async () => {
    if (!testName) return
    setTesting(true)
    setTestResult(null)
    try {
      let params = {}
      try { params = JSON.parse(testParams) } catch {}
      const resp = await fetch(`/api/runtime-tools/${testName}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      const data = await resp.json()
      setTestResult(data)
    } catch (e) {
      setTestResult({ success: false, error: e.message })
    }
    setTesting(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 头部 */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
      }}>
        <Wrench size={16} color="var(--accent)" />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>工具管理</span>
        <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {tools.length} 个工具
        </span>
      </div>

      {/* 工具列表 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24, fontSize: 12 }}>
            加载中...
          </div>
        ) : tools.length === 0 ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24, fontSize: 12 }}>
            暂无注册工具
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {tools.map((tool) => (
              <div key={tool.name} style={{
                padding: '10px 12px', borderRadius: 8,
                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                    {tool.icon} {tool.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {tool.description}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
                  <span style={{
                    fontSize: 10, padding: '2px 8px', borderRadius: 4,
                    background: tool.enabled ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                    color: tool.enabled ? 'var(--green)' : 'var(--red)',
                    border: `1px solid ${tool.enabled ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
                  }}>
                    {tool.enabled ? '启用' : '禁用'}
                  </span>
                  <button
                    onClick={() => handleToggle(tool.name)}
                    style={{
                      padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                      background: tool.enabled ? 'rgba(239,68,68,0.08)' : 'rgba(16,185,129,0.08)',
                      border: `1px solid ${tool.enabled ? 'rgba(239,68,68,0.15)' : 'rgba(16,185,129,0.15)'}`,
                      color: tool.enabled ? 'var(--red)' : 'var(--green)',
                    }}
                  >
                    {tool.enabled ? '禁用' : '启用'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 工具测试区 */}
        <div style={{
          marginTop: 20, padding: '12px', borderRadius: 8,
          background: 'var(--bg-secondary)', border: '1px solid var(--border)',
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>
            工具测试
          </div>
          <select
            value={testName}
            onChange={(e) => { setTestName(e.target.value); setTestResult(null) }}
            style={{
              width: '100%', padding: '8px 10px', marginBottom: 8,
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              borderRadius: 6, fontSize: 12, color: 'var(--text-primary)',
            }}
          >
            <option value="">选择工具...</option>
            {tools.filter((t) => t.enabled).map((t) => (
              <option key={t.name} value={t.name}>{t.icon} {t.name}</option>
            ))}
          </select>
          <textarea
            value={testParams}
            onChange={(e) => setTestParams(e.target.value)}
            style={{
              width: '100%', minHeight: 50, padding: '8px 10px', marginBottom: 8,
              background: 'var(--bg-primary)', border: '1px solid var(--border)',
              borderRadius: 6, fontSize: 11, color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)', resize: 'vertical',
            }}
            placeholder='参数 JSON，如: {"query": "FastAPI 教程"}'
          />
          <button
            onClick={handleTest}
            disabled={testing || !testName}
            style={{
              width: '100%', padding: '8px', borderRadius: 6, fontSize: 12,
              background: 'var(--accent)', border: 'none', color: 'white',
              cursor: testing || !testName ? 'default' : 'pointer',
              fontWeight: 500, opacity: testing || !testName ? 0.5 : 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
            }}
          >
            {testing ? <><Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> 执行中...</> : <><Play size={12} /> 执行测试</>}
          </button>
          {testResult && (
            <div style={{
              marginTop: 10, padding: '8px 10px', borderRadius: 6,
              background: testResult.success ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
              border: `1px solid ${testResult.success ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'}`,
              maxHeight: 150, overflowY: 'auto',
            }}>
              <div style={{ fontSize: 11, color: testResult.success ? 'var(--green)' : 'var(--red)', fontWeight: 600, marginBottom: 4 }}>
                {testResult.success ? '成功' : '失败'} {testResult.usage?.time_ms ? `(${testResult.usage.time_ms}ms)` : ''}
              </div>
              <pre style={{
                fontSize: 10, color: 'var(--text-secondary)',
                whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0,
              }}>
                {JSON.stringify(testResult.data || testResult.error, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
