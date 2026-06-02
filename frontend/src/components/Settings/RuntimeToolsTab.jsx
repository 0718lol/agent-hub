import React from 'react'

export default function RuntimeToolsTab({
  isDark, saving, rtTools, rtLoading, handleToggleRtTool,
  rtTestName, setRtTestName, rtTestParams, setRtTestParams,
  handleTestRtTool, rtTestResult,
}) {
  const labelStyle = {
    fontSize: 13,
    color: 'var(--text-muted)',
    marginBottom: 6,
    display: 'block',
    fontWeight: 500,
  }

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-primary)',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'inherit',
  }

  const btnStyle = {
    width: '100%',
    padding: '12px',
    borderRadius: 10,
    background: '#4f46e5',
    border: 'none',
    color: 'white',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    opacity: saving ? 0.6 : 1,
    transition: 'all 0.2s',
  }

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
        fontSize: 13, color: isDark ? '#a5b4fc' : '#4338ca',
      }}>
        Agent 可通过 <code>[tool_call:name]</code> 标签调用以下工具，系统自动执行并返回结果
      </div>

      {/* Tool List */}
      <div style={{ marginBottom: 20 }}>
        <label style={labelStyle}>已注册工具 ({rtTools.length})</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rtLoading ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 12 }}>加载中...</div>
          ) : rtTools.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 12 }}>暂无工具</div>
          ) : (
            rtTools.map((tool) => (
              <div key={tool.name} style={{
                padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {tool.icon} {tool.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {tool.description}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{
                    fontSize: 10, padding: '2px 8px', borderRadius: 4,
                    background: tool.enabled ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : (isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2'),
                    color: tool.enabled ? '#059669' : (isDark ? '#f87171' : '#dc2626'),
                    border: `1px solid ${tool.enabled ? (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0') : (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca')}`,
                  }}>{tool.enabled ? '启用' : '禁用'}</span>
                  <button onClick={() => handleToggleRtTool(tool.name)} style={{
                    padding: '4px 10px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                    background: tool.enabled ? (isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2') : (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5'),
                    border: `1px solid ${tool.enabled ? (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca') : (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0')}`,
                    color: tool.enabled ? (isDark ? '#f87171' : '#dc2626') : '#059669',
                  }}>{tool.enabled ? '禁用' : '启用'}</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Test Tool */}
      <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>工具测试</label>
        <div style={{ marginBottom: 10 }}>
          <select
            value={rtTestName}
            onChange={(e) => setRtTestName(e.target.value)}
            style={{ ...inputStyle, marginBottom: 8 }}
          >
            <option value="">选择工具...</option>
            {rtTools.filter(t => t.enabled).map((t) => (
              <option key={t.name} value={t.name}>{t.icon} {t.name}</option>
            ))}
          </select>
          <textarea
            value={rtTestParams}
            onChange={(e) => setRtTestParams(e.target.value)}
            style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            placeholder='参数 JSON，如: {"query": "FastAPI 教程"}'
          />
        </div>
        <button onClick={handleTestRtTool} disabled={saving || !rtTestName} style={{
          ...btnStyle, background: '#059669',
          opacity: (saving || !rtTestName) ? 0.6 : 1,
        }}>执行测试</button>
        {rtTestResult && (
          <div style={{
            marginTop: 12, padding: '10px', borderRadius: 8,
            background: rtTestResult.success ? (isDark ? 'rgba(34,197,94,0.08)' : '#f0fdf4') : (isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2'),
            border: `1px solid ${rtTestResult.success ? (isDark ? 'rgba(34,197,94,0.2)' : '#bbf7d0') : (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca')}`,
            maxHeight: '25vh', overflowY: 'auto',
          }}>
            <div style={{ fontSize: 11, color: rtTestResult.success ? 'var(--text-primary)' : (isDark ? '#f87171' : 'var(--danger, #dc2626)'), fontWeight: 600, marginBottom: 4 }}>
              {rtTestResult.success ? '✅ 成功' : '❌ 失败'} {rtTestResult.usage?.time_ms ? `(${rtTestResult.usage.time_ms}ms)` : ''}
            </div>
            <pre style={{
              fontSize: 11, color: 'var(--text-primary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              margin: 0, maxHeight: '20vh', overflow: 'auto',
            }}>
              {JSON.stringify(rtTestResult.data || rtTestResult.error, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </>
  )
}
