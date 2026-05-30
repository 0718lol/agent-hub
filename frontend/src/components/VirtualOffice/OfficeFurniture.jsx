import React, { useId } from 'react'

/**
 * OfficeFurniture — 矢量办公家具库（无 emoji）
 *
 * 所有家具用 SVG 路径绘制，正面/3-4 视角，扁平现代风。
 * 接受 width/height props，按比例缩放。
 *
 * 使用方式：
 *   <Desk width={140} height={100} />
 *   <Sofa width={180} height={90} />
 */

// ---------- 办公桌（带显示器）----------
export function Desk({ width = 140, height = 100, accent = '#6366f1' }) {
  const uid = useId().replace(/:/g, '')
  const gTop = `desk-top-${uid}`
  const gScr = `desk-scr-${uid}`
  const w = width
  const h = height
  return (
    <svg width={w} height={h} viewBox="0 0 140 100" overflow="visible">
      <defs>
        <linearGradient id={gTop} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#c89876" />
          <stop offset="100%" stopColor="#a47654" />
        </linearGradient>
        <linearGradient id={gScr} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
      </defs>
      {/* 桌脚阴影 */}
      <ellipse cx="70" cy="92" rx="62" ry="5" fill="rgba(0,0,0,0.18)" />
      {/* 桌腿 */}
      <rect x="14" y="58" width="6" height="32" rx="2" fill="#5d3f28" />
      <rect x="120" y="58" width="6" height="32" rx="2" fill="#5d3f28" />
      {/* 桌面（梯形透视感） */}
      <path d="M 8 58 L 132 58 L 128 78 L 12 78 Z" fill={`url(#${gTop})`} />
      <rect x="8" y="55" width="124" height="6" rx="2" fill="#a47654" />
      {/* 显示器底座 */}
      <rect x="62" y="50" width="16" height="6" rx="1" fill="#52525b" />
      <rect x="66" y="44" width="8" height="8" fill="#52525b" />
      {/* 显示器屏幕 */}
      <rect x="42" y="14" width="56" height="34" rx="3" fill="#27272a" />
      <rect x="44" y="16" width="52" height="30" rx="2" fill={`url(#${gScr})`} />
      {/* 屏幕内容线条（代码感） */}
      <rect x="48" y="20" width="20" height="2" rx="1" fill={accent} opacity="0.7" />
      <rect x="48" y="25" width="34" height="2" rx="1" fill="#64748b" opacity="0.6" />
      <rect x="52" y="30" width="28" height="2" rx="1" fill="#64748b" opacity="0.5" />
      <rect x="48" y="35" width="38" height="2" rx="1" fill={accent} opacity="0.5" />
      <rect x="52" y="40" width="22" height="2" rx="1" fill="#64748b" opacity="0.4" />
      {/* 桌面物品：键盘 */}
      <rect x="48" y="62" width="44" height="6" rx="1" fill="#3f3f46" />
      {/* 咖啡杯 */}
      <ellipse cx="108" cy="64" rx="6" ry="2" fill="#fafafa" />
      <rect x="102" y="58" width="12" height="6" rx="1" fill="#fafafa" />
      <path d="M 114 60 Q 118 60 118 63 Q 118 66 114 66" stroke="#fafafa" strokeWidth="1.5" fill="none" />
    </svg>
  )
}

// ---------- 三人沙发 ----------
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
      <ellipse cx="100" cy="84" rx="92" ry="4" fill="rgba(0,0,0,0.18)" />
      {/* 沙发主体 */}
      <rect x="6" y="36" width="188" height="46" rx="8" fill={`url(#${g})`} />
      {/* 左右扶手 */}
      <rect x="0" y="28" width="20" height="56" rx="6" fill="#6e7fa6" />
      <rect x="180" y="28" width="20" height="56" rx="6" fill="#6e7fa6" />
      {/* 三个靠垫 */}
      <rect x="22" y="20" width="50" height="36" rx="6" fill="#8a9bc2" stroke="#6e7fa6" strokeWidth="1" />
      <rect x="75" y="20" width="50" height="36" rx="6" fill="#8a9bc2" stroke="#6e7fa6" strokeWidth="1" />
      <rect x="128" y="20" width="50" height="36" rx="6" fill="#8a9bc2" stroke="#6e7fa6" strokeWidth="1" />
      {/* 坐垫高光 */}
      <rect x="24" y="22" width="46" height="4" rx="2" fill="rgba(255,255,255,0.25)" />
      <rect x="77" y="22" width="46" height="4" rx="2" fill="rgba(255,255,255,0.25)" />
      <rect x="130" y="22" width="46" height="4" rx="2" fill="rgba(255,255,255,0.25)" />
    </svg>
  )
}

// ---------- 大屏电视 ----------
export function TV({ width = 200, height = 140 }) {
  const uid = useId().replace(/:/g, '')
  const g = `tv-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 200 140" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#ec4899" />
        </linearGradient>
      </defs>
      {/* 阴影 */}
      <ellipse cx="100" cy="135" rx="80" ry="3" fill="rgba(0,0,0,0.2)" />
      {/* 电视支架 */}
      <rect x="92" y="118" width="16" height="14" fill="#27272a" />
      <rect x="70" y="130" width="60" height="4" rx="2" fill="#27272a" />
      {/* 电视外框 */}
      <rect x="6" y="6" width="188" height="116" rx="6" fill="#0f172a" />
      <rect x="10" y="10" width="180" height="108" rx="3" fill={`url(#${g})`} opacity="0.85" />
      {/* 屏幕内容：抽象图表 */}
      <rect x="22" y="84" width="14" height="22" rx="2" fill="rgba(255,255,255,0.5)" />
      <rect x="42" y="68" width="14" height="38" rx="2" fill="rgba(255,255,255,0.6)" />
      <rect x="62" y="50" width="14" height="56" rx="2" fill="rgba(255,255,255,0.7)" />
      <rect x="82" y="60" width="14" height="46" rx="2" fill="rgba(255,255,255,0.6)" />
      <rect x="102" y="40" width="14" height="66" rx="2" fill="rgba(255,255,255,0.8)" />
      {/* 折线 */}
      <polyline points="22,40 50,30 80,38 110,22 140,28 170,18" stroke="#fafafa" strokeWidth="2" fill="none" opacity="0.85" />
      {/* 高光 */}
      <rect x="14" y="14" width="60" height="4" rx="2" fill="rgba(255,255,255,0.4)" />
    </svg>
  )
}

// ---------- 茶几 ----------
export function CoffeeTable({ width = 100, height = 50 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 100 50" overflow="visible">
      <ellipse cx="50" cy="46" rx="44" ry="3" fill="rgba(0,0,0,0.15)" />
      {/* 桌腿 */}
      <rect x="10" y="24" width="4" height="20" fill="#3f3f46" />
      <rect x="86" y="24" width="4" height="20" fill="#3f3f46" />
      {/* 桌面 */}
      <rect x="4" y="20" width="92" height="8" rx="2" fill="#27272a" />
      <rect x="4" y="18" width="92" height="3" rx="1" fill="#52525b" />
      {/* 桌上书本 */}
      <rect x="20" y="11" width="22" height="9" rx="1" fill="#dc2626" />
      <rect x="22" y="13" width="18" height="2" fill="rgba(255,255,255,0.3)" />
      {/* 杯子 */}
      <ellipse cx="68" cy="18" rx="6" ry="2" fill="#fef3c7" />
      <rect x="62" y="11" width="12" height="8" rx="1" fill="#fef3c7" />
    </svg>
  )
}

// ---------- 咖啡机 ----------
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
      <ellipse cx="35" cy="106" rx="32" ry="2" fill="rgba(0,0,0,0.2)" />
      {/* 主体 */}
      <rect x="6" y="14" width="58" height="92" rx="6" fill={`url(#${g})`} />
      {/* 顶盖 */}
      <rect x="10" y="6" width="50" height="12" rx="3" fill="#3f3f46" />
      {/* 显示屏 */}
      <rect x="14" y="22" width="42" height="14" rx="2" fill="#0f172a" />
      <rect x="18" y="26" width="20" height="3" fill="#22c55e" />
      <rect x="18" y="31" width="14" height="2" fill="#22c55e" opacity="0.6" />
      {/* 出水嘴 */}
      <rect x="28" y="50" width="14" height="10" fill="#18181b" />
      <rect x="32" y="58" width="6" height="6" fill="#0f172a" />
      {/* 杯子 */}
      <rect x="22" y="68" width="26" height="16" rx="2" fill="#fafafa" />
      <ellipse cx="35" cy="68" rx="13" ry="2" fill="#92400e" />
      {/* 热气 */}
      <path d="M 30 40 Q 28 32 30 24 Q 32 20 30 14" stroke="rgba(255,255,255,0.4)" strokeWidth="2" fill="none" strokeLinecap="round">
        <animate attributeName="opacity" values="0.6;0.2;0.6" dur="2s" repeatCount="indefinite" />
      </path>
      <path d="M 40 40 Q 42 32 40 24 Q 38 20 40 14" stroke="rgba(255,255,255,0.4)" strokeWidth="2" fill="none" strokeLinecap="round">
        <animate attributeName="opacity" values="0.2;0.6;0.2" dur="2s" repeatCount="indefinite" />
      </path>
    </svg>
  )
}

// ---------- 跑步机 ----------
export function Treadmill({ width = 140, height = 130 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 140 130" overflow="visible">
      <ellipse cx="70" cy="126" rx="62" ry="3" fill="rgba(0,0,0,0.2)" />
      {/* 跑带底座 */}
      <rect x="14" y="92" width="112" height="32" rx="6" fill="#1f2937" />
      <rect x="20" y="98" width="100" height="20" rx="2" fill="#000" />
      {/* 跑带条纹 */}
      <line x1="30" y1="108" x2="40" y2="108" stroke="#52525b" strokeWidth="1.5" />
      <line x1="60" y1="108" x2="70" y2="108" stroke="#52525b" strokeWidth="1.5" />
      <line x1="90" y1="108" x2="100" y2="108" stroke="#52525b" strokeWidth="1.5" />
      {/* 控制台支柱 */}
      <rect x="22" y="40" width="8" height="56" fill="#27272a" />
      <rect x="110" y="40" width="8" height="56" fill="#27272a" />
      {/* 控制台 */}
      <rect x="14" y="14" width="112" height="34" rx="6" fill="#27272a" />
      <rect x="20" y="20" width="100" height="22" rx="3" fill="#0f172a" />
      {/* 跑步数据 */}
      <text x="32" y="33" fill="#22c55e" fontSize="10" fontFamily="monospace">5.2 km</text>
      <text x="78" y="33" fill="#ef4444" fontSize="10" fontFamily="monospace">142 bpm</text>
    </svg>
  )
}

// ---------- 盆栽 ----------
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
      <ellipse cx="30" cy="96" rx="22" ry="2" fill="rgba(0,0,0,0.2)" />
      {/* 花盆 */}
      <path d="M 12 70 L 48 70 L 44 95 L 16 95 Z" fill={`url(#${g})`} />
      <ellipse cx="30" cy="70" rx="18" ry="3" fill="#78350f" />
      {/* 土壤 */}
      <ellipse cx="30" cy="70" rx="16" ry="2" fill="#3f1d05" />
      {/* 叶子 */}
      <ellipse cx="22" cy="50" rx="8" ry="22" fill="#16a34a" transform="rotate(-25 22 50)" />
      <ellipse cx="38" cy="48" rx="8" ry="22" fill="#15803d" transform="rotate(28 38 48)" />
      <ellipse cx="30" cy="40" rx="7" ry="26" fill="#22c55e" />
      <ellipse cx="26" cy="58" rx="6" ry="14" fill="#16a34a" transform="rotate(-15 26 58)" />
      <ellipse cx="34" cy="58" rx="6" ry="14" fill="#15803d" transform="rotate(15 34 58)" />
    </svg>
  )
}

// ---------- 落地窗 ----------
export function Window({ width = 160, height = 120 }) {
  const uid = useId().replace(/:/g, '')
  const g = `sky-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 160 120" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#bae6fd" />
        </linearGradient>
      </defs>
      {/* 窗框 */}
      <rect x="0" y="0" width="160" height="120" rx="4" fill="#525252" />
      {/* 玻璃 */}
      <rect x="6" y="6" width="148" height="108" fill={`url(#${g})`} />
      {/* 十字格 */}
      <rect x="76" y="6" width="4" height="108" fill="#525252" />
      <rect x="6" y="58" width="148" height="4" fill="#525252" />
      {/* 远景：太阳 */}
      <circle cx="120" cy="30" r="10" fill="#fef3c7" opacity="0.8" />
      {/* 云 */}
      <ellipse cx="40" cy="35" rx="16" ry="5" fill="rgba(255,255,255,0.7)" />
      <ellipse cx="46" cy="32" rx="10" ry="4" fill="rgba(255,255,255,0.7)" />
      {/* 楼宇剪影 */}
      <rect x="10" y="80" width="20" height="32" fill="rgba(100,116,139,0.4)" />
      <rect x="35" y="70" width="30" height="42" fill="rgba(100,116,139,0.4)" />
      <rect x="100" y="75" width="24" height="37" fill="rgba(100,116,139,0.4)" />
      <rect x="128" y="68" width="22" height="44" fill="rgba(100,116,139,0.4)" />
    </svg>
  )
}

// ---------- 白板 ----------
export function Whiteboard({ width = 150, height = 100 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 150 100" overflow="visible">
      {/* 框 */}
      <rect x="0" y="0" width="150" height="100" rx="3" fill="#a1a1aa" />
      {/* 白板面 */}
      <rect x="4" y="4" width="142" height="92" fill="#fafafa" />
      {/* 涂鸦：流程图 */}
      <rect x="14" y="14" width="32" height="18" rx="2" fill="#fef3c7" stroke="#f59e0b" strokeWidth="1.5" />
      <rect x="58" y="14" width="32" height="18" rx="2" fill="#dbeafe" stroke="#3b82f6" strokeWidth="1.5" />
      <rect x="102" y="14" width="32" height="18" rx="2" fill="#dcfce7" stroke="#22c55e" strokeWidth="1.5" />
      {/* 箭头 */}
      <line x1="46" y1="23" x2="56" y2="23" stroke="#52525b" strokeWidth="1.5" />
      <line x1="90" y1="23" x2="100" y2="23" stroke="#52525b" strokeWidth="1.5" />
      {/* 涂鸦文字线 */}
      <line x1="14" y1="48" x2="80" y2="48" stroke="#3b82f6" strokeWidth="1.5" />
      <line x1="14" y1="56" x2="100" y2="56" stroke="#52525b" strokeWidth="1" />
      <line x1="14" y1="64" x2="76" y2="64" stroke="#52525b" strokeWidth="1" />
      {/* 红色重点圈 */}
      <circle cx="106" cy="62" r="14" fill="none" stroke="#ef4444" strokeWidth="2" />
      <text x="98" y="66" fontSize="10" fill="#ef4444" fontWeight="700">PM</text>
    </svg>
  )
}

// ---------- 装饰挂画 ----------
export function WallArt({ width = 80, height = 60 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 80 60" overflow="visible">
      <rect x="0" y="0" width="80" height="60" fill="#92400e" />
      <rect x="3" y="3" width="74" height="54" fill="#fef3c7" />
      {/* 抽象图案 */}
      <circle cx="25" cy="20" r="8" fill="#f59e0b" />
      <path d="M 8 50 L 30 30 L 50 42 L 72 22 L 72 50 Z" fill="#f97316" />
      <path d="M 8 50 L 50 50 L 72 50 L 72 56 L 8 56 Z" fill="#15803d" />
    </svg>
  )
}

// ---------- 吊灯 ----------
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
      {/* 吊线 */}
      <line x1="25" y1="0" x2="25" y2="34" stroke="#27272a" strokeWidth="1.5" />
      {/* 灯罩 */}
      <path d="M 8 34 L 42 34 L 36 56 L 14 56 Z" fill="#1f2937" />
      <ellipse cx="25" cy="34" rx="17" ry="4" fill="#374151" />
      {/* 灯泡光 */}
      <ellipse cx="25" cy="60" rx="22" ry="14" fill={`url(#${g})`} />
      <circle cx="25" cy="56" r="4" fill="#fef3c7">
        <animate attributeName="opacity" values="0.85;1;0.85" dur="3s" repeatCount="indefinite" />
      </circle>
    </svg>
  )
}

// ---------- 散步小径（圆形地毯 + 盆栽） ----------
export function ZenSpot({ width = 130, height = 100 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 130 100" overflow="visible">
      {/* 圆形地毯 */}
      <ellipse cx="65" cy="78" rx="58" ry="14" fill="#86efac" opacity="0.3" />
      <ellipse cx="65" cy="78" rx="48" ry="11" fill="#22c55e" opacity="0.2" />
      <ellipse cx="65" cy="78" rx="36" ry="8" fill="#15803d" opacity="0.2" />
      {/* 小石头 */}
      <ellipse cx="20" cy="72" rx="6" ry="4" fill="#a8a29e" />
      <ellipse cx="108" cy="74" rx="5" ry="3" fill="#a8a29e" />
      <ellipse cx="32" cy="80" rx="4" ry="2.5" fill="#78716c" />
    </svg>
  )
}
