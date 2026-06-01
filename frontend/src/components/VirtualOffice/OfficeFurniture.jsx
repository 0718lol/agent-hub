import React, { useId } from 'react'

/**
 * OfficeFurniture — 3/4 等距视角家具库（Marvis 风）
 *
 * 风格：白色主调 + 浅灰阴影 + 看得到深度（桌腿/椅背/显示器支架）
 */

// ---------- 工位（桌子 + 椅子 + 显示器 一体）----------
export function Desk({ width = 180, height = 200, accent = '#6366f1' }) {
  const uid = useId().replace(/:/g, '')
  const gDesk = `dt-${uid}`
  const gMon = `mon-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 180 200" overflow="visible">
      <defs>
        <linearGradient id={gDesk} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="100%" stopColor="#e7e5e4" />
        </linearGradient>
        <linearGradient id={gMon} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
      </defs>
      {/* 地面阴影 */}
      <ellipse cx="90" cy="190" rx="80" ry="6" fill="rgba(0,0,0,0.12)" />

      {/* 显示器（最后面，靠墙）*/}
      <rect x="58" y="14" width="64" height="42" rx="3" fill={`url(#${gMon})`} />
      <rect x="62" y="18" width="56" height="34" rx="2" fill={accent} opacity="0.25" />
      {/* 屏幕代码行 */}
      <rect x="66" y="22" width="22" height="2" fill="#fafafa" opacity="0.85" />
      <rect x="66" y="27" width="36" height="2" fill="#fafafa" opacity="0.55" />
      <rect x="70" y="32" width="28" height="2" fill="#fafafa" opacity="0.45" />
      <rect x="66" y="37" width="40" height="2" fill="#fafafa" opacity="0.65" />
      <rect x="70" y="42" width="24" height="2" fill="#fafafa" opacity="0.4" />
      {/* 显示器支架 */}
      <rect x="86" y="56" width="8" height="10" fill="#52525b" />
      <ellipse cx="90" cy="68" rx="14" ry="3" fill="#3f3f46" />

      {/* 桌面（3/4 视角：上面 + 前面）*/}
      <path d="M 20 68 L 160 68 L 168 78 L 12 78 Z" fill={`url(#${gDesk})`} />
      <path d="M 12 78 L 168 78 L 168 88 L 12 88 Z" fill="#d6d3d1" />
      {/* 桌面物品 */}
      <rect x="50" y="73" width="44" height="6" rx="1" fill="#52525b" opacity="0.8" />
      <circle cx="120" cy="76" r="4" fill="#fafafa" stroke="#a16207" strokeWidth="1" />

      {/* 桌腿（前面两根）*/}
      <rect x="20" y="88" width="6" height="38" fill="#a8a29e" />
      <rect x="154" y="88" width="6" height="38" fill="#a8a29e" />

      {/* 椅子靠背（在桌子前）*/}
      <rect x="68" y="100" width="44" height="48" rx="6" fill="#27272a" />
      <rect x="70" y="102" width="40" height="40" rx="4" fill="#3f3f46" />

      {/* 椅子座位（被靠背遮一部分）*/}
      <ellipse cx="90" cy="155" rx="32" ry="8" fill="#27272a" />
      <ellipse cx="90" cy="153" rx="30" ry="6" fill="#52525b" />

      {/* 椅子升降柱 */}
      <rect x="86" y="155" width="8" height="18" fill="#27272a" />

      {/* 五星脚轮 */}
      <ellipse cx="90" cy="178" rx="36" ry="8" fill="rgba(0,0,0,0.18)" />
      <g fill="#27272a">
        <ellipse cx="62" cy="178" rx="6" ry="3" />
        <ellipse cx="118" cy="178" rx="6" ry="3" />
        <ellipse cx="78" cy="183" rx="5" ry="2.5" />
        <ellipse cx="102" cy="183" rx="5" ry="2.5" />
        <ellipse cx="90" cy="180" rx="5" ry="2.5" />
      </g>
    </svg>
  )
}

// ---------- 沙发（3 人，3/4 视角）----------
export function Sofa({ width = 240, height = 110 }) {
  const uid = useId().replace(/:/g, '')
  const g = `sofa-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 240 110" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#f5f5f4" />
          <stop offset="100%" stopColor="#d6d3d1" />
        </linearGradient>
      </defs>
      <ellipse cx="120" cy="104" rx="108" ry="5" fill="rgba(0,0,0,0.15)" />

      {/* 靠背（最高的部分） */}
      <path d="M 14 14 L 226 14 Q 232 14 232 22 L 232 50 L 8 50 L 8 22 Q 8 14 14 14 Z" fill={`url(#${g})`} />

      {/* 靠垫分隔 */}
      <line x1="80" y1="14" x2="80" y2="48" stroke="#d6d3d1" strokeWidth="2" />
      <line x1="160" y1="14" x2="160" y2="48" stroke="#d6d3d1" strokeWidth="2" />

      {/* 座位（前面） */}
      <path d="M 8 50 L 232 50 L 232 80 Q 232 86 226 86 L 14 86 Q 8 86 8 80 Z" fill="#e7e5e4" />

      {/* 扶手 */}
      <path d="M 0 30 L 14 22 L 14 86 L 0 86 Z" fill="#d6d3d1" />
      <path d="M 240 30 L 226 22 L 226 86 L 240 86 Z" fill="#d6d3d1" />

      {/* 腿 */}
      <rect x="14" y="86" width="6" height="10" fill="#78716c" />
      <rect x="220" y="86" width="6" height="10" fill="#78716c" />
    </svg>
  )
}

// ---------- 大屏电视 + 电视柜（3/4 视角）----------
export function TV({ width = 220, height = 170 }) {
  const uid = useId().replace(/:/g, '')
  const g = `tv-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 220 170" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#ec4899" />
        </linearGradient>
      </defs>
      <ellipse cx="110" cy="164" rx="86" ry="5" fill="rgba(0,0,0,0.18)" />

      {/* 电视屏幕（贴墙） */}
      <rect x="20" y="10" width="180" height="100" rx="4" fill="#0f172a" />
      <rect x="24" y="14" width="172" height="92" rx="2" fill={`url(#${g})`} opacity="0.9" />
      {/* 屏幕内容 */}
      <rect x="40" y="74" width="14" height="26" rx="2" fill="rgba(255,255,255,0.7)" />
      <rect x="62" y="60" width="14" height="40" rx="2" fill="rgba(255,255,255,0.75)" />
      <rect x="84" y="48" width="14" height="52" rx="2" fill="rgba(255,255,255,0.8)" />
      <rect x="106" y="56" width="14" height="44" rx="2" fill="rgba(255,255,255,0.7)" />
      <rect x="128" y="42" width="14" height="58" rx="2" fill="rgba(255,255,255,0.85)" />
      <polyline points="40,40 70,30 100,35 130,18 160,28 190,16" stroke="#fafafa" strokeWidth="2" fill="none" opacity="0.85" />

      {/* 电视柜（3/4 视角） */}
      <path d="M 30 116 L 190 116 L 196 124 L 24 124 Z" fill="#fafafa" stroke="#d6d3d1" strokeWidth="1" />
      <path d="M 24 124 L 196 124 L 196 152 L 24 152 Z" fill="#e7e5e4" />
      {/* 柜门 */}
      <line x1="110" y1="124" x2="110" y2="152" stroke="#a8a29e" strokeWidth="1" />
      <circle cx="100" cy="138" r="1.5" fill="#52525b" />
      <circle cx="120" cy="138" r="1.5" fill="#52525b" />
      {/* 柜腿 */}
      <rect x="28" y="152" width="4" height="8" fill="#78716c" />
      <rect x="188" y="152" width="4" height="8" fill="#78716c" />
    </svg>
  )
}

// ---------- 茶几 ----------
export function CoffeeTable({ width = 120, height = 70 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 120 70" overflow="visible">
      <ellipse cx="60" cy="64" rx="52" ry="4" fill="rgba(0,0,0,0.15)" />
      {/* 桌面 */}
      <path d="M 12 18 L 108 18 L 114 26 L 6 26 Z" fill="#fafafa" stroke="#d6d3d1" strokeWidth="1" />
      <path d="M 6 26 L 114 26 L 114 32 L 6 32 Z" fill="#d6d3d1" />
      {/* 桌上物品 */}
      <rect x="30" y="14" width="24" height="6" rx="1" fill="#dc2626" />
      <circle cx="80" cy="20" r="6" fill="#fef3c7" stroke="#a16207" strokeWidth="1" />
      {/* 桌腿 */}
      <rect x="14" y="32" width="4" height="26" fill="#a8a29e" />
      <rect x="102" y="32" width="4" height="26" fill="#a8a29e" />
    </svg>
  )
}

// ---------- 咖啡机（3/4 视角，可见前面 + 顶面） ----------
export function CoffeeMachine({ width = 90, height = 140 }) {
  const uid = useId().replace(/:/g, '')
  const g = `cm-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 90 140" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#3f3f46" />
          <stop offset="100%" stopColor="#27272a" />
        </linearGradient>
      </defs>
      <ellipse cx="45" cy="134" rx="32" ry="3" fill="rgba(0,0,0,0.2)" />
      {/* 顶面（3/4 视角） */}
      <path d="M 14 18 L 76 18 L 82 24 L 8 24 Z" fill="#52525b" />
      {/* 主体 */}
      <rect x="8" y="24" width="74" height="106" rx="4" fill={`url(#${g})`} />
      {/* 显示屏 */}
      <rect x="16" y="34" width="58" height="18" rx="2" fill="#0f172a" />
      <rect x="20" y="38" width="24" height="3" fill="#22c55e" />
      <rect x="20" y="44" width="18" height="2" fill="#22c55e" opacity="0.7" />
      {/* 出水口 */}
      <rect x="32" y="60" width="26" height="6" fill="#18181b" />
      <ellipse cx="45" cy="68" rx="8" ry="3" fill="#0f172a" />
      {/* 杯子 */}
      <path d="M 32 80 L 58 80 L 56 100 L 34 100 Z" fill="#fafafa" stroke="#d6d3d1" strokeWidth="1" />
      <ellipse cx="45" cy="80" rx="13" ry="2" fill="#92400e" />
      {/* 控制按钮 */}
      <circle cx="20" cy="115" r="4" fill="#dc2626" />
      <circle cx="34" cy="115" r="4" fill="#22c55e" />
      <circle cx="48" cy="115" r="4" fill="#3b82f6" />
      {/* 热气 */}
      <path d="M 38 30 Q 36 22 38 14 Q 40 10 38 4" stroke="rgba(255,255,255,0.4)" strokeWidth="2" fill="none" strokeLinecap="round">
        <animate attributeName="opacity" values="0.6;0.2;0.6" dur="2s" repeatCount="indefinite" />
      </path>
      <path d="M 52 30 Q 54 22 52 14 Q 50 10 52 4" stroke="rgba(255,255,255,0.4)" strokeWidth="2" fill="none" strokeLinecap="round">
        <animate attributeName="opacity" values="0.2;0.6;0.2" dur="2s" repeatCount="indefinite" />
      </path>
    </svg>
  )
}

// ---------- 跑步机（侧视，参考 Marvis 截图） ----------
export function Treadmill({ width = 180, height = 150 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 180 150" overflow="visible">
      <ellipse cx="90" cy="144" rx="78" ry="4" fill="rgba(0,0,0,0.2)" />

      {/* 跑带（侧视：长方形） */}
      <path d="M 20 100 L 160 100 L 170 116 L 10 116 Z" fill="#0f172a" />
      <path d="M 24 100 L 156 100 L 156 96 L 24 96 Z" fill="#1f2937" />
      {/* 跑带条纹 */}
      <line x1="40" y1="100" x2="60" y2="100" stroke="#52525b" strokeWidth="1.5" />
      <line x1="80" y1="100" x2="100" y2="100" stroke="#52525b" strokeWidth="1.5" />
      <line x1="120" y1="100" x2="140" y2="100" stroke="#52525b" strokeWidth="1.5" />

      {/* 跑带前轮 */}
      <ellipse cx="20" cy="100" rx="6" ry="6" fill="#1f2937" />
      <ellipse cx="160" cy="100" rx="6" ry="6" fill="#1f2937" />

      {/* 扶手立柱 */}
      <rect x="22" y="30" width="8" height="70" fill="#a8a29e" />
      <rect x="150" y="30" width="8" height="70" fill="#a8a29e" />

      {/* 控制台 */}
      <path d="M 14 14 L 166 14 L 170 24 L 10 24 Z" fill="#27272a" />
      <rect x="10" y="24" width="160" height="12" fill="#1f2937" />
      <rect x="18" y="18" width="144" height="14" rx="2" fill="#0f172a" />
      <text x="34" y="29" fill="#22c55e" fontSize="9" fontFamily="monospace" fontWeight="600">5.2 km</text>
      <text x="84" y="29" fill="#fde047" fontSize="9" fontFamily="monospace">12'30"</text>
      <text x="130" y="29" fill="#ef4444" fontSize="9" fontFamily="monospace">142</text>

      {/* 扶手 */}
      <rect x="14" y="38" width="152" height="4" rx="2" fill="#52525b" />
    </svg>
  )
}

// ---------- 盆栽（3/4 视角） ----------
export function Plant({ width = 70, height = 110 }) {
  const uid = useId().replace(/:/g, '')
  const g = `pot-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 70 110" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#a16207" />
          <stop offset="100%" stopColor="#713f12" />
        </linearGradient>
      </defs>
      <ellipse cx="35" cy="104" rx="22" ry="3" fill="rgba(0,0,0,0.2)" />
      {/* 花盆（3/4 视角：顶椭圆 + 梯形侧面） */}
      <ellipse cx="35" cy="68" rx="20" ry="5" fill={`url(#${g})`} />
      <path d="M 15 68 L 55 68 L 50 100 L 20 100 Z" fill={`url(#${g})`} />
      <ellipse cx="35" cy="100" rx="15" ry="3" fill="#5b2a05" />
      {/* 土壤 */}
      <ellipse cx="35" cy="68" rx="17" ry="3" fill="#3f1d05" />
      {/* 叶子 */}
      <ellipse cx="22" cy="42" rx="9" ry="24" fill="#16a34a" transform="rotate(-30 22 42)" />
      <ellipse cx="48" cy="42" rx="9" ry="24" fill="#15803d" transform="rotate(30 48 42)" />
      <ellipse cx="35" cy="30" rx="8" ry="28" fill="#22c55e" />
      <ellipse cx="28" cy="55" rx="6" ry="14" fill="#16a34a" transform="rotate(-20 28 55)" />
      <ellipse cx="42" cy="55" rx="6" ry="14" fill="#15803d" transform="rotate(20 42 55)" />
    </svg>
  )
}

// ---------- 落地窗 ----------
export function Window({ width = 180, height = 130 }) {
  const uid = useId().replace(/:/g, '')
  const g = `sky-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 180 130" overflow="visible">
      <defs>
        <linearGradient id={g} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#7dd3fc" />
          <stop offset="100%" stopColor="#bae6fd" />
        </linearGradient>
      </defs>
      {/* 窗框 */}
      <rect x="0" y="0" width="180" height="130" rx="4" fill="#a8a29e" />
      {/* 玻璃 */}
      <rect x="6" y="6" width="168" height="118" fill={`url(#${g})`} />
      {/* 十字格 */}
      <rect x="86" y="6" width="4" height="118" fill="#a8a29e" />
      <rect x="6" y="62" width="168" height="4" fill="#a8a29e" />
      {/* 远景 */}
      <circle cx="138" cy="32" r="11" fill="#fef3c7" opacity="0.85" />
      <ellipse cx="40" cy="36" rx="18" ry="6" fill="rgba(255,255,255,0.75)" />
      <ellipse cx="48" cy="32" rx="10" ry="4" fill="rgba(255,255,255,0.75)" />
      {/* 楼宇 */}
      <rect x="10" y="80" width="22" height="40" fill="rgba(100,116,139,0.4)" />
      <rect x="38" y="68" width="32" height="52" fill="rgba(100,116,139,0.4)" />
      <rect x="100" y="74" width="26" height="46" fill="rgba(100,116,139,0.4)" />
      <rect x="132" y="64" width="24" height="56" fill="rgba(100,116,139,0.4)" />
    </svg>
  )
}

// ---------- 白板 ----------
export function Whiteboard({ width = 160, height = 110 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 160 110" overflow="visible">
      <rect x="0" y="0" width="160" height="110" rx="3" fill="#a8a29e" />
      <rect x="4" y="4" width="152" height="102" fill="#fafafa" />
      {/* 流程图 */}
      <rect x="16" y="16" width="34" height="20" rx="2" fill="#fef3c7" stroke="#f59e0b" strokeWidth="1.5" />
      <rect x="62" y="16" width="34" height="20" rx="2" fill="#dbeafe" stroke="#3b82f6" strokeWidth="1.5" />
      <rect x="108" y="16" width="34" height="20" rx="2" fill="#dcfce7" stroke="#22c55e" strokeWidth="1.5" />
      <line x1="50" y1="26" x2="60" y2="26" stroke="#52525b" strokeWidth="1.5" />
      <line x1="96" y1="26" x2="106" y2="26" stroke="#52525b" strokeWidth="1.5" />
      <line x1="16" y1="52" x2="86" y2="52" stroke="#3b82f6" strokeWidth="1.5" />
      <line x1="16" y1="62" x2="108" y2="62" stroke="#52525b" strokeWidth="1" />
      <line x1="16" y1="72" x2="80" y2="72" stroke="#52525b" strokeWidth="1" />
      <circle cx="116" cy="70" r="14" fill="none" stroke="#ef4444" strokeWidth="2" />
      <text x="108" y="74" fontSize="10" fill="#ef4444" fontWeight="700">PM</text>
    </svg>
  )
}

// ---------- 装饰挂画 ----------
export function WallArt({ width = 90, height = 70 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 90 70" overflow="visible">
      <rect x="0" y="0" width="90" height="70" fill="#78350f" />
      <rect x="3" y="3" width="84" height="64" fill="#fef3c7" />
      <circle cx="28" cy="22" r="9" fill="#f59e0b" />
      <path d="M 8 58 L 32 32 L 54 46 L 80 24 L 80 58 Z" fill="#f97316" />
      <path d="M 8 58 L 80 58 L 80 64 L 8 64 Z" fill="#15803d" />
    </svg>
  )
}

// ---------- 吊灯（侧视：吊线 + 灯罩 + 光晕） ----------
export function PendantLamp({ width = 60, height = 100 }) {
  const uid = useId().replace(/:/g, '')
  const g = `lamp-${uid}`
  return (
    <svg width={width} height={height} viewBox="0 0 60 100" overflow="visible">
      <defs>
        <radialGradient id={g}>
          <stop offset="0%" stopColor="#fef3c7" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#fef3c7" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* 吊线 */}
      <line x1="30" y1="0" x2="30" y2="40" stroke="#27272a" strokeWidth="1.5" />
      {/* 灯罩 */}
      <path d="M 10 40 L 50 40 L 44 64 L 16 64 Z" fill="#27272a" />
      <ellipse cx="30" cy="40" rx="20" ry="4" fill="#3f3f46" />
      <ellipse cx="30" cy="64" rx="14" ry="3" fill="#1f2937" />
      {/* 灯泡光晕 */}
      <ellipse cx="30" cy="72" rx="26" ry="16" fill={`url(#${g})`} />
      <circle cx="30" cy="66" r="4" fill="#fef3c7">
        <animate attributeName="opacity" values="0.85;1;0.85" dur="3s" repeatCount="indefinite" />
      </circle>
    </svg>
  )
}

// ---------- 散步区/瑜伽垫（3/4 视角） ----------
export function ZenSpot({ width = 150, height = 110 }) {
  return (
    <svg width={width} height={height} viewBox="0 0 150 110" overflow="visible">
      {/* 瑜伽垫（3/4 视角） */}
      <path d="M 20 60 L 130 60 L 140 76 L 10 76 Z" fill="#86efac" opacity="0.4" />
      <path d="M 10 76 L 140 76 L 140 86 L 10 86 Z" fill="#22c55e" opacity="0.3" />
      {/* 圆环装饰 */}
      <ellipse cx="75" cy="68" rx="44" ry="6" fill="#15803d" opacity="0.25" />
      {/* 小石头 */}
      <ellipse cx="30" cy="70" rx="5" ry="3" fill="#a8a29e" />
      <ellipse cx="120" cy="72" rx="4" ry="2.5" fill="#a8a29e" />
      <ellipse cx="55" cy="78" rx="3" ry="2" fill="#78716c" />
    </svg>
  )
}
