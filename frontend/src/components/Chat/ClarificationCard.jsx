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
        background: 'rgba(16, 185, 129, 0.15)',
        border: '1px solid rgba(16, 185, 129, 0.3)',
        borderRadius: 10,
        fontSize: 13,
        color: 'var(--text-primary)',
      }}>
        已收到你的回答，正在为你生成详细方案...
      </div>
    )
  }

  return (
    <div style={{
      margin: '8px 0',
      padding: 16,
      background: 'var(--bg-secondary)',
      border: '1px solid var(--border)',
      borderRadius: 10,
    }}>
      <div style={{
        fontSize: 14,
        fontWeight: 600,
        color: 'var(--text-primary)',
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
            <div style={{ fontSize: 13, color: 'var(--text-primary)', marginBottom: 6 }}>
              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>Q{i + 1}.</span> {q}
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
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: 'var(--text-primary)',
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
          background: allAnswered ? 'var(--accent)' : 'rgba(99, 102, 241, 0.3)',
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
