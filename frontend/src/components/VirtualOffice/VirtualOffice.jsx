import React, { useState, useEffect, useMemo } from 'react'
import AgentCharacter from '../AgentCharacter/AgentCharacter'
import OfficeSlot from '../AgentCharacter/OfficeSlot'
import { AGENT_ACTIONS } from '../AgentCharacter/agentAction.types'
import { useChatStore } from '../../stores/chatStore'
import { useCanvasStore } from '../../stores/canvasStore'
import './VirtualOffice.css'

const OFFICE_WIDTH = 720
const OFFICE_HEIGHT = 460
const SLOT_W = 80
const SLOT_H = 110

const WORKSTATIONS = [
  { x: 60, y: 90 },
  { x: 180, y: 90 },
  { x: 300, y: 90 },
  { x: 420, y: 90 },
  { x: 540, y: 90 },
]
const REST_SLOTS = [
  { x: 60, y: 290, type: 'sofa', label: '🛋️' },
  { x: 180, y: 290, type: 'coffee', label: '☕' },
  { x: 300, y: 290, type: 'gym', label: '🏋️' },
  { x: 420, y: 290, type: 'sofa', label: '🛋️' },
  { x: 540, y: 290, type: 'walk', label: '🌿' },
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

function determineAgentAction(agentId, typingAgents, thinkingAgents, tasks) {
  for (const convId in typingAgents) {
    const set = typingAgents[convId]
    if (set && set.has && set.has(agentId)) return { action: AGENT_ACTIONS.TALK, bubble: null }
  }
  for (const convId in thinkingAgents) {
    const map = thinkingAgents[convId] || {}
    if (map[agentId]) {
      const t = String(map[agentId]).trim()
      const bubble = t ? (t.length > 20 ? t.slice(0, 20) + '…' : t) : null
      return { action: AGENT_ACTIONS.WORK, bubble }
    }
  }
  const myTasks = tasks.filter((t) => t.assignee === agentId)
  if (myTasks.some((t) => ['in_progress', 'doing', 'running'].includes(t.status))) {
    return { action: AGENT_ACTIONS.WORK, bubble: null }
  }
  return null
}

export default function VirtualOffice({ open, onClose }) {
  const conversations = useChatStore((s) => s.conversations)
  const typingAgents = useChatStore((s) => s.typingAgents)
  const thinkingAgents = useChatStore((s) => s.thinkingAgents)
  const setActive = useChatStore((s) => s.setActiveConversation)
  const tasks = useCanvasStore((s) => s.tasks)

  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

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

  const layout = useMemo(() => {
    const working = []
    const resting = []

    for (const agent of agents) {
      const state = determineAgentAction(agent.id, typingAgents, thinkingAgents, tasks)
      if (state) working.push({ ...agent, ...state })
      else resting.push(agent)
    }

    const placedWorking = working.slice(0, WORKSTATIONS.length).map((a, i) => ({
      ...a,
      slot: WORKSTATIONS[i],
      slotType: 'desk',
    }))

    const placedResting = resting.map((a) => {
      const idx = hashStringToInt(a.id) % REST_SLOTS.length
      return {
        ...a,
        slot: REST_SLOTS[idx],
        slotType: REST_SLOTS[idx].type,
        slotLabel: REST_SLOTS[idx].label,
        action: REST_ACTIONS_BY_TYPE[REST_SLOTS[idx].type] || AGENT_ACTIONS.IDLE,
        bubble: null,
      }
    })

    return { working: placedWorking, resting: placedResting }
  }, [agents, typingAgents, thinkingAgents, tasks])

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
    <div className="virtual-office-overlay" onClick={onClose}>
      <div className="virtual-office-panel" onClick={(e) => e.stopPropagation()}>
        <div className="vo-header">
          <span className="vo-title">🏢 AgentHub 工作室</span>
          <span className="vo-stats">
            在岗 <b>{workingCount}</b> · 休息 <b>{restingCount}</b>
          </span>
          <button className="vo-close" onClick={onClose}>×</button>
        </div>

        <div
          className="vo-stage"
          style={{ width: OFFICE_WIDTH, height: OFFICE_HEIGHT }}
        >
          <div className="vo-zone vo-zone-work">
            <span className="vo-zone-label">工位区</span>
            {WORKSTATIONS.map((pos, i) => (
              <div key={i} className="vo-desk" style={{ left: pos.x - 6, top: pos.y + SLOT_H - 8 }} />
            ))}
          </div>

          <div className="vo-zone vo-zone-rest">
            <span className="vo-zone-label">休息区</span>
            {REST_SLOTS.map((s, i) => (
              <div key={i} className={`vo-furniture vo-furniture-${s.type}`} style={{ left: s.x, top: s.y + SLOT_H - 4 }}>
                {s.label}
              </div>
            ))}
          </div>

          {layout.working.map((agent) => (
            <OfficeSlot
              key={agent.id}
              position={agent.slot}
              width={SLOT_W}
              height={SLOT_H}
              slotType="desk"
              zIndex={2}
            >
              <AgentCharacter
                agentId={agent.id}
                agentName={agent.name}
                avatar={agent.avatar || '🤖'}
                position={{ x: 0, y: 0 }}
                action={agent.action}
                bubble={agent.bubble}
                scale={0.7}
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
              zIndex={2}
            >
              <AgentCharacter
                agentId={agent.id}
                agentName={agent.name}
                avatar={agent.avatar || '🤖'}
                position={{ x: 0, y: 0 }}
                action={agent.action}
                scale={0.65}
                onClick={() => handleAgentClick(agent)}
              />
            </OfficeSlot>
          ))}
        </div>

        <div className="vo-footer">
          <span className="vo-hint">💡 点击任意员工 → 跳转到对应对话窗口</span>
        </div>
      </div>
    </div>
  )
}
