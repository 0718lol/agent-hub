import React, { useState, useEffect, useMemo, useRef } from 'react'
import AgentCharacter from '../AgentCharacter/AgentCharacter'
import OfficeSlot from '../AgentCharacter/OfficeSlot'
import { AGENT_ACTIONS } from '../AgentCharacter/agentAction.types'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import {
  Desk, Sofa, TV, CoffeeTable, CoffeeMachine, Treadmill,
  Plant, Window, Whiteboard, WallArt, PendantLamp, ZenSpot,
} from './OfficeFurniture'
import './VirtualOffice.css'

const SLOT_W = 96
const SLOT_H = 130

const WORKSTATION_PCT = [
  { x: 0.10, y: 0.30 },
  { x: 0.26, y: 0.30 },
  { x: 0.42, y: 0.30 },
  { x: 0.58, y: 0.30 },
  { x: 0.74, y: 0.30 },
]

const REST_SLOTS_PCT = [
  { x: 0.10, y: 0.74, type: 'sofa' },
  { x: 0.20, y: 0.74, type: 'sofa' },
  { x: 0.50, y: 0.78, type: 'coffee' },
  { x: 0.66, y: 0.82, type: 'walk' },
  { x: 0.86, y: 0.78, type: 'gym' },
]

const REST_ACTIONS_BY_TYPE = {
  sofa: AGENT_ACTIONS.SLEEP,
  coffee: AGENT_ACTIONS.COFFEE,
  gym: AGENT_ACTIONS.GYM,
  walk: AGENT_ACTIONS.WALK,
}

const FURNITURE_LIST = [
  { type: 'Window', x: 0.10, y: 0.10, w: 200, h: 140 },
  { type: 'Whiteboard', x: 0.50, y: 0.10, w: 200, h: 130 },
  { type: 'WallArt', x: 0.86, y: 0.08, w: 100, h: 80 },
  { type: 'PendantLamp', x: 0.34, y: 0.04, w: 50, h: 80 },
  { type: 'PendantLamp', x: 0.66, y: 0.04, w: 50, h: 80 },
  { type: 'Plant', x: 0.04, y: 0.34, w: 70, h: 110 },
  { type: 'Plant', x: 0.94, y: 0.34, w: 70, h: 110 },
  { type: 'Desk', x: 0.10, y: 0.36, w: 160, h: 110 },
  { type: 'Desk', x: 0.26, y: 0.36, w: 160, h: 110 },
  { type: 'Desk', x: 0.42, y: 0.36, w: 160, h: 110 },
  { type: 'Desk', x: 0.58, y: 0.36, w: 160, h: 110 },
  { type: 'Desk', x: 0.74, y: 0.36, w: 160, h: 110 },
  { type: 'TV', x: 0.16, y: 0.62, w: 220, h: 150 },
  { type: 'Sofa', x: 0.16, y: 0.78, w: 240, h: 100 },
  { type: 'CoffeeTable', x: 0.16, y: 0.92, w: 110, h: 50 },
  { type: 'CoffeeMachine', x: 0.42, y: 0.74, w: 80, h: 130 },
  { type: 'Plant', x: 0.34, y: 0.92, w: 60, h: 95 },
  { type: 'ZenSpot', x: 0.66, y: 0.92, w: 160, h: 110 },
  { type: 'Plant', x: 0.58, y: 0.62, w: 70, h: 110 },
  { type: 'Treadmill', x: 0.86, y: 0.72, w: 160, h: 150 },
  { type: 'Plant', x: 0.94, y: 0.92, w: 60, h: 95 },
]

const FURNITURE_COMPONENT_MAP = {
  Desk, Sofa, TV, CoffeeTable, CoffeeMachine, Treadmill,
  Plant, Window, Whiteboard, WallArt, PendantLamp, ZenSpot,
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
  const [stageSize, setStageSize] = useState({ w: 1400, h: 800 })

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

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
            slot: { x: px.x + stack * 28, y: px.y - stack * 16 },
            slotType: pct.type,
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
          <div className="vo-wall" />
          <div className="vo-floor" />
          <div className="vo-floor-shadow" />

          {FURNITURE_LIST.map((f, i) => {
            const Comp = FURNITURE_COMPONENT_MAP[f.type]
            if (!Comp) return null
            const left = Math.round(f.x * stageSize.w - f.w / 2)
            const top = Math.round(f.y * stageSize.h - f.h / 2)
            return (
              <div
                key={`fur-${i}`}
                className="vo-furniture-piece"
                style={{ left, top }}
              >
                <Comp width={f.w} height={f.h} />
              </div>
            )
          })}

          {layout.working.map((agent) => (
            <OfficeSlot
              key={agent.id}
              position={agent.slot}
              width={SLOT_W}
              height={SLOT_H}
              slotType="desk"
              zIndex={5}
            >
              <AgentCharacter
                agentId={agent.id}
                agentName={agent.name}
                avatar={agent.avatar || '🤖'}
                position={{ x: 0, y: 0 }}
                action={agent.action}
                bubble={agent.bubble}
                scale={0.85}
                onClick={() => handleAgentClick(agent)}
              />
            </OfficeSlot>
          ))}

          {layout.resting.map((agent) => (
            <OfficeSlot
              key={agent.id}
              position={agent.slot}
              width={SLOT_W}
              height={SLOT_H}
              slotType={agent.slotType}
              zIndex={5}
            >
              <AgentCharacter
                agentId={agent.id}
                agentName={agent.name}
                avatar={agent.avatar || '🤖'}
                position={{ x: 0, y: 0 }}
                action={agent.action}
                scale={0.75}
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
