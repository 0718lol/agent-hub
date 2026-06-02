import React from 'react'
import styles from './SettingsPanel.module.css'

export default function CronTasksTab({
  isDark, saving, cronLoading, cronTasks, fetchCronTasks,
  handleToggleCronTask, handleRunCronTaskNow, handleDeleteCronTask,
  selectedAgentForCron, setSelectedAgentForCron, cronInterval, setCronInterval,
  cronPrompt, setCronPrompt, handleAddCronTask,
}) {
  return (
    <>
      <div className={styles.cronInfoBox} style={{
        background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`,
        color: isDark ? '#a5b4fc' : '#4338ca',
      }}>
        <span>Always-on 离线常驻自治 — 网页关闭后 Agent 仍能后台自主开发</span>
        <button onClick={fetchCronTasks} disabled={cronLoading} className={styles.cronRefreshBtn}
          style={{ opacity: cronLoading ? 0.6 : 1 }}>{cronLoading ? '...' : '刷新'}</button>
      </div>

      {/* Task List */}
      <div style={{ marginBottom: 20 }}>
        <label className={styles.label}>当前后台自治作业</label>
        <div className={styles.scrollList}>
          {cronTasks.length === 0 ? (
            <div className={styles.emptyText}>
              暂无活动中的后台自治作业
            </div>
          ) : (
            cronTasks.map((t) => (
              <div key={t.id} className={styles.taskItem} style={{
                border: `1px solid ${t.status === 'running' ? '#a78bfa' : t.status === 'active' ? (isDark ? 'rgba(34,197,94,0.25)' : '#a7f3d0') : (isDark ? 'rgba(245,158,11,0.25)' : '#fde68a')}`,
              }}>
                <div className={styles.taskHeader}>
                  <span className={styles.taskAgent}>
                    {t.status === 'running' ? '🔵' : t.status === 'active' ? '🟢' : '🟡'} {t.agent_id}
                  </span>
                  <span className={styles.taskInterval}>每 {t.interval_seconds}s</span>
                </div>
                <div className={styles.taskPrompt}>{t.task_prompt.slice(0, 60)}...</div>
                <div className={styles.taskActions}>
                  <button onClick={() => handleToggleCronTask(t.id, t.status)} disabled={saving} className={styles.actionBtn} style={{
                    background: isDark ? 'rgba(255,255,255,0.06)' : '#f3f4f6', border: `1px solid ${isDark ? 'rgba(255,255,255,0.15)' : '#d1d5db'}`, color: isDark ? '#e5e7eb' : '#374151',
                  }}>{t.status === 'active' ? '暂停' : '恢复'}</button>
                  <button onClick={() => handleRunCronTaskNow(t.id)} disabled={saving || t.status === 'running'} className={styles.actionBtn} style={{
                    background: isDark ? 'rgba(99,102,241,0.12)' : '#eef2ff', border: `1px solid ${isDark ? 'rgba(99,102,241,0.25)' : '#c7d2fe'}`, color: isDark ? '#a5b4fc' : '#4338ca',
                  }}>立即执行</button>
                  <button onClick={() => handleDeleteCronTask(t.id)} disabled={saving} className={styles.actionBtn} style={{
                    background: isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2', border: `1px solid ${isDark ? 'rgba(239,68,68,0.25)' : '#fecaca'}`, color: isDark ? '#f87171' : '#dc2626',
                  }}>删除</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Create Form */}
      <div className={styles.createForm}>
        <label className={styles.sectionTitle}>创建新离线自治任务</label>
        <div className={styles.formGroup}>
          <div className={styles.formRow}>
            <div className={styles.formCol}>
              <label className={styles.formLabel}>执行 Agent</label>
              <select value={selectedAgentForCron} onChange={(e) => setSelectedAgentForCron(e.target.value)} className={styles.inputSecondary}>
                <option value="agent_pm">PM 小助手</option>
                <option value="agent_frontend">前端工程师</option>
                <option value="agent_backend">后端工程师</option>
                <option value="agent_tester">测试工程师</option>
                <option value="agent_devops">运维工程师</option>
                <option value="agent_designer">设计顾问</option>
              </select>
            </div>
            <div className={styles.formCol}>
              <label className={styles.formLabel}>自治周期</label>
              <select value={cronInterval} onChange={(e) => setCronInterval(parseInt(e.target.value))} className={styles.inputSecondary}>
                <option value={60}>每分钟 (自测)</option>
                <option value={300}>每 5 分钟</option>
                <option value={1800}>每 30 分钟</option>
                <option value={3600}>每小时</option>
                <option value={86400}>每日</option>
              </select>
            </div>
          </div>
          <div>
            <label className={styles.formLabel}>自治 Prompt 指令</label>
            <textarea
              value={cronPrompt}
              onChange={(e) => setCronPrompt(e.target.value)}
              rows={3}
              className={styles.inputSecondary}
              style={{ resize: 'vertical', lineHeight: '1.5' }}
              placeholder="输入分配给 Agent 的后台离线自治开发/检测指令..."
            />
          </div>
          <button onClick={handleAddCronTask} disabled={saving || !cronPrompt.trim()} className={styles.saveBtn} style={{ opacity: saving ? 0.6 : 1 }}>
            {saving ? '正在处理...' : '创建常驻离线自治任务'}
          </button>
        </div>
      </div>
    </>
  )
}
