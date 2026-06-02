import React from 'react'
import styles from './SettingsPanel.module.css'

export default function RuntimeToolsTab({
  isDark, saving, rtTools, rtLoading, handleToggleRtTool,
  rtTestName, setRtTestName, rtTestParams, setRtTestParams,
  handleTestRtTool, rtTestResult,
}) {
  return (
    <>
      <div className={styles.tabInfoBox} style={{
        background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
        color: isDark ? '#a5b4fc' : '#4338ca',
      }}>
        Agent 可通过 <code>[tool_call:name]</code> 标签调用以下工具，系统自动执行并返回结果
      </div>

      {/* Tool List */}
      <div style={{ marginBottom: 20 }}>
        <label className={styles.label}>已注册工具 ({rtTools.length})</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rtLoading ? (
            <div className={styles.emptyText}>加载中...</div>
          ) : rtTools.length === 0 ? (
            <div className={styles.emptyText}>暂无工具</div>
          ) : (
            rtTools.map((tool) => (
              <div key={tool.name} className={styles.toolItem}>
                <div className={styles.layerBody}>
                  <div className={styles.toolName}>
                    {tool.icon} {tool.name}
                  </div>
                  <div className={styles.toolDesc}>
                    {tool.description}
                  </div>
                </div>
                <div className={styles.toolActions}>
                  <span className={styles.statusBadge} style={{
                    background: tool.enabled ? (isDark ? 'rgba(34,197,94,0.12)' : '#ecfdf5') : (isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2'),
                    color: tool.enabled ? '#059669' : (isDark ? '#f87171' : '#dc2626'),
                    border: `1px solid ${tool.enabled ? (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0') : (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca')}`,
                  }}>{tool.enabled ? '启用' : '禁用'}</span>
                  <button onClick={() => handleToggleRtTool(tool.name)} className={styles.toggleToolBtn} style={{
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
      <div className={styles.testCard}>
        <label className={styles.sectionTitle}>工具测试</label>
        <div style={{ marginBottom: 10 }}>
          <select
            value={rtTestName}
            onChange={(e) => setRtTestName(e.target.value)}
            className={styles.inputSecondary}
            style={{ marginBottom: 8 }}
          >
            <option value="">选择工具...</option>
            {rtTools.filter(t => t.enabled).map((t) => (
              <option key={t.name} value={t.name}>{t.icon} {t.name}</option>
            ))}
          </select>
          <textarea
            value={rtTestParams}
            onChange={(e) => setRtTestParams(e.target.value)}
            className={styles.inputSecondary}
            style={{ minHeight: 60, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            placeholder='参数 JSON，如: {"query": "FastAPI 教程"}'
          />
        </div>
        <button onClick={handleTestRtTool} disabled={saving || !rtTestName} className={styles.saveBtn} style={{
          background: '#059669',
          opacity: (saving || !rtTestName) ? 0.6 : 1,
        }}>执行测试</button>
        {rtTestResult && (
          <div className={styles.testResult} style={{
            background: rtTestResult.success ? (isDark ? 'rgba(34,197,94,0.08)' : '#f0fdf4') : (isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2'),
            border: `1px solid ${rtTestResult.success ? (isDark ? 'rgba(34,197,94,0.2)' : '#bbf7d0') : (isDark ? 'rgba(239,68,68,0.25)' : '#fecaca')}`,
          }}>
            <div className={styles.resultTitle} style={{ color: rtTestResult.success ? 'var(--text-primary)' : (isDark ? '#f87171' : 'var(--danger, #dc2626)') }}>
              {rtTestResult.success ? '✅ 成功' : '❌ 失败'} {rtTestResult.usage?.time_ms ? `(${rtTestResult.usage.time_ms}ms)` : ''}
            </div>
            <pre className={styles.resultPre}>
              {JSON.stringify(rtTestResult.data || rtTestResult.error, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </>
  )
}
