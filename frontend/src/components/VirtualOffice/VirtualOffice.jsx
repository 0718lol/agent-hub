import React, { useState, useEffect, useMemo, useRef } from 'react'
import AgentCharacter from '../AgentCharacter/AgentCharacter'
import OfficeSlot from '../AgentCharacter/OfficeSlot'
import { AGENT_ACTIONS } from '../AgentCharacter/agentAction.types'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import './VirtualOffice.css'

const SLOT_W = 96
const SLOT_H = 130

// 工位坐标百分比 — 上半部一行 5 个
const WORKSTATION_PCT = [
  { x: 0.08, y: 0.18 },
  { x: 0.24, y: 0.18 },
  { x: 0.40, y: 0.18 },
  { x: 0.56, y: 0.18 },
  { x: 0.72, y: 0.18 },
]

// 休息位 — 下半部分散在客厅/茶水/健身/散步
const REST_SLOTS_PCT = [
  { x: 0.08, y: 0.62, type: 'sofa', label: '🛋️' },
  { x: 0.22, y: 0.62, type: 'sofa', label: '🛋️' },
  { x: 0.45, y: 0.65, type: 'coffee', label: '☕' },
  { x: 0.62, y: 0.65, type: 'walk', label: '🌿' },
  { x: 0.80, y: 0.65, type: 'gym', label: '🏋️' },
]

// 装饰家具（不参与 layout）
const FURNITURE_PCT = [
  // 工作区
  { x: 0.03, y: 0.04, emoji: '🪟', size: 44, cls: 'vo-fur-window' },
  { x: 0.94, y: 0.05, emoji: '📋', size: 38, cls: 'vo-fur-board' },
  { x: 0.42, y: 0.04, emoji: '💡', size: 28, cls: 'vo-fur-lamp' },
  { x: 0.50, y: 0.04, emoji: '💡', size: 28, cls: 'vo-fur-lamp' },
  { x: 0.58, y: 0.04, emoji: '💡', size: 28, cls: 'vo-fur-lamp' },

  // 休息区 — 客厅
  { x: 0.34, y: 0.55, emoji: '📺', size: 56, cls: 'vo-fur-tv' },
  { x: 0.155, y: 0.84, emoji: '🪑', size: 32, cls: 'vo-fur-table' },
  { x: 0.02, y: 0.50, emoji: '🪴', size: 36, cls: 'vo-fur-plant' },

  // 茶水间 / 走道
  { x: 0.475, y: 0.86, emoji: '🚰', size: 30, cls: 'vo-fur-water' },
  { x: 0.66, y: 0.85, emoji: '🌳', size: 38, cls: 'vo-fur-tree' },

  // 健身区
  { x: 0.95, y: 0.55, emoji: '🪴', size: 36, cls: 'vo-fur-plant' },
  { x: 0.85, y: 0.86, emoji: '🧘', size: 28, cls: 'vo-fur-yoga' },
]

const REST_ACTIONS_BY_TYPE = {
  sofa: AGENT_ACTIONS.SLEEP,
  coffee: AGENT_ACTIONS.COFFEE,
  gym: AGENT_ACTIONS.GYM,
  walk: AGENT_ACTIONS.WALK,
}

function hashStringToInt(s) {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

const ROLE_DEFAULT_BUBBLES = {
  agent_pm: '正在拆解任务...',
  agent_frontend: '正在写组件...',
  agent_backend: '正在写 API...',
  agent_designer: '正在画 UI...',
  agent_tester: '正在跑测试...',
  agent_devops: '正在部署...',
  agent_builder: '正在生成 agent...',
}

function getDefaultWorkBubble(agentId, tasks) {
  if (ROLE_DEFAULT_BUBBLES[agentId]) return ROLE_DEFAULT_BUBBLES[agentId]
  const myTasks = tasks.filter((t) => t.assignee === agentId)
  const inProgress = myTasks.find((t) => ['in_progress', 'doing', 'running'].includes(t.status))
  if (inProgress?.title) {
    const t = inProgress.title
    return t.length > 18 ? t.slice(0, 18) + '…' : t
  }
  const id = (agentId || '').toLowerCase()
  if (id.includes('frontend')) return '正在写组件...'
  if (id.includes('backend')) return '正在写 API...'
  if (id.includes('design')) return '正在画 UI...'
  if (id.includes('test')) return '正在跑测试...'
  if (id.includes('deploy') || id.includes('devops')) return '正在部署...'
  if (id.includes('pm')) return '正在拆解任务...'
  return '正在生成代码...'
}

function determineAgentAction(agentId, typingAgents, thinkingAgents, tasks) {
  for (const convId in typingAgents) {
    const set = typingAgents[convId]
    if (set && set.has && set.has(agentId)) {
      return { action: AGENT_ACTIONS.TALK, bubble: '正在回复...' }
    }
  }
  for (const convId in thinkingAgents) {
    const map = thinkingAgents[convId] || {}
    if (map[agentId]) {
      const t = String(map[agentId]).trim()
      const bubble = t
        ? (t.length > 18 ? t.slice(0, 18) + '…' : t)
        : getDefaultWorkBubble(agentId, tasks)
      return { action: AGENT_ACTIONS.WORK, bubble }
    }
  }
  const myTasks = tasks.filter((t) => t.assignee === agentId)
  if (myTasks.some((t) => ['in_progress', 'doing', 'running'].includes(t.status))) {
    return { action: AGENT_ACTIONS.WORK, bubble: getDefaultWorkBubble(agentId, tasks) }
  }
  return null
}

export default function VirtualOffice({ open, onClose }) {
  const conversations = useChatStore((s) => s.conversations)
  const typingAgents = useChatStore((s) => s.typingAgents)
  const thinkingAgents = useChatStore((s) => s.thinkingAgents)
  const setActive = useChatStore((s) => s.setActiveConversation)
  const tasks = useCanvasStore((s) => s.tasks)

  const stageRef = useRef(null)
  const [stageSize, setStageSize] = useState({ w: 1200, h: 700 })

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // 监听 stage 实际尺寸（全屏后随窗口变化）
  useEffect(() => {
    if (!open) return
    const update = () => {
      const r = stageRef.current?.getBoundingClientRect()
      if (r && r.width > 0 && r.height > 0) {
        setStageSize({ w: r.width, h: r.height })
      }
    }
    const t = setTimeout(update, 0)
    let obs = null
    if (stageRef.current && typeof ResizeObserver !== 'undefined') {
      obs = new ResizeObserver(update)
      obs.observe(stageRef.current)
    }
    window.addEventListener('resize', update)
    return () => {
      clearTimeout(t)
      if (obs) obs.disconnect()
      window.removeEventListener('resize', update)
    }
  }, [open])

  const agents = useMemo(() => {
    return conversations
      .filter((c) => c.type === 'single' && c.agentId && c.agentId !== 'agent_builder')
      .map((c) => ({
        id: c.agentId,
        name: c.name,
        convId: c.id,
        avatar: c.avatar || null,
      }))
  }, [conversations])

  // 把百分比转成像素，且左上角对齐到角色中心
  const toPx = (pct) => ({
    x: Math.round(pct.x * stageSize.w - SLOT_W / 2),
    y: Math.round(pct.y * stageSize.h - SLOT_H / 2),
  })

  const layout = useMemo(() => {
    try {
      const working = []
      const resting = []

      for (const agent of agents) {
        if (!agent || !agent.id) continue
        const state = determineAgentAction(agent.id, typingAgents, thinkingAgents, tasks)
        if (state) working.push({ ...agent, ...state })
        else resting.push(agent)
      }

      const placedWorking = (() => {
        const N = working.length
        if (N === 0) return []
        if (N <= WORKSTATION_PCT.length) {
          return working.map((a, i) => ({
            ...a,
            slot: toPx(WORKSTATION_PCT[i]),
            slotType: 'desk',
          }))
        }
        // 超员压缩：均匀分布在工作区横向
        const startX = WORKSTATION_PCT[0].x
        const endX = WORKSTATION_PCT[WORKSTATION_PCT.length - 1].x
        const step = (endX - startX) / (N - 1)
        return working.map((a, i) => ({
          ...a,
          slot: toPx({ x: startX + i * step, y: WORKSTATION_PCT[0].y }),
          slotType: 'desk',
        }))
      })()

      const placedResting = (() => {
        const slotCount = {}
        return resting.map((a) => {
          const preferred = hashStringToInt(String(a.id || '')) % REST_SLOTS_PCT.length
          let bestIdx = preferred
          for (let probe = 0; probe < REST_SLOTS_PCT.length; probe++) {
            const i = (preferred + probe) % REST_SLOTS_PCT.length
            if (!slotCount[i]) { bestIdx = i; break }
            if ((slotCount[i] || 0) < (slotCount[bestIdx] || 0)) bestIdx = i
          }
          const stack = slotCount[bestIdx] || 0
          slotCount[bestIdx] = stack + 1
          const pct = REST_SLOTS_PCT[bestIdx]
          const px = toPx(pct)
          return {
            ...a,
            slot: { x: px.x + stack * 26, y: px.y - stack * 14 },
            slotType: pct.type,
            slotLabel: pct.label,
            action: REST_ACTIONS_BY_TYPE[pct.type] || AGENT_ACTIONS.IDLE,
            bubble: null,
          }
        })
      })()

      return { working: placedWorking, resting: placedResting }
    } catch (err) {
      console.error('[VirtualOffice] layout 计算失败：', err)
      return { working: [], resting: [] }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents, typingAgents, thinkingAgents, tasks, stageSize])

  const handleAgentClick = (agent) => {
    if (agent.convId) {
      setActive(agent.convId)
      onClose && onClose()
    }
  }

  if (!open) return null

  const workingCount = layout.working.length
  const restingCount = layout.resting.length

  return (
    <div className="virtual-office-overlay vo-fullscreen" onClick={onClose}>
      <div className="virtual-office-panel" onClick={(e) => e.stopPropagation()}>
        <div className="vo-header">
          <span className="vo-title">🏢 AgentHub 工作室</span>
          <span className="vo-stats">
            在岗 <b>{workingCount}</b> · 休息 <b>{restingCount}</b>
          </span>
          <button className="vo-close" onClick={onClose} title="关闭 (Esc)">×</button>
        </div>

        <div ref={stageRef} className="vo-stage">
          {/* 区域底色 */}
          <div className="vo-floor vo-floor-work" />
          <div className="vo-floor vo-floor-rest" />
          <div className="vo-divider" />

          {/* 区域标签 */}
          <span className="vo-zone-label vo-zone-label-work">工位区 · WORK</span>
          <span className="vo-zone-label vo-zone-label-rest">休息区 · CHILL</span>

          {/* 工位桌（5 个） */}
          {WORKSTATION_PCT.map((pct, i) => {
            const px = toPx(pct)
            return (
              <div
                key={`desk-${i}`}
                className="vo-desk"
                style={{ left: px.x - 6, top: px.y + SLOT_H - 8 }}
              />
            )
          })}

          {/* 装饰家具 */}
          {FURNITURE_PCT.map((f, i) => (
            <div
              key={`fur-${i}`}
              className={`vo-furniture ${f.cls || ''}`}
              style={{
                left: Math.round(f.x * stageSize.w - f.size / 2),
                top: Math.round(f.y * stageSize.h - f.size / 2),
                fontSize: f.size,
                width: f.size,
                height: f.size,
              }}
            >
              {f.emoji}
            </div>
          ))}

          {/* 休息位标签（沙发/咖啡/健身/散步） */}
          {REST_SLOTS_PCT.map((s, i) => {
            const px = toPx(s)
            return (
              <div
                key={`rest-${i}`}
                className={`vo-rest-anchor vo-rest-${s.type}`}
                style={{ left: px.x + SLOT_W / 2 - 16, top: px.y + SLOT_H - 4 }}
              >
                {s.label}
              </div>
            )
          })}

          {/* 工作中的 agent */}
          {layout.working.map((agent) => (
            <OfficeSlot
              key={agent.id}
              position={agent.slot}
              width={SLOT_W}
              height={SLOT_H}
              slotType="desk"
              zIndex={3}
            >
              <AgentCharacter
                agentId={agent.id}
                agentName={agent.name}
                avatar={agent.avatar || '🤖'}
                position={{ x: 0, y: 0 }}
                action={agent.action}
                bubble={agent.bubble}
                scale={0.8}
                onClick={() => handleAgentClick(agent)}
              />
            </OfficeSlot>
          ))}

          {/* 休息中的 agent */}
          {layout.resting.map((agent) => (
            <OfficeSlot
              key={agent.id}
              position={agent.slot}
              width={SLOT_W}
              height={SLOT_H}
              slotType={agent.slotType}
              zIndex={3}
            >
              <AgentCharacter
                agentId={agent.id}
                agentName={agent.name}
                avatar={agent.avatar || '🤖'}
                position={{ x: 0, y: 0 }}
                action={agent.action}
                scale={0.7}
                onClick={() => handleAgentClick(agent)}
              />
            </OfficeSlot>
          ))}
        </div>

        <div className="vo-footer">
          <span className="vo-hint">💡 单击员工 → 跳转到对应对话窗口 · 按 Esc 关闭</span>
        </div>
      </div>
    </div>
  )
}
