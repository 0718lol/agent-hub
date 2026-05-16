import React, { useState } from 'react'

export default function ClarificationCard({ questions, onSubmit }) {
  const [answers, setAnswers] = useState(questions.map(() => ''))
  const [submitted, setSubmitted] = useState(false)

  const handleSubmit = () => {
    setSubmitted(true)
    if (onSubmit) {
      onSubmit(questions.map((q, i) => ({ question: q, answer: answers[i] })))
    }
  }

  const allAnswered = answers.every((a) => a.trim().length > 0)

  if (submitted) {
    return (
      <div style={{
        margin: '8px 0',
        padding: 16,
        background: 'rgba(16, 185, 129, 0.08)',
        border: '1px solid rgba(16, 185, 129, 0.2)',
        borderRadius: 10,
        fontSize: 13,
        color: '#10b981',
      }}>
        已收到你的回答，正在为你生成详细方案...
      </div>
    )
  }

  return (
    <div style={{
      margin: '8px 0',
      padding: 16,
      background: 'rgba(99, 102, 241, 0.06)',
      border: '1px solid rgba(99, 102, 241, 0.15)',
      borderRadius: 10,
    }}>
      <div style={{
        fontSize: 13,
        fontWeight: 600,
        color: '#6366f1',
        marginBottom: 12,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        需求澄清
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {questions.map((q, i) => (
          <div key={i}>
            <div style={{ fontSize: 13, color: '#e2e8f0', marginBottom: 6 }}>
              <span style={{ color: '#6366f1', fontWeight: 600 }}>Q{i + 1}.</span> {q}
            </div>
            <input
              value={answers[i]}
              onChange={(e) => {
                const next = [...answers]
                next[i] = e.target.value
                setAnswers(next)
              }}
              placeholder="请输入你的回答..."
              style={{
                width: '100%',
                padding: '8px 12px',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 6,
                color: '#f8fafc',
                fontSize: 13,
                outline: 'none',
                fontFamily: 'inherit',
              }}
            />
          </div>
        ))}
      </div>

      <button
        onClick={handleSubmit}
        disabled={!allAnswered}
        style={{
          marginTop: 14,
          width: '100%',
          padding: '10px',
          background: allAnswered ? '#6366f1' : 'rgba(99, 102, 241, 0.3)',
          border: 'none',
          borderRadius: 8,
          color: 'white',
          fontSize: 13,
          fontWeight: 600,
          cursor: allAnswered ? 'pointer' : 'not-allowed',
          transition: 'all 0.2s',
        }}
      >
        提交回答
      </button>
    </div>
  )
}
