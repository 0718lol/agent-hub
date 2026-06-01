import React, { useId } from 'react'

/**
 * OfficeFurniture — 俯视 2D 家具库（Marvis 风格）
 *
 * 所有家具从正上方俯视绘制，适配平面办公室场景。
 */

// ---------- 办公桌（俯视：矩形桌面 + 椅子 + 显示器）----------
export function Desk({ width = 140, height = 100, accent = '#6366f1' }) {
  const uid = useId().replace(/:/g, '')
  const gTop = `desk-top-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 140 100" overflow="visible">
      <defs>
        <linearGradient id={gTop} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#c89876" />
          <stop offset="100%" stopColor="#a47654" />
        </linearGradient>
      </defs>
      {/* 阴影 */}
      <ellipse cx="70" cy="92" rx="58" ry="6" fill="rgba(0,0,0,0.15)" />
      {/* 桌面 */}
      <rect x="10" y="30" width="120" height="60" rx="4" fill={`url(#${gTop})`} />
      {/* 显示器（顶部边缘） */}
      <rect x="40" y="35" width="60" height="8" rx="2" fill="#1e293b" />
      <rect x="42" y="37" width="56" height="4" rx="1" fill={accent} opacity="0.6" />
      {/* 键盘 */}
      <rect x="50" y="55" width="40" height="18" rx="2" fill="#3f3f46" />
      {/* 鼠标 */}
      <ellipse cx="100" cy="64" rx="5" ry="7" fill="#52525b" />
      {/* 咖啡杯 */}
      <circle cx="25" cy="50" r="6" fill="#fafafa" stroke="#a16207" strokeWidth="1.5" />
      {/* 椅子（桌子下方） */}
      <rect x="50" y="92" width="40" height="6" rx="3" fill="#6b7280" />
      <circle cx="70" cy="95" r="16" fill="#8b92a0" />
    </svg>
  )
}

// ---------- 三人沙发（俯视：长条 + 靠背）----------
export function Sofa({ width = 200, height = 90 }) {
  const uid = useId().replace(/:/g, '')
  const g = `sofa-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 200 90" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#7c8db5" />
          <stop offset="100%" stopColor="#5b6c93" />
        </linearGradient>
      </defs>
      <ellipse cx="100" cy="84" rx="88" ry="5" fill="rgba(0,0,0,0.18)" />
      {/* 靠背 */}
      <rect x="10" y="10" width="180" height="20" rx="6" fill="#6e7fa6" />
      {/* 坐垫主体 */}
      <rect x="10" y="28" width="180" height="50" rx="8" fill={`url(#${g})`} />
      {/* 三个坐垫分隔线 */}
      <line x1="70" y1="30" x2="70" y2="76" stroke="#5b6c93" strokeWidth="2" />
      <line x1="130" y1="30" x2="130" y2="76" stroke="#5b6c93" strokeWidth="2" />
      {/* 扶手 */}
      <rect x="6" y="28" width="8" height="50" rx="4" fill="#6e7fa6" />
      <rect x="186" y="28" width="8" height="50" rx="4" fill="#6e7fa6" />
    </svg>
  )
}

// ---------- 大屏电视（俯视：薄矩形 + 支架）----------
export function TV({ width = 200, height = 140 }) {
  const uid = useId().replace(/:/g, '')
  const g = `tv-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 200 140" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#ec4899" />
        </linearGradient>
      </defs>
      <ellipse cx="100" cy="132" rx="70" ry="4" fill="rgba(0,0,0,0.2)" />
      {/* 支架底座 */}
      <rect x="70" y="120" width="60" height="12" rx="4" fill="#27272a" />
      {/* 电视屏幕（薄矩形，屏幕朝下） */}
      <rect x="20" y="20" width="160" height="100" rx="4" fill="#0f172a" />
      <rect x="24" y="24" width="152" height="92" rx="2" fill={`url(#${g})`} opacity="0.85" />
      {/* 屏幕内容：简化图表 */}
      <rect x="40" y="80" width="12" height="28" rx="2" fill="rgba(255,255,255,0.6)" />
      <rect x="60" y="65" width="12" height="43" rx="2" fill="rgba(255,255,255,0.7)" />
      <rect x="80" y="50" width="12" height="58" rx="2" fill="rgba(255,255,255,0.8)" />
      <rect x="100" y="60" width="12" height="48" rx="2" fill="rgba(255,255,255,0.7)" />
      <rect x="120" y="45" width="12" height="63" rx="2" fill="rgba(255,255,255,0.85)" />
    </svg>
  )
}

// ---------- 茶几（俯视：圆角矩形桌面）----------
export function CoffeeTable({ width = 100, height = 50 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 100 50" overflow="visible">
      <ellipse cx="50" cy="46" rx="42" ry="3" fill="rgba(0,0,0,0.15)" />
      {/* 桌面 */}
      <rect x="8" y="10" width="84" height="32" rx="8" fill="#27272a" />
      <rect x="10" y="12" width="80" height="28" rx="6" fill="#3f3f46" />
      {/* 桌上物品：书 */}
      <rect x="20" y="18" width="20" height="16" rx="1" fill="#dc2626" />
      {/* 杯子 */}
      <circle cx="65" cy="26" r="6" fill="#fef3c7" stroke="#a16207" strokeWidth="1" />
    </svg>
  )
}

// ---------- 咖啡机（俯视：矩形机身）----------
export function CoffeeMachine({ width = 70, height = 110 }) {
  const uid = useId().replace(/:/g, '')
  const g = `cm-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 70 110" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#52525b" />
          <stop offset="100%" stopColor="#27272a" />
        </linearGradient>
      </defs>
      <ellipse cx="35" cy="104" rx="28" ry="3" fill="rgba(0,0,0,0.2)" />
      {/* 机身 */}
      <rect x="10" y="20" width="50" height="80" rx="6" fill={`url(#${g})`} />
      {/* 顶部显示屏 */}
      <rect x="16" y="28" width="38" height="20" rx="2" fill="#0f172a" />
      <rect x="20" y="32" width="18" height="4" fill="#22c55e" />
      {/* 出水口 */}
      <circle cx="35" cy="65" r="8" fill="#18181b" />
      <circle cx="35" cy="65" r="4" fill="#0f172a" />
      {/* 杯子托盘 */}
      <rect x="20" y="85" width="30" height="12" rx="2" fill="#1f2937" />
    </svg>
  )
}

// ---------- 跑步机（俯视：椭圆跑带 + 控制台）----------
export function Treadmill({ width = 140, height = 130 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 140 130" overflow="visible">
      <ellipse cx="70" cy="124" rx="58" ry="4" fill="rgba(0,0,0,0.2)" />
      {/* 跑带 */}
      <ellipse cx="70" cy="75" rx="50" ry="38" fill="#000" />
      <ellipse cx="70" cy="75" rx="44" ry="32" fill="#1f2937" />
      {/* 跑带条纹 */}
      <line x1="40" y1="75" x2="100" y2="75" stroke="#52525b" strokeWidth="1.5" />
      <line x1="45" y1="60" x2="95" y2="60" stroke="#52525b" strokeWidth="1" />
      <line x1="45" y1="90" x2="95" y2="90" stroke="#52525b" strokeWidth="1" />
      {/* 控制台（顶部） */}
      <rect x="30" y="20" width="80" height="28" rx="4" fill="#27272a" />
      <rect x="35" y="25" width="70" height="18" rx="2" fill="#0f172a" />
      {/* 数据显示 */}
      <text x="45" y="37" fill="#22c55e" fontSize="8" fontFamily="monospace">5.2km</text>
      <text x="80" y="37" fill="#ef4444" fontSize="8" fontFamily="monospace">142</text>
    </svg>
  )
}

// ---------- 盆栽（俯视：圆形盆 + 叶子）----------
export function Plant({ width = 60, height = 100 }) {
  const uid = useId().replace(/:/g, '')
  const g = `pot-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 60 100" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#a16207" />
          <stop offset="100%" stopColor="#713f12" />
        </linearGradient>
      </defs>
      <ellipse cx="30" cy="94" rx="20" ry="3" fill="rgba(0,0,0,0.2)" />
      {/* 花盆（圆形俯视） */}
      <circle cx="30" cy="70" r="18" fill={`url(#${g})`} />
      <circle cx="30" cy="70" r="15" fill="#78350f" />
      {/* 土壤 */}
      <circle cx="30" cy="70" r="13" fill="#3f1d05" />
      {/* 叶子（俯视：多个椭圆辐射状） */}
      <ellipse cx="30" cy="50" rx="10" ry="18" fill="#16a34a" />
      <ellipse cx="30" cy="50" rx="18" ry="10" fill="#15803d" />
      <ellipse cx="20" cy="55" rx="8" ry="14" fill="#22c55e" transform="rotate(-35 20 55)" />
      <ellipse cx="40" cy="55" rx="8" ry="14" fill="#22c55e" transform="rotate(35 40 55)" />
      <ellipse cx="25" cy="45" rx="6" ry="10" fill="#16a34a" transform="rotate(-60 25 45)" />
      <ellipse cx="35" cy="45" rx="6" ry="10" fill="#16a34a" transform="rotate(60 35 45)" />
    </svg>
  )
}

// ---------- 落地窗（俯视：墙上的矩形窗框）----------
export function Window({ width = 160, height = 120 }) {
  const uid = useId().replace(/:/g, '')
  const g = `sky-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 160 120" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#bae6fd" />
        </linearGradient>
      </defs>
      {/* 窗框（嵌在墙里，俯视看到顶边） */}
      <rect x="0" y="0" width="160" height="120" rx="4" fill="#525252" />
      {/* 玻璃 */}
      <rect x="6" y="6" width="148" height="108" fill={`url(#${g})`} opacity="0.7" />
      {/* 十字格 */}
      <rect x="76" y="6" width="4" height="108" fill="#525252" opacity="0.5" />
      <rect x="6" y="58" width="148" height="4" fill="#525252" opacity="0.5" />
      {/* 远景：云（简化） */}
      <ellipse cx="40" cy="35" rx="14" ry="8" fill="rgba(255,255,255,0.6)" />
      <ellipse cx="120" cy="50" rx="18" ry="10" fill="rgba(255,255,255,0.6)" />
    </svg>
  )
}

// ---------- 白板（俯视：墙上矩形）----------
export function Whiteboard({ width = 150, height = 100 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 150 100" overflow="visible">
      {/* 框 */}
      <rect x="0" y="0" width="150" height="100" rx="3" fill="#a1a1aa" />
      {/* 白板面 */}
      <rect x="4" y="4" width="142" height="92" fill="#fafafa" />
      {/* 涂鸦：流程图（俯视简化） */}
      <rect x="20" y="20" width="28" height="20" rx="2" fill="#fef3c7" stroke="#f59e0b" strokeWidth="1.5" />
      <rect x="62" y="20" width="28" height="20" rx="2" fill="#dbeafe" stroke="#3b82f6" strokeWidth="1.5" />
      <rect x="104" y="20" width="28" height="20" rx="2" fill="#dcfce7" stroke="#22c55e" strokeWidth="1.5" />
      {/* 箭头 */}
      <line x1="48" y1="30" x2="60" y2="30" stroke="#52525b" strokeWidth="1.5" />
      <line x1="90" y1="30" x2="102" y2="30" stroke="#52525b" strokeWidth="1.5" />
      {/* 文字线 */}
      <line x1="20" y1="55" x2="80" y2="55" stroke="#3b82f6" strokeWidth="1.5" />
      <line x1="20" y1="65" x2="100" y2="65" stroke="#52525b" strokeWidth="1" />
      <line x1="20" y1="75" x2="70" y2="75" stroke="#52525b" strokeWidth="1" />
    </svg>
  )
}

// ---------- 装饰挂画（俯视：墙上矩形）----------
export function WallArt({ width = 80, height = 60 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 80 60" overflow="visible">
      <rect x="0" y="0" width="80" height="60" fill="#92400e" />
      <rect x="3" y="3" width="74" height="54" fill="#fef3c7" />
      {/* 抽象图案 */}
      <circle cx="25" cy="20" r="8" fill="#f59e0b" />
      <path d="M 8 50 L 30 30 L 50 42 L 72 22 L 72 50 Z" fill="#f97316" />
      <path d="M 8 50 L 50 50 L 72 50 L 72 54 L 8 54 Z" fill="#15803d" />
    </svg>
  )
}

// ---------- 吊灯（俯视：圆形灯罩 + 光晕）----------
export function PendantLamp({ width = 50, height = 80 }) {
  const uid = useId().replace(/:/g, '')
  const g = `lamp-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 50 80" overflow="visible">
      <defs>
        <radialGradient id={g}>
          <stop offset="0%" stopColor="#fef3c7" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#fef3c7" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* 光晕 */}
      <ellipse cx="25" cy="40" rx="22" ry="22" fill={`url(#${g})`} />
      {/* 灯罩（圆形俯视） */}
      <circle cx="25" cy="40" r="16" fill="#1f2937" />
      <circle cx="25" cy="40" r="12" fill="#374151" />
      {/* 灯泡中心 */}
      <circle cx="25" cy="40" r="4" fill="#fef3c7">
        <animate attributeName="opacity" values="0.85;1;0.85" dur="3s" repeatCount="indefinite" />
      </circle>
    </svg>
  )
}

// ---------- 散步小径（俯视：圆形地毯）----------
export function ZenSpot({ width = 130, height = 100 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 130 100" overflow="visible">
      {/* 圆形地毯 */}
      <ellipse cx="65" cy="50" rx="58" ry="42" fill="#86efac" opacity="0.3" />
      <ellipse cx="65" cy="50" rx="48" ry="34" fill="#22c55e" opacity="0.2" />
      <ellipse cx="65" cy="50" rx="36" ry="26" fill="#15803d" opacity="0.2" />
      {/* 小石头 */}
      <ellipse cx="30" cy="40" rx="5" ry="4" fill="#a8a29e" />
      <ellipse cx="95" cy="55" rx="4" ry="3" fill="#a8a29e" />
      <ellipse cx="50" cy="65" rx="3" ry="2.5" fill="#78716c" />
    </svg>
  )
}
