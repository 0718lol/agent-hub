import React, { useEffect, useRef, useState, useCallback } from 'react'

const clamp = (v, min, max) => Math.max(min, Math.min(max, v))

function loadPosition(storageKey, defaultPos) {
  if (!storageKey) return defaultPos
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return defaultPos
    const parsed = JSON.parse(raw)
    if (typeof parsed.x === 'number' && typeof parsed.y === 'number') return parsed
  } catch {}
  return defaultPos
}

function savePosition(storageKey, pos) {
  if (!storageKey) return
  try {
    localStorage.setItem(storageKey, JSON.stringify(pos))
  } catch {}
}

export default function DraggableFloating({
  defaultPosition,
  storageKey = 'agenthub-pet-pos',
  width = 96,
  height = 130,
  edgeMargin = 8,
  zIndex = 9999,
  draggable = true,
  snapToEdge = false,
  onPositionChange,
  children,
}) {
  const fallback = defaultPosition || {
    x: typeof window !== 'undefined' ? window.innerWidth - width - 24 : 0,
    y: typeof window !== 'undefined' ? window.innerHeight - height - 24 : 0,
  }
  const [pos, setPos] = useState(() => loadPosition(storageKey, fallback))
  const [dragging, setDragging] = useState(false)
  const offsetRef = useRef({ x: 0, y: 0 })
  const movedRef = useRef(false)
  const elRef = useRef(null)

  useEffect(() => {
    const onResize = () => {
      setPos((p) => ({
        x: clamp(p.x, edgeMargin, window.innerWidth - width - edgeMargin),
        y: clamp(p.y, edgeMargin, window.innerHeight - height - edgeMargin),
      }))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [width, height, edgeMargin])

  const handlePointerDown = useCallback((e) => {
    if (!draggable) return
    if (e.button !== undefined && e.button !== 0) return
    movedRef.current = false
    offsetRef.current = { x: e.clientX - pos.x, y: e.clientY - pos.y }
    setDragging(true)
    try { e.target.setPointerCapture(e.pointerId) } catch {}
  }, [draggable, pos.x, pos.y])

  const handlePointerMove = useCallback((e) => {
    if (!dragging) return
    const dx = Math.abs((e.clientX - offsetRef.current.x) - pos.x)
    const dy = Math.abs((e.clientY - offsetRef.current.y) - pos.y)
    if (dx > 3 || dy > 3) movedRef.current = true
    const next = {
      x: clamp(e.clientX - offsetRef.current.x, edgeMargin, window.innerWidth - width - edgeMargin),
      y: clamp(e.clientY - offsetRef.current.y, edgeMargin, window.innerHeight - height - edgeMargin),
    }
    setPos(next)
  }, [dragging, edgeMargin, width, height, pos.x, pos.y])

  const handlePointerUp = useCallback((e) => {
    if (!dragging) return
    setDragging(false)
    try { e.target.releasePointerCapture(e.pointerId) } catch {}
    let final = pos
    if (snapToEdge) {
      const midX = pos.x + width / 2
      final = { ...pos, x: midX < window.innerWidth / 2 ? edgeMargin : window.innerWidth - width - edgeMargin }
      setPos(final)
    }
    savePosition(storageKey, final)
    onPositionChange && onPositionChange(final)
  }, [dragging, pos, snapToEdge, storageKey, width, edgeMargin, onPositionChange])

  const handleClickCapture = useCallback((e) => {
    if (movedRef.current) {
      e.stopPropagation()
      e.preventDefault()
      movedRef.current = false
    }
  }, [])

  return (
    <div
      ref={elRef}
      className={`df-floating ${dragging ? 'df-dragging' : ''}`}
      style={{
        position: 'fixed',
        left: pos.x,
        top: pos.y,
        width,
        height,
        zIndex,
        cursor: draggable ? (dragging ? 'grabbing' : 'grab') : 'default',
        touchAction: 'none',
        userSelect: 'none',
        transition: dragging ? 'none' : 'left 0.3s ease, top 0.3s ease',
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={handlePointerUp}
      onClickCapture={handleClickCapture}
    >
      {children}
    </div>
  )
}
