import React from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import IconAvatar from '../IconAvatar'

export default function AgentDAG() {
  const nodes = useCanvasStore((s) => s.dagNodes)
  const edges = useCanvasStore((s) => s.dagEdges)

  const getNodePos = (id) => nodes.find((n) => n.id === id)

  return (
    <div className="dag-container">
      <svg width="100%" height="100%" style={{ position: 'absolute', top: 0, left: 0, zIndex: 1 }}>
        {edges.map((edge, i) => {
          const from = getNodePos(edge.from)
          const to = getNodePos(edge.to)
          if (!from || !to) return null
          return (
            <line
              key={i}
              x1={from.x + 40}
              y1={from.y + 40}
              x2={to.x + 40}
              y2={to.y + 40}
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
          style={{ left: node.x, top: node.y }}
        >
          <div className="node-icon"><IconAvatar iconKey={node.iconKey} size={16} /></div>
          <div className="node-label">{node.label}</div>
        </div>
      ))}
    </div>
  )
}
