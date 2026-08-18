import React, { useEffect, useState } from 'react'
import { Check, Pencil, Settings, Target, X } from 'lucide-react'
import { useChatStore } from '../../stores/chatStore'

const STAGES = [
  ['not_started', '未开始'],
  ['planning', '规划中'],
  ['building', '构建中'],
  ['validating', '验证中'],
  ['ready', '已就绪'],
  ['blocked', '受阻'],
]

const EMPTY_GOAL = {
  objective: '',
  stage: 'not_started',
  latestDeliverable: '',
  pendingDecision: '',
  nextAction: '',
}

export default function GoalSnapshot({ conversationId, readiness, isFirstTask }) {
  const goal = useChatStore((state) => state.conversations.find((item) => item.id === conversationId)?.goal)
  const updateGoal = useChatStore((state) => state.updateGoal)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState({ ...EMPTY_GOAL, ...goal })

  useEffect(() => {
    if (!editing) setDraft({ ...EMPTY_GOAL, ...goal })
  }, [goal, editing])

  const save = async () => {
    if (!draft.objective.trim()) return
    setSaving(true)
    const saved = await updateGoal(conversationId, {
      objective: draft.objective.trim(),
      stage: draft.stage,
      latestDeliverable: draft.latestDeliverable.trim() || null,
      pendingDecision: draft.pendingDecision.trim() || null,
      nextAction: draft.nextAction.trim() || null,
    })
    setSaving(false)
    if (saved) setEditing(false)
  }

  const openModelSettings = () => {
    window.dispatchEvent(new CustomEvent('open-settings', { detail: { tab: 'llm' } }))
  }

  const stageLabel = STAGES.find(([value]) => value === goal?.stage)?.[1] || '未开始'
  const showPreflight = isFirstTask && readiness && !readiness.loading

  return (
    <section className="goal-snapshot" aria-label="当前目标">
      {showPreflight && (
        <div className={`task-preflight ${readiness.service === 'offline' ? 'error' : readiness.model === 'demo' ? 'warning' : 'ready'}`}>
          <span className="task-preflight-dot" />
          <strong>{readiness.service === 'offline' ? '服务离线' : readiness.model === 'demo' ? '演示模式' : '模型已连接'}</strong>
          <span>{readiness.buildServices === 'ready' ? '构建服务已就绪' : '后台构建受限'}</span>
          {readiness.model === 'demo' && readiness.service === 'online' && (
            <button type="button" onClick={openModelSettings} title="连接模型" aria-label="连接模型">
              <Settings size={14} />
            </button>
          )}
        </div>
      )}

      {editing ? (
        <div className="goal-editor">
          <label className="goal-objective-field">
            <span>目标</span>
            <input
              autoFocus
              maxLength={2000}
              value={draft.objective}
              onChange={(event) => setDraft((current) => ({ ...current, objective: event.target.value }))}
              placeholder="这段对话要持续完成什么？"
            />
          </label>
          <label>
            <span>阶段</span>
            <select value={draft.stage} onChange={(event) => setDraft((current) => ({ ...current, stage: event.target.value }))}>
              {STAGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>
            <span>待决事项</span>
            <input maxLength={1000} value={draft.pendingDecision} onChange={(event) => setDraft((current) => ({ ...current, pendingDecision: event.target.value }))} />
          </label>
          <label>
            <span>下一步</span>
            <input maxLength={1000} value={draft.nextAction} onChange={(event) => setDraft((current) => ({ ...current, nextAction: event.target.value }))} />
          </label>
          <div className="goal-editor-actions">
            <button type="button" onClick={() => setEditing(false)} title="取消" aria-label="取消编辑目标"><X size={15} /></button>
            <button type="button" className="primary" disabled={saving || !draft.objective.trim()} onClick={save} title="保存" aria-label="保存目标"><Check size={15} /></button>
          </div>
        </div>
      ) : (
        <div className="goal-summary">
          <Target size={16} />
          <div className="goal-summary-main">
            <div className="goal-summary-objective">{goal?.objective || '尚未设置持续目标'}</div>
            {(goal?.latestDeliverable || goal?.pendingDecision || goal?.nextAction) && (
              <div className="goal-summary-details">
                {goal.latestDeliverable && <span>产物：{goal.latestDeliverable}</span>}
                {goal.pendingDecision && <span>待确认：{goal.pendingDecision}</span>}
                {goal.nextAction && <span>下一步：{goal.nextAction}</span>}
              </div>
            )}
          </div>
          <span className={`goal-stage stage-${goal?.stage || 'not_started'}`}>{stageLabel}</span>
          <button type="button" className="goal-edit-button" onClick={() => setEditing(true)} title="编辑目标" aria-label="编辑目标"><Pencil size={14} /></button>
        </div>
      )}
    </section>
  )
}
