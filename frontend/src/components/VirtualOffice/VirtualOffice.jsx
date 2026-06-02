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

// agent 站在椅子位置（桌子下方），看起来像"坐在椅子上"
const WORKSTATION_PCT = [
  { x: 0.16, y: 0.52 },
  { x: 0.32, y: 0.52 },
  { x: 0.48, y: 0.52 },
  { x: 0.64, y: 0.52 },
  { x: 0.80, y: 0.52 },
]

const REST_SLOTS_PCT = [
  { x: 0.13, y: 0.80, type: 'sofa' },
  { x: 0.22, y: 0.80, type: 'sofa' },
  { x: 0.48, y: 0.82, type: 'coffee' },
  { x: 0.66, y: 0.86, type: 'walk' },
  { x: 0.84, y: 0.84, type: 'gym' },
]

const REST_ACTIONS_BY_TYPE = {
  sofa: AGENT_ACTIONS.SLEEP,
  coffee: AGENT_ACTIONS.COFFEE,
  gym: AGENT_ACTIONS.GYM,
  walk: AGENT_ACTIONS.WALK,
}

// 自由活动节奏：每个 agent 在一个活动停留 8-22 秒后换位置
const FREE_MOVE_CHECK_INTERVAL = 4000  // 每 4 秒检查一次
const ACTIVITY_MIN_MS = 8000
const ACTIVITY_MAX_MS = 22000

function pickRandomRestSlot(currentIdx) {
  // 7 成随机选不同的，3 成保持
  if (Math.random() < 0.3) return currentIdx
  let next = Math.floor(Math.random() * REST_SLOTS_PCT.length)
  if (next === currentIdx) {
    next = (next + 1 + Math.floor(Math.random() * (REST_SLOTS_PCT.length - 1))) % REST_SLOTS_PCT.length
  }
  return next
}

const FURNITURE_LIST = [
  // 上墙：窗 / 白板 / 挂画 + 顶部吊灯
  { type: 'Window', x: 0.10, y: 0.08, w: 180, h: 130 },
  { type: 'Whiteboard', x: 0.50, y: 0.08, w: 160, h: 110 },
  { type: 'WallArt', x: 0.88, y: 0.06, w: 90, h: 70 },
  { type: 'PendantLamp', x: 0.30, y: 0.16, w: 60, h: 100 },
  { type: 'PendantLamp', x: 0.50, y: 0.16, w: 60, h: 100 },
  { type: 'PendantLamp', x: 0.70, y: 0.16, w: 60, h: 100 },

  // 工位区两侧盆栽
  { type: 'Plant', x: 0.03, y: 0.40, w: 70, h: 110 },
  { type: 'Plant', x: 0.97, y: 0.40, w: 70, h: 110 },

  // 工位（5 张工作站：桌+椅+显示器一体）
  { type: 'Desk', x: 0.16, y: 0.42, w: 180, h: 200 },
  { type: 'Desk', x: 0.32, y: 0.42, w: 180, h: 200 },
  { type: 'Desk', x: 0.48, y: 0.42, w: 180, h: 200 },
  { type: 'Desk', x: 0.64, y: 0.42, w: 180, h: 200 },
  { type: 'Desk', x: 0.80, y: 0.42, w: 180, h: 200 },

  // 休息区：电视 + 沙发 + 茶几（左下）
  { type: 'TV', x: 0.16, y: 0.68, w: 220, h: 170 },
  { type: 'Sofa', x: 0.18, y: 0.86, w: 240, h: 110 },
  { type: 'CoffeeTable', x: 0.05, y: 0.90, w: 120, h: 70 },

  // 茶水间：咖啡机 + 盆栽
  { type: 'CoffeeMachine', x: 0.42, y: 0.82, w: 90, h: 140 },
  { type: 'Plant', x: 0.36, y: 0.96, w: 70, h: 100 },

  // 散步 / 禅意区
  { type: 'ZenSpot', x: 0.65, y: 0.92, w: 150, h: 110 },
  { type: 'Plant', x: 0.58, y: 0.70, w: 70, h: 110 },

  // 健身区：跑步机 + 盆栽
  { type: 'Treadmill', x: 0.85, y: 0.78, w: 180, h: 150 },
  { type: 'Plant', x: 0.95, y: 0.95, w: 70, h: 100 },
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

  // 自由活动状态：{ agentId: { slotIdx, nextChangeAt, walking } }
  const [freeMove, setFreeMove] = useState({})
  const freeMoveRef = useRef(freeMove)
  freeMoveRef.current = freeMove

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // 自由活动定时器：每 4 秒检查一次，到时间的 agent 换位
  useEffect(() => {
    if (!open) return
    const tick = () => {
      const now = Date.now()
      setFreeMove((prev) => {
        const next = { ...prev }
        let changed = false
        for (const agentId in next) {
          const entry = next[agentId]
          if (entry.walking) continue
          if (now >= entry.nextChangeAt) {
            const newIdx = pickRandomRestSlot(entry.slotIdx)
            if (newIdx !== entry.slotIdx) {
              next[agentId] = {
                slotIdx: newIdx,
                nextChangeAt: now + ACTIVITY_MIN_MS + Math.random() * (ACTIVITY_MAX_MS - ACTIVITY_MIN_MS),
                walking: true,
                walkEndsAt: now + 1200,
              }
              changed = true
            } else {
              // 留在原地，重置计时
              next[agentId] = {
                ...entry,
                nextChangeAt: now + ACTIVITY_MIN_MS + Math.random() * (ACTIVITY_MAX_MS - ACTIVITY_MIN_MS),
              }
              changed = true
            }
          } else if (entry.walking && now >= entry.walkEndsAt) {
            next[agentId] = { ...entry, walking: false }
            changed = true
          }
        }
        return changed ? next : prev
      })
    }
    const id = setInterval(tick, FREE_MOVE_CHECK_INTERVAL / 2)
    return () => clearInterval(id)
  }, [open])

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

  const toPx = (pct) => {
    const x = Math.round(pct.x * stageSize.w - SLOT_W / 2)
    const y = Math.round(pct.y * stageSize.h - SLOT_H / 2)
    // 边界检查：确保不超出 stage
    return {
      x: Math.max(0, Math.min(x, stageSize.w - SLOT_W)),
      y: Math.max(0, Math.min(y, stageSize.h - SLOT_H)),
    }
  }

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
        const now = Date.now()
        return resting.map((a) => {
          const fm = freeMove[a.id]
          let bestIdx
          if (fm && typeof fm.slotIdx === 'number') {
            bestIdx = fm.slotIdx
            slotCount[bestIdx] = (slotCount[bestIdx] || 0) + 1
          } else {
            // 第一次进入：hash 选起始位
            const preferred = hashStringToInt(String(a.id || '')) % REST_SLOTS_PCT.length
            bestIdx = preferred
            for (let probe = 0; probe < REST_SLOTS_PCT.length; probe++) {
              const i = (preferred + probe) % REST_SLOTS_PCT.length
              if (!slotCount[i]) { bestIdx = i; break }
              if ((slotCount[i] || 0) < (slotCount[bestIdx] || 0)) bestIdx = i
            }
            slotCount[bestIdx] = (slotCount[bestIdx] || 0) + 1
            // 同时初始化它的 freeMove，下一帧定时器会用到
            if (!freeMoveRef.current[a.id]) {
              setTimeout(() => {
                setFreeMove((prev) => prev[a.id] ? prev : ({
                  ...prev,
                  [a.id]: {
                    slotIdx: bestIdx,
                    nextChangeAt: now + ACTIVITY_MIN_MS + Math.random() * (ACTIVITY_MAX_MS - ACTIVITY_MIN_MS),
                    walking: false,
                  }
                }))
              }, 0)
            }
          }
          const stack = (slotCount[bestIdx] || 1) - 1
          const pct = REST_SLOTS_PCT[bestIdx]
          const px = toPx(pct)
          const isWalking = fm && fm.walking
          return {
            ...a,
            slot: { x: px.x + stack * 28, y: px.y - stack * 16 },
            slotType: pct.type,
            action: isWalking ? AGENT_ACTIONS.WALK : (REST_ACTIONS_BY_TYPE[pct.type] || AGENT_ACTIONS.IDLE),
            bubble: isWalking ? '溜达去...' : null,
          }
        })
      })()

      return { working: placedWorking, resting: placedResting }
    } catch (err) {
      console.error('[VirtualOffice] layout 计算失败：', err)
      return { working: [], resting: [] }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agents, typingAgents, thinkingAgents, tasks, stageSize, freeMove])

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
