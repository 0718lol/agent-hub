/**
 * AgentCharacter 动作枚举 — 桌宠和虚拟办公室共享
 *
 * 在 AgentCharacter.css 里每个 action 对应一组 keyframes
 * 添加新 action 时：
 *   1. 在这里加常量
 *   2. 在 AgentCharacter.css 加 .ac-{action} 样式
 *   3. 在 useAgentAction 决定何时切换
 */
export const AGENT_ACTIONS = Object.freeze({
  IDLE: 'idle',       // 默认：呼吸 + 偶尔眨眼
  WORK: 'work',       // 工作中：双臂敲键盘
  TALK: 'talk',       // 说话中：嘴巴张合 + 头点动
  SLEEP: 'sleep',     // 休息：闭眼 + Zz
  WALK: 'walk',       // 移动中：左右轻摆
  COFFEE: 'coffee',   // 喝咖啡（VirtualOffice）
  GYM: 'gym',         // 健身（VirtualOffice）
})

export const ALL_ACTIONS = Object.values(AGENT_ACTIONS)

export function isValidAction(action) {
  return ALL_ACTIONS.includes(action)
}

/**
 * 角色形象槽位 — 由调用方注入颜色 / 模型 / 头像
 * 桌宠用单个，VirtualOffice 用多个
 */
export const DEFAULT_THEME_COLOR = 'var(--accent, #6366f1)'
