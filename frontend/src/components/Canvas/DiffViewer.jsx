import React, { useState } from 'react'

const MOCK_DIFF = [
  { type: 'context', text: 'import React from "react";' },
  { type: 'context', text: '' },
  { type: 'removed', text: 'const App = () => {' },
  { type: 'added', text: 'const App = () => {' },
  { type: 'context', text: '  const [todos, setTodos] = useState([]);' },
  { type: 'added', text: '  const [filter, setFilter] = useState("all");' },
  { type: 'context', text: '' },
  { type: 'context', text: '  return (' },
  { type: 'removed', text: '    <div className="app">' },
  { type: 'added', text: '    <div className="todo-app">' },
  { type: 'added', text: '      <FilterBar onChange={setFilter} />' },
  { type: 'context', text: '      {todos.map(t => <TodoItem key={t.id} {...t} />)}' },
  { type: 'context', text: '    </div>' },
  { type: 'context', text: '  );' },
  { type: 'context', text: '};' },
]

const FILES = ['App.jsx', 'api.js', 'TodoItem.jsx']

export default function DiffViewer() {
  const [activeFile, setActiveFile] = useState(0)

  return (
    <div>
      <div style={{ display: 'flex', gap: 4, marginBottom: 12 }}>
        {FILES.map((f, i) => (
          <button
            key={f}
            onClick={() => setActiveFile(i)}
            style={{
              padding: '6px 12px',
              background: activeFile === i ? 'rgba(99,102,241,0.2)' : 'transparent',
              border: `1px solid ${activeFile === i ? 'rgba(99,102,241,0.4)' : 'rgba(255,255,255,0.1)'}`,
              borderRadius: 6,
              color: activeFile === i ? '#6366f1' : '#94a3b8',
              cursor: 'pointer',
              fontSize: 12,
              fontFamily: 'monospace',
            }}
          >
            {f}
          </button>
        ))}
      </div>

      <div className="diff-viewer">
        {MOCK_DIFF.map((line, i) => (
          <div key={i} className={`diff-line ${line.type}`}>
            <span style={{ display: 'inline-block', width: 24, color: '#64748b', userSelect: 'none' }}>
              {line.type === 'added' ? '+' : line.type === 'removed' ? '-' : ' '}
            </span>
            {line.text || ' '}
          </div>
        ))}
      </div>
    </div>
  )
}
