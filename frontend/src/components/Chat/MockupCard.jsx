import React from 'react'

const MOCKUPS = {
  todo: {
    title: 'Todo App',
    sections: [
      { type: 'header', label: 'Todo List', color: '#6366f1' },
      { type: 'input', label: '添加任务...', button: '添加' },
      { type: 'list', items: ['学习 React', '写后端 API', '部署上线'], done: [false, true, false] },
    ],
  },
  dashboard: {
    title: 'Dashboard',
    sections: [
      { type: 'header', label: '数据概览', color: '#22d3ee' },
      { type: 'cards', items: ['用户数 1.2k', '订单 856', '收入 ¥52k', '转化率 3.2%'] },
      { type: 'chart' },
    ],
  },
  login: {
    title: 'Login Page',
    sections: [
      { type: 'header', label: '登录', color: '#f59e0b' },
      { type: 'form', fields: ['邮箱地址', '密码'] },
      { type: 'button', label: '登录' },
      { type: 'link', label: '忘记密码？' },
    ],
  },
  ecommerce: {
    title: '商品列表',
    sections: [
      { type: 'header', label: '精选商品', color: '#10b981' },
      { type: 'products', items: ['耳机 ¥299', '键盘 ¥599', '鼠标 ¥199', '显示器 ¥2499'] },
    ],
  },
  promo: {
    title: '营销落地页',
    sections: [
      { type: 'hero', label: '🍦 巧乐兹 — 一口甜蜜', sub: '经典巧克力脆层 × 绵密冰淇淋', color: '#f97316' },
      { type: 'cards', items: ['🍫 浓郁巧克力', '🥛 新鲜奶源', '✨ 多种口味', '🎉 限时优惠'] },
      { type: 'button', label: '立即尝鲜 →' },
    ],
  },
}

export default function MockupCard({ type = 'todo' }) {
  const mockup = MOCKUPS[type] || MOCKUPS.todo
  const width = 320
  const height = 360

  return (
    <div style={{
      margin: '8px 0',
      borderRadius: 10,
      overflow: 'hidden',
      border: '1px solid rgba(255,255,255,0.1)',
      background: '#0f172a',
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '8px 12px',
        background: 'rgba(255,255,255,0.05)',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
      }}>
        <span style={{ fontSize: 12, color: '#94a3b8' }}>UI 原型 — {mockup.title}</span>
        <span style={{ fontSize: 11, color: '#6366f1', cursor: 'pointer' }}>导出 SVG</span>
      </div>
      <div style={{ padding: 12, display: 'flex', justifyContent: 'center' }}>
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ borderRadius: 8 }}>
          <rect width={width} height={height} fill="#1e293b" rx="8" />

          {mockup.sections.map((section, i) => {
            const y = 16 + i * 80
            return renderSection(section, i, y, width)
          })}
        </svg>
      </div>
    </div>
  )
}

function renderSection(section, index, y, width) {
  const padding = 20
  const contentWidth = width - padding * 2

  switch (section.type) {
    case 'header':
      return (
        <g key={index}>
          <rect x={padding} y={y} width={contentWidth} height={32} rx="6" fill={section.color} opacity="0.15" />
          <text x={padding + 12} y={y + 22} fill={section.color} fontSize="14" fontWeight="600">{section.label}</text>
        </g>
      )

    case 'hero':
      return (
        <g key={index}>
          <defs>
            <linearGradient id={`heroGrad-${index}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={section.color} stopOpacity="0.3" />
              <stop offset="100%" stopColor={section.color} stopOpacity="0.05" />
            </linearGradient>
          </defs>
          <rect x={padding} y={y} width={contentWidth} height={70} rx="10" fill={`url(#heroGrad-${index})`} />
          <text x={width / 2} y={y + 28} fill={section.color} fontSize="15" fontWeight="700" textAnchor="middle">{section.label}</text>
          <text x={width / 2} y={y + 48} fill="#94a3b8" fontSize="11" textAnchor="middle">{section.sub}</text>
        </g>
      )

    case 'input':
      return (
        <g key={index}>
          <rect x={padding} y={y} width={contentWidth - 60} height={32} rx="6" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
          <text x={padding + 10} y={y + 21} fill="#64748b" fontSize="12">{section.label}</text>
          <rect x={width - padding - 50} y={y} width={50} height={32} rx="6" fill="#6366f1" />
          <text x={width - padding - 35} y={y + 21} fill="white" fontSize="12" fontWeight="500">{section.button}</text>
        </g>
      )

    case 'list':
      return (
        <g key={index}>
          {section.items.map((item, i) => {
            const itemY = y + i * 38
            const isDone = section.done?.[i]
            return (
              <g key={i}>
                <rect x={padding} y={itemY} width={contentWidth} height={32} rx="6" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
                <rect x={padding + 8} y={itemY + 8} width={16} height={16} rx="3" fill={isDone ? '#6366f1' : 'transparent'} stroke="#6366f1" strokeWidth="1.5" />
                {isDone && <text x={padding + 12} y={itemY + 21} fill="white" fontSize="10">✓</text>}
                <text x={padding + 32} y={itemY + 21} fill={isDone ? '#64748b' : '#e2e8f0'} fontSize="12" textDecoration={isDone ? 'line-through' : 'none'}>{item}</text>
              </g>
            )
          })}
        </g>
      )

    case 'cards':
      return (
        <g key={index}>
          {section.items.map((item, i) => {
            const cardX = padding + i * 72
            return (
              <g key={i}>
                <rect x={cardX} y={y} width={64} height={50} rx="6" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
                <text x={cardX + 32} y={y + 20} fill="#94a3b8" fontSize="8" textAnchor="middle">{item.split(' ')[0]}</text>
                <text x={cardX + 32} y={y + 36} fill="#e2e8f0" fontSize="11" fontWeight="600" textAnchor="middle">{item.split(' ')[1]}</text>
              </g>
            )
          })}
        </g>
      )

    case 'chart':
      const bars = [40, 65, 50, 80, 55, 70, 45]
      return (
        <g key={index}>
          {bars.map((h, i) => {
            const barX = padding + i * 38
            const barH = h * 0.6
            return (
              <rect key={i} x={barX} y={y + 60 - barH} width={28} height={barH} rx="4" fill="#6366f1" opacity={0.5 + i * 0.07} />
            )
          })}
        </g>
      )

    case 'form':
      return (
        <g key={index}>
          {section.fields.map((field, i) => {
            const fieldY = y + i * 44
            return (
              <g key={i}>
                <text x={padding} y={fieldY + 12} fill="#94a3b8" fontSize="11">{field}</text>
                <rect x={padding} y={fieldY + 16} width={contentWidth} height={28} rx="6" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
              </g>
            )
          })}
        </g>
      )

    case 'button':
      return (
        <g key={index}>
          <rect x={padding} y={y} width={contentWidth} height={36} rx="8" fill="#6366f1" />
          <text x={width / 2} y={y + 24} fill="white" fontSize="14" fontWeight="600" textAnchor="middle">{section.label}</text>
        </g>
      )

    case 'link':
      return (
        <g key={index}>
          <text x={width / 2} y={y + 16} fill="#6366f1" fontSize="12" textAnchor="middle" textDecoration="underline">{section.label}</text>
        </g>
      )

    case 'products':
      return (
        <g key={index}>
          {section.items.map((item, i) => {
            const col = i % 2
            const row = Math.floor(i / 2)
            const cardX = padding + col * 140
            const cardY = y + row * 80
            return (
              <g key={i}>
                <rect x={cardX} y={cardY} width={130} height={70} rx="8" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
                <rect x={cardX + 10} y={cardY + 10} width={110} height={30} rx="4" fill="rgba(255,255,255,0.03)" />
                <text x={cardX + 65} y={cardY + 30} fill="#475569" fontSize="8" textAnchor="middle">商品图</text>
                <text x={cardX + 10} y={cardY + 55} fill="#e2e8f0" fontSize="11">{item.split(' ')[0]}</text>
                <text x={cardX + 120} y={cardY + 55} fill="#6366f1" fontSize="11" fontWeight="600" textAnchor="end">{item.split(' ')[1]}</text>
              </g>
            )
          })}
        </g>
      )

    default:
      return null
  }
}
