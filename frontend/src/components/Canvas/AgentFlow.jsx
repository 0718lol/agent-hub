import React, { useState, useCallback, useMemo, useEffect } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useCanvasStore } from '../../stores/canvasStore'
import { useAgentStore } from '../../stores/agentStore'
import IconAvatar from '../IconAvatar'

// ---- 自定义节点：用 position: relative 定位 Handle ----
function AgentNode({ data }) {
  const { label, iconKey, status, agentId } = data
  const statusColors = {
    idle: 'var(--text-muted)',
    working: 'var(--accent)',
    done: 'var(--green)',
    error: 'var(--red)',
  }
  const borderColor = statusColors[status] || 'var(--border)'

  return (
    <div style={{ position: 'relative' }}>
      <Handle
        type="target"
        position={Position.Left}
        style={{
          width: 14, height: 14,
          background: 'var(--accent)',
          border: '3px solid var(--bg-primary)',
          borderRadius: '50%',
          cursor: 'crosshair',
        }}
      />
      <div style={{
        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4,
        padding: '10px 14px', borderRadius: 10,
        background: 'var(--bg-secondary)',
        border: `2px solid ${borderColor}`,
        minWidth: 72,
        transition: 'border-color 0.2s',
        cursor: 'default',
      }}>
        <IconAvatar agentId={agentId} iconKey={iconKey} size={20} />
        <span style={{ fontSize: 11, color: 'var(--text-primary)', fontWeight: 500 }}>{label}</span>
        {status === 'working' && (
          <span style={{ fontSize: 9, color: 'var(--accent)', marginTop: 1 }}>● 执行中</span>
        )}
        {status === 'done' && (
          <span style={{ fontSize: 9, color: 'var(--green)', marginTop: 1 }}>✓ 完成</span>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        style={{
          width: 14, height: 14,
          background: 'var(--accent)',
          border: '3px solid var(--bg-primary)',
          borderRadius: '50%',
          cursor: 'crosshair',
        }}
      />
    </div>
  )
}

const nodeTypes = { agent: AgentNode }

// ---- 默认拓扑 ----
function getDefaultNodes() {
  return [
    { id: 'user', type: 'agent', position: { x: 250, y: 0 }, data: { label: '用户', iconKey: 'user', status: 'idle' } },
    { id: 'agent_pm', type: 'agent', position: { x: 250, y: 100 }, data: { label: 'PM', iconKey: 'agent_pm', agentId: 'agent_pm', status: 'idle' } },
    { id: 'agent_designer', type: 'agent', position: { x: 50, y: 220 }, data: { label: '设计', iconKey: 'agent_designer', agentId: 'agent_designer', status: 'idle' } },
    { id: 'agent_frontend', type: 'agent', position: { x: 170, y: 220 }, data: { label: '前端', iconKey: 'agent_frontend', agentId: 'agent_frontend', status: 'idle' } },
    { id: 'agent_backend', type: 'agent', position: { x: 290, y: 220 }, data: { label: '后端', iconKey: 'agent_backend', agentId: 'agent_backend', status: 'idle' } },
    { id: 'agent_tester', type: 'agent', position: { x: 410, y: 220 }, data: { label: '测试', iconKey: 'agent_tester', agentId: 'agent_tester', status: 'idle' } },
    { id: 'agent_devops', type: 'agent', position: { x: 350, y: 100 }, data: { label: '运维', iconKey: 'agent_devops', agentId: 'agent_devops', status: 'idle' } },
  ]
}

function getDefaultEdges() {
  return [
    { id: 'e-user-pm', source: 'user', target: 'agent_pm', markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-pm-designer', source: 'agent_pm', target: 'agent_designer', markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-pm-frontend', source: 'agent_pm', target: 'agent_frontend', markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-pm-backend', source: 'agent_pm', target: 'agent_backend', markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-pm-tester', source: 'agent_pm', target: 'agent_tester', markerEnd: { type: MarkerType.ArrowClosed } },
    { id: 'e-pm-devops', source: 'agent_pm', target: 'agent_devops', markerEnd: { type: MarkerType.ArrowClosed } },
  ]
}

// ---- 组件 ----
export default function AgentFlow({ compact = false }) {
  const agents = useAgentStore((s) => s.agents)
  const dagStatus = useCanvasStore((s) => s.dagNodes)
  const [editMode, setEditMode] = useState(false)
  const [showNodeMenu, setShowNodeMenu] = useState(false)

  const savedTopology = useMemo(() => {
    try {
      const raw = localStorage.getItem('agent-hub-topology')
      if (raw) return JSON.parse(raw)
    } catch {}
    return null
  }, [])

  const [nodes, setNodes, onNodesChange] = useNodesState(savedTopology?.nodes || getDefaultNodes())
  const [edges, setEdges, onEdgesChange] = useEdgesState(savedTopology?.edges || getDefaultEdges())

  // 同步 dagNodes 状态
  useEffect(() => {
    setNodes((nds) => nds.map((n) => {
      const dagNode = dagStatus.find((d) => d.id === n.id)
      if (dagNode) {
        return { ...n, data: { ...n.data, status: dagNode.status } }
      }
      return n
    }))
  }, [dagStatus])

  // 连线
  const onConnect = useCallback((params) => {
    setEdges((eds) => addEdge({
      ...params,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: 'var(--accent)', strokeWidth: 2 },
    }, eds))
  }, [])

  // 保存
  const handleSave = useCallback(() => {
    localStorage.setItem('agent-hub-topology', JSON.stringify({ nodes, edges }))
  }, [nodes, edges])

  // 重置
  const handleReset = useCallback(() => {
    setNodes(getDefaultNodes())
    setEdges(getDefaultEdges())
    localStorage.removeItem('agent-hub-topology')
  }, [])

  // 添加节点
  const handleAddNode = useCallback((agentId) => {
    const agent = agents.find((a) => a.agent_id === agentId)
    if (!agent) return
    if (nodes.find((n) => n.id === agentId)) return
    const newNode = {
      id: agentId,
      type: 'agent',
      position: { x: 200 + Math.random() * 100, y: 150 + Math.random() * 100 },
      data: { label: agent.name, iconKey: agentId, agentId, status: 'idle' },
    }
    setNodes((nds) => [...nds, newNode])
    setShowNodeMenu(false)
  }, [nodes, agents])

  // 删除
  const onNodesDelete = useCallback((deleted) => {
    const allowed = deleted.filter((n) => n.id !== 'user' && n.id !== 'agent_pm')
    if (allowed.length < deleted.length) return
    setNodes((nds) => nds.filter((n) => !deleted.find((d) => d.id === n.id)))
    setEdges((eds) => eds.filter((e) => !deleted.find((d) => d.id === e.source || d.id === e.target)))
  }, [])

  const onEdgesDelete = useCallback((deleted) => {
    setEdges((eds) => eds.filter((e) => !deleted.find((d) => d.id === e.id)))
  }, [])

  const availableAgents = useMemo(() => {
    const nodeIds = new Set(nodes.map((n) => n.id))
    return agents.filter((a) => !nodeIds.has(a.agent_id) && a.agent_id !== 'agent_builder')
  }, [nodes, agents])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 工具栏 */}
      <div style={{
        padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8,
        borderBottom: '1px solid var(--border)', flexShrink: 0,
      }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>协作图</span>
        <div style={{ flex: 1 }} />

        <button
          onClick={() => setShowNodeMenu(!showNodeMenu)}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 11,
            background: showNodeMenu ? 'var(--accent-bg)' : 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            color: showNodeMenu ? 'var(--accent)' : 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          + 添加节点
        </button>
        <button
          onClick={handleSave}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 11,
            background: 'var(--green)', border: 'none',
            color: '#fff', cursor: 'pointer',
          }}
        >
          保存
        </button>
        <button
          onClick={handleReset}
          style={{
            padding: '4px 10px', borderRadius: 6, fontSize: 11,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            color: 'var(--text-muted)', cursor: 'pointer',
          }}
        >
          重置
        </button>
      </div>

      {/* 添加节点菜单 */}
      {showNodeMenu && (
        <div style={{
          padding: '8px 12px', display: 'flex', flexWrap: 'wrap', gap: 6,
          borderBottom: '1px solid var(--border)', background: 'var(--bg-secondary)',
        }}>
          {availableAgents.map((a) => (
            <button
              key={a.agent_id}
              onClick={() => handleAddNode(a.agent_id)}
              style={{
                padding: '4px 10px', borderRadius: 6, fontSize: 11,
                background: 'var(--bg-primary)', border: '1px solid var(--border)',
                color: 'var(--text-primary)', cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 4,
              }}
            >
              <IconAvatar agentId={a.agent_id} size={12} />
              {a.name}
            </button>
          ))}
          {availableAgents.length === 0 && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>所有 Agent 已在画布中</span>
          )}
        </div>
      )}

      {/* React Flow 画布 */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodesDelete={onNodesDelete}
          onEdgesDelete={onEdgesDelete}
          nodeTypes={nodeTypes}
          nodesDraggable={true}
          nodesConnectable={true}
          elementsSelectable={true}
          deleteKeyCode="Delete"
          connectionLineStyle={{ stroke: 'var(--accent)', strokeWidth: 2, strokeDasharray: '5,5' }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          style={{ background: 'var(--bg-primary)' }}
          defaultEdgeOptions={{
            style: { stroke: 'var(--accent)', strokeWidth: 2 },
            markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--accent)' },
          }}
        >
          <Background color="var(--border)" gap={20} size={1} />
          {!compact && <Controls style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }} />}
        </ReactFlow>
      </div>

      {/* 操作提示 */}
      {!compact && (
        <div style={{
          padding: '10px 16px', textAlign: 'center',
          fontSize: 13, fontWeight: 500, color: 'var(--accent)',
          borderTop: '1px solid var(--border)',
          background: 'var(--accent-bg)',
          letterSpacing: 0.3,
        }}>
          拖拽节点移动 · 从蓝色圆点拖出连线 · 点击连线后按 Delete 键可删除连线
        </div>
      )}
    </div>
  )
}
