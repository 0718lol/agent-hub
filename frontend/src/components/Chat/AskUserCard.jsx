import React, { useState } from 'react'
import { HelpCircle, Send, Sparkles } from 'lucide-react'

export default function AskUserCard({ question, options, onAnswer }) {
  const [selected, setSelected] = useState(null)
  const [showOther, setShowOther] = useState(false)
  const [otherText, setOtherText] = useState('')
  const [submitted, setSubmitted] = useState(false)

  const lock = (answer) => {
    setSelected(answer)
    setSubmitted(true)
    if (onAnswer) onAnswer(answer)
  }

  const handleOptionClick = (opt) => {
    if (submitted) return
    lock(opt.label)
  }

  const handleOtherSubmit = () => {
    if (submitted) return
    const text = otherText.trim()
    if (!text) return
    lock(text)
  }

  if (submitted) {
    return (
      <div style={{
        margin: '8px 0',
        padding: 14,
        background: 'rgba(16, 185, 129, 0.08)',
        border: '1px solid rgba(16, 185, 129, 0.2)',
        borderRadius: 10,
        fontSize: 13,
        color: '#10b981',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          ✓ 已选择：<strong>{selected}</strong>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      margin: '8px 0',
      padding: 16,
      background: 'rgba(168, 85, 247, 0.06)',
      border: '1px solid rgba(168, 85, 247, 0.18)',
      borderRadius: 10,
    }}>
      <div style={{
        fontSize: 13,
        fontWeight: 600,
        color: '#a855f7',
        marginBottom: 12,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        <HelpCircle size={14} />
        {question}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {options.map((opt, i) => (
          <button
            key={i}
            onClick={() => handleOptionClick(opt)}
            style={{
              padding: '10px 12px',
              background: opt.recommended
                ? 'rgba(168, 85, 247, 0.12)'
                : 'rgba(255,255,255,0.04)',
              border: opt.recommended
                ? '1px solid rgba(168, 85, 247, 0.35)'
                : '1px solid rgba(255,255,255,0.08)',
              borderRadius: 8,
              color: '#f8fafc',
              fontSize: 13,
              textAlign: 'left',
              cursor: 'pointer',
              transition: 'all 0.15s',
              display: 'flex',
              flexDirection: 'column',
              gap: 3,
              fontFamily: 'inherit',
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'rgba(168, 85, 247, 0.18)'
              e.currentTarget.style.borderColor = 'rgba(168, 85, 247, 0.5)'
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = opt.recommended
                ? 'rgba(168, 85, 247, 0.12)'
                : 'rgba(255,255,255,0.04)'
              e.currentTarget.style.borderColor = opt.recommended
                ? 'rgba(168, 85, 247, 0.35)'
                : 'rgba(255,255,255,0.08)'
            }}
          >
            <div style={{
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 6,
            }}>
              <span>{opt.label}</span>
              {opt.recommended && (
                <span style={{
                  fontSize: 10,
                  fontWeight: 500,
                  padding: '2px 6px',
                  background: 'rgba(168, 85, 247, 0.25)',
                  color: '#c4b5fd',
                  borderRadius: 4,
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 3,
                }}>
                  <Sparkles size={9} />
                  Recommended
                </span>
              )}
            </div>
            {opt.description && (
              <div style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.4 }}>
                {opt.description}
              </div>
            )}
          </button>
        ))}
      </div>

      {!showOther ? (
        <button
          onClick={() => setShowOther(true)}
          style={{
            marginTop: 10,
            padding: '8px 12px',
            width: '100%',
            background: 'transparent',
            border: '1px dashed rgba(255,255,255,0.15)',
            borderRadius: 8,
            color: '#94a3b8',
            fontSize: 12,
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
          onMouseOver={(e) => { e.currentTarget.style.borderColor = 'rgba(168, 85, 247, 0.4)' }}
          onMouseOut={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.15)' }}
        >
          ✎ Other（自定义回答）
        </button>
      ) : (
        <div style={{ marginTop: 10, display: 'flex', gap: 6 }}>
          <input
            autoFocus
            value={otherText}
            onChange={(e) => setOtherText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleOtherSubmit() }}
            placeholder="输入你的自定义答案..."
            style={{
              flex: 1,
              padding: '8px 12px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(168, 85, 247, 0.3)',
              borderRadius: 6,
              color: '#f8fafc',
              fontSize: 13,
              outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <button
            onClick={handleOtherSubmit}
            disabled={!otherText.trim()}
            style={{
              padding: '8px 12px',
              background: otherText.trim() ? '#a855f7' : 'rgba(168, 85, 247, 0.3)',
              border: 'none',
              borderRadius: 6,
              color: 'white',
              cursor: otherText.trim() ? 'pointer' : 'not-allowed',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <Send size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
