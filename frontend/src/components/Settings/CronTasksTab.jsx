import React from 'react'
import { labelStyle, inputStyle, makeBtnStyle } from './sharedStyles'

export default function CronTasksTab({
  fetchCronTasks, cronLoading, cronTasks, saving,
  handleToggleCronTask, handleRunCronTaskNow, handleDeleteCronTask,
  selectedAgentForCron, setSelectedAgentForCron, cronInterval, setCronInterval,
  cronPrompt, setCronPrompt, handleAddCronTask,
}) {
  const btnStyle = makeBtnStyle(saving)

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)',
        fontSize: 13, color: 'var(--accent)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span>Always-on 离线常驻自治 — 网页关闭后 Agent 仍能后台自主开发</span>
        <button onClick={fetchCronTasks} disabled={cronLoading} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
          background: 'var(--accent)', color: 'white', border: 'none', cursor: 'pointer',
          opacity: cronLoading ? 0.6 : 1,
        }}>{cronLoading ? '...' : '刷新'}</button>
      </div>

      {/* Task List */}
      <div style={{ marginBottom: 20 }}>
        <label style={labelStyle}>当前后台自治作业</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '25vh', overflowY: 'auto' }}>
          {cronTasks.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '16px 0', fontSize: 12 }}>
              暂无活动中的后台自治作业
            </div>
          ) : (
            cronTasks.map((t) => (
              <div key={t.id} style={{
                padding: '10px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                border: `1px solid ${t.status === 'running' ? 'var(--accent)' : t.status === 'active' ? 'rgba(16, 185, 129, 0.25)' : 'rgba(245, 158, 11, 0.2)'}`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {t.status === 'running' ? '🔵' : t.status === 'active' ? '🟢' : '🟡'} {t.agent_id}
                  </span>
                  <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>每 {t.interval_seconds}s</span>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>{t.task_prompt.slice(0, 60)}...</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button onClick={() => handleToggleCronTask(t.id, t.status)} disabled={saving} style={{
                    padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                    background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)',
                  }}>{t.status === 'active' ? '暂停' : '恢复'}</button>
                  <button onClick={() => handleRunCronTaskNow(t.id)} disabled={saving || t.status === 'running'} style={{
                    padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                    background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', color: 'var(--accent)',
                  }}>立即执行</button>
                  <button onClick={() => handleDeleteCronTask(t.id)} disabled={saving} style={{
                    padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                    background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', color: 'var(--red)',
                  }}>删除</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Create Form */}
      <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>创建新离线自治任务</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', gap: 10 }}>
            <div style={{ flex: 1 }}>
              <label style={{ ...labelStyle, fontSize: 11 }}>执行 Agent</label>
              <select value={selectedAgentForCron} onChange={(e) => setSelectedAgentForCron(e.target.value)} style={inputStyle}>
                <option value="agent_pm">PM 小助手</option>
                <option value="agent_frontend">前端工程师</option>
                <option value="agent_backend">后端工程师</option>
                <option value="agent_tester">测试工程师</option>
                <option value="agent_devops">运维工程师</option>
                <option value="agent_designer">设计顾问</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ ...labelStyle, fontSize: 11 }}>自治周期</label>
              <select value={cronInterval} onChange={(e) => setCronInterval(parseInt(e.target.value))} style={inputStyle}>
                <option value={60}>每分钟 (自测)</option>
                <option value={300}>每 5 分钟</option>
                <option value={1800}>每 30 分钟</option>
                <option value={3600}>每小时</option>
                <option value={86400}>每日</option>
              </select>
            </div>
          </div>
          <div>
            <label style={{ ...labelStyle, fontSize: 11 }}>自治 Prompt 指令</label>
            <textarea
              value={cronPrompt}
              onChange={(e) => setCronPrompt(e.target.value)}
              rows={3}
              style={{ ...inputStyle, resize: 'vertical', lineHeight: '1.5' }}
              placeholder="输入分配给 Agent 的后台离线自治开发/检测指令..."
            />
          </div>
          <button onClick={handleAddCronTask} disabled={saving || !cronPrompt.trim()} style={btnStyle}>
            {saving ? '正在处理...' : '创建常驻离线自治任务'}
          </button>
        </div>
      </div>
    </>
  )
}
