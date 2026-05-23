import React from 'react'
import Sidebar from './components/Layout/Sidebar'
import ChatPanel from './components/Layout/ChatPanel'
import SlidePanel from './components/Layout/SlidePanel'

export default function App() {
  return (
    <div className="app-layout">
      <Sidebar />
      <ChatPanel />
      <SlidePanel />
    </div>
  )
}
