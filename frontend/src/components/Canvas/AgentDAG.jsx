import React, { useState, useRef, useEffect } from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { useChatStore } from '../../stores/chatStore'
import { wsClient } from '../../utils/websocket'

const AGENT_META = {
  user: {
    title: '项目主管',
    desc: '系统发起人与产品负责人，下发核心开发目标，并对最终成果进行交付验收。',
    templates: ['发布全新需求目标', '催促各 Agent 加快进度', '验收当前已完成的代码'],
  },
  agent_pm: {
    title: 'PM (项目经理)',
    desc: '拆解项目阶段任务，生成详细的开发规范与任务分配看板，主导进度控制。',
    templates: [
      '重新分析当前需求并整理任务看板',
      '拆解新的功能模块开发子任务',
      '协调当前团队的开发优先级',
    ],
  },
  agent_designer: {
    title: 'UI/UX 设计顾问',
    desc: '规划现代、高品质的界面原型设计，定制页面排版、毛玻璃卡片与主题配色。',
    templates: [
      '设计高颜值的深色毛玻璃主题风格',
      '提供主导航栏的响应式布局建议',
      '为核心组件设计流畅的悬浮微动效',
    ],
  },
  agent_frontend: {
    title: '前端工程师',
    desc: '负责开发高保真的 React 前端交互组件，编写优美的全局 CSS 响应式样式。',
    templates: [
      '将背景改为深蓝毛玻璃质感，添加浮动网格',
      '在首页卡片上添加酷炫的悬浮发光边框',
      '把页面布局调整为多栏响应式网格',
    ],
  },
  agent_backend: {
    title: '后端工程师',
    desc: '开发 FastAPI 服务端路由，编写数据模型持久化逻辑与本地大模型的高速通信。',
    templates: [
      '编写新的数据存储与 CRUD 查询 API',
      '集成并发限频与详细接口调用日志',
      '配置 Ollama 本地模型的高速通信缓存',
    ],
  },
  agent_tester: {
    title: 'QA 测试工程师',
    desc: '生成全面的单元测试用例，查找代码健壮性与安全边界隐患，定位运行 Bug。',
    templates: [
      '为所有 HTTP API 路由注入单元测试',
      '模拟异常边界值并校验 API 的错误处理',
      '审查前端控制台日志与 DOM 渲染健康度',
    ],
  },
  agent_devops: {
    title: 'DevOps 运维工程师',
    desc: '编写 Dockerfiles / Docker Compose 环境配置，保证高可用打包、代理及发布。',
    templates: [
      '生成优化后的多阶段 Docker 镜像配置',
      '配置 Nginx 反向代理与 SSL 缓存首部',
      '检查容器内各项系统服务的心跳健康度',
    ],
  },
}

export default function AgentDAG() {
  const nodes = useCanvasStore((s) => s.dagNodes)
  const edges = useCanvasStore((s) => s.dagEdges)
  const updateNodePosition = useCanvasStore((s) => s.updateNodePosition)
  
  const activeConversationId = useChatStore((s) => s.activeConversationId)
  const addMessage = useChatStore((s) => s.addMessage)
  
  const containerRef = useRef(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [customCommand, setCustomCommand] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  
  // Dragging metadata
  const dragRef = useRef({
    nodeId: null,
    startX: 0,
    startY: 0,
    mouseStartX: 0,
    mouseStartY: 0,
    hasMoved: false
  })

  const getNodePos = (id) => nodes.find((n) => n.id === id)

  // Mouse handlers for dragging
  const handleMouseDown = (e, node) => {
    if (e.button !== 0) return // Left-click only
    e.preventDefault()
    
    dragRef.current = {
      nodeId: node.id,
      startX: node.x,
      startY: node.y,
      mouseStartX: e.clientX,
      mouseStartY: e.clientY,
      hasMoved: false
    }
    
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  const handleMouseMove = (e) => {
    const drag = dragRef.current
    if (!drag.nodeId) return
    
    const dx = e.clientX - drag.mouseStartX
    const dy = e.clientY - drag.mouseStartY
    
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) {
      drag.hasMoved = true
    }
    
    let newX = drag.startX + dx
    let newY = drag.startY + dy
    
    // Clamp to canvas container boundaries
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect()
      const maxX = rect.width - 80
      const maxY = rect.height - 80
      newX = Math.max(0, Math.min(newX, maxX))
      newY = Math.max(0, Math.min(newY, maxY))
    }
    
    updateNodePosition(drag.nodeId, newX, newY)
  }

  const handleMouseUp = (e) => {
    const drag = dragRef.current
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
    
    if (drag.nodeId) {
      if (!drag.hasMoved) {
        // Clean click! Toggle selected state and reset textbox
        const clickedNode = nodes.find(n => n.id === drag.nodeId)
        setSelectedNode((prev) => (prev?.id === drag.nodeId ? null : clickedNode))
        setCustomCommand('')
      }
      drag.nodeId = null
    }
  }

  // Clean listeners on unmount
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [])

  // Send interactive instruction
  const handleTriggerAgent = async () => {
    if (!selectedNode || !activeConversationId) return
    setIsSubmitting(true)

    const commandText = customCommand.trim()
    const taskTitle = commandText || '协同运行本工作段'
    const fullMessageText = `[手动指派 ${selectedNode.label}] ${taskTitle}`

    try {
      // 1. Add local chat bubbles reactively
      addMessage(activeConversationId, {
        sender: 'user',
        content: { text: fullMessageText },
        streaming: false,
      })

      // 2. Dispatch WebSocket command to targeted agent
      wsClient.send({
        type: 'message',
        conversation_id: activeConversationId,
        sender: 'user',
        content: { 
          text: taskTitle, 
          target_agent: selectedNode.id 
        },
      })

      setCustomCommand('')
      setSelectedNode(null) // auto-dismiss popover
    } catch (err) {
      console.error('[DAG Canvas] Trigger agent error:', err)
    } finally {
      setIsSubmitting(false)
    }
  }

  const selectedMeta = selectedNode ? AGENT_META[selectedNode.id] : null

  return (
    <div className="dag-container" ref={containerRef}>
      {/* SVG Connectors with animated flows */}
      <svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0, zIndex: 1 }}>
        {edges.map((edge, i) => {
          const from = getNodePos(edge.from)
          const to = getNodePos(edge.to)
          if (!from || !to) return null

          // Determine edge status based on source/dest nodes
          let edgeClass = 'dag-flow-edge'
          if (from.status === 'working' || to.status === 'working') {
            edgeClass += ' working'
          } else if (from.status === 'done' && to.status === 'done') {
            edgeClass += ' done'
          }

          return (
            <line
              key={i}
              className={edgeClass}
              x1={from.x + 40}
              y1={from.y + 40}
              x2={to.x + 40}
              y2={to.y + 40}
            />
          )
        })}
      </svg>

      {/* Nodes Map */}
      {nodes.map((node) => {
        const isSelected = selectedNode?.id === node.id
        const dragActive = dragRef.current.nodeId === node.id
        
        let nodeClass = `dag-node ${node.status}`
        if (isSelected) nodeClass += ' selected'
        if (dragActive) nodeClass += ' dragging'

        return (
          <div
            key={node.id}
            className={nodeClass}
            style={{ left: node.x, top: node.y }}
            onMouseDown={(e) => handleMouseDown(e, node)}
          >
            <div className="node-icon">{node.icon}</div>
            <div className="node-label">{node.label}</div>
          </div>
        )
      })}

      {/* Stunning Glassmorphic Details Popover Drawer */}
      {selectedNode && selectedMeta && (
        <div className="dag-detail-card">
          <div className="dag-detail-header">
            <div className="dag-detail-avatar-title">
              <div className="dag-detail-avatar">{selectedNode.icon}</div>
              <div className="dag-detail-title-wrapper">
                <div className="dag-detail-name">{selectedMeta.title}</div>
                <div className={`dag-detail-badge ${selectedNode.status}`}>
                  {selectedNode.status === 'working' ? '⚙️ 运行中' : selectedNode.status === 'done' ? '✅ 就绪' : '💤 空闲'}
                </div>
              </div>
            </div>
            <button className="dag-detail-close" onClick={() => setSelectedNode(null)}>
              ✕
            </button>
          </div>

          <div className="dag-detail-body">
            <div className="dag-detail-desc">{selectedMeta.desc}</div>

            <div className="dag-detail-section-title">任务快捷模板</div>
            <div className="dag-detail-templates">
              {selectedMeta.templates.map((tpl, idx) => (
                <button
                  key={idx}
                  className="dag-detail-template-btn"
                  onClick={() => setCustomCommand(tpl)}
                >
                  💡 {tpl}
                </button>
              ))}
            </div>

            <div className="dag-detail-section-title">下发任务指令</div>
            <textarea
              className="dag-detail-input"
              placeholder="请输入指派该 Agent 执行的具体子任务..."
              value={customCommand}
              onChange={(e) => setCustomCommand(e.target.value)}
            />

            <button
              className="dag-detail-action-btn"
              disabled={isSubmitting || selectedNode.status === 'working'}
              onClick={handleTriggerAgent}
            >
              {selectedNode.status === 'working' ? '🔄 Agent 运行中...' : '⚡ 指派该 Agent 运行'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
