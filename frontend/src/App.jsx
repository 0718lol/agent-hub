import React from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import CanvasPanel from './components/Layout/CanvasPanel'

export default function App() {
  return (
    <div className="app-layout">
      <Sidebar />
      <ChatPanel />
      <CanvasPanel />
    </div>
  )
}
