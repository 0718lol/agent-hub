import { useEffect, useRef, useState } from 'react'
import { useChatStore } from '../stores/chatStore'
import { useCanvasStore } from '../stores/canvasStore'

const IDLE_TIMEOUT_MS = 30 * 1000

export function useAgentAction(agentId, options = {}) {
  const { idleTimeout = IDLE_TIMEOUT_MS } = options
  const [action, setAction] = useState('idle')
  const [bubble, setBubble] = useState(null)
  const lastActivityRef = useRef(Date.now())
  const sleepTimerRef = useRef(null)
  const bubbleTimerRef = useRef(null)

  const typingAgents = useChatStore((s) => s.typingAgents)
  const thinkingAgents = useChatStore((s) => s.thinkingAgents)
  const generatingConvs = useChatStore((s) => s.generatingConvs)
  const tasks = useCanvasStore((s) => s.tasks)

  useEffect(() => {
    let isWorking = false
    let isTalking = false
    let bubbleText = null

    if (agentId) {
      for (const convId in typingAgents) {
        const set = typingAgents[convId]
        if (set && set.has && set.has(agentId)) {
          isTalking = true
          break
        }
      }

      for (const convId in thinkingAgents) {
        const map = thinkingAgents[convId] || {}
        if (map[agentId]) {
          isWorking = true
          const t = String(map[agentId]).trim()
          if (t) bubbleText = t.length > 24 ? t.slice(0, 24) + '…' : t
          break
        }
      }

      const myTasks = tasks.filter((t) => t.assignee === agentId)
      if (myTasks.some((t) => t.status === 'in_progress' || t.status === 'doing' || t.status === 'running')) {
        isWorking = true
      }
    } else {
      const anyTyping = Object.values(typingAgents).some(
        (s) => s && s.size && s.size > 0
      )
      const anyThinking = Object.values(thinkingAgents).some(
        (m) => m && Object.keys(m).length > 0
      )
      const anyGenerating = generatingConvs && generatingConvs.size > 0
      isTalking = anyTyping
      isWorking = anyThinking || anyGenerating
    }

    let next = 'idle'
    if (isTalking) next = 'talk'
    else if (isWorking) next = 'work'

    if (next !== 'idle') {
      lastActivityRef.current = Date.now()
      if (sleepTimerRef.current) {
        clearTimeout(sleepTimerRef.current)
        sleepTimerRef.current = null
      }
      setAction(next)
      if (bubbleText) {
        setBubble(bubbleText)
        if (bubbleTimerRef.current) clearTimeout(bubbleTimerRef.current)
        bubbleTimerRef.current = setTimeout(() => setBubble(null), 4000)
      }
    } else {
      setAction('idle')
      sleepTimerRef.current = setTimeout(() => {
        const idleFor = Date.now() - lastActivityRef.current
        if (idleFor >= idleTimeout) setAction('sleep')
      }, idleTimeout)
    }

    return () => {
      if (sleepTimerRef.current) clearTimeout(sleepTimerRef.current)
    }
  }, [agentId, typingAgents, thinkingAgents, generatingConvs, tasks, idleTimeout])

  useEffect(() => {
    return () => {
      if (bubbleTimerRef.current) clearTimeout(bubbleTimerRef.current)
    }
  }, [])

  const sayBubble = (text, durationMs = 3000) => {
    setBubble(text)
    if (bubbleTimerRef.current) clearTimeout(bubbleTimerRef.current)
    bubbleTimerRef.current = setTimeout(() => setBubble(null), durationMs)
  }

  return { action, bubble, setBubble: sayBubble, setAction }
}
