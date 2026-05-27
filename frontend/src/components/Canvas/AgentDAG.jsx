import React from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import IconAvatar from '../IconAvatar'

export default function AgentDAG({ compact = false }) {
  const nodes = useCanvasStore((s) => s.dagNodes)
  const edges = useCanvasStore((s) => s.dagEdges)

  const getNodePos = (id) => nodes.find((n) => n.id === id)

  const r = compact ? 25 : 40  // 节点半宽
  const iconSize = compact ? 12 : 16
  const fontSize = compact ? 10 : 12

  return (
    <div className="dag-container" style={{ height: compact ? 240 : 400 }}>
      <svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0, zIndex: 1 }}>
        {edges.map((edge, i) => {
          const from = getNodePos(edge.from)
          const to = getNodePos(edge.to)
          if (!from || !to) return null
          return (
            <line
              key={i}
              x1={from.x + r}
              y1={from.y + r}
              x2={to.x + r}
              y2={to.y + r}
              stroke="rgba(99, 102, 241, 0.3)"
              strokeWidth="2"
              strokeDasharray="6,4"
            />
          )
        })}
      </svg>

      {nodes.map((node) => (
        <div
          key={node.id}
          className={`dag-node ${node.status}`}
          style={{
            left: node.x,
            top: node.y,
            width: compact ? 50 : 80,
            height: compact ? 50 : 80,
          }}
        >
          <div className="node-icon"><IconAvatar iconKey={node.iconKey} size={iconSize} /></div>
          {!compact && <div className="node-label" style={{ fontSize }}>{node.label}</div>}
        </div>
      ))}
    </div>
  )
}
