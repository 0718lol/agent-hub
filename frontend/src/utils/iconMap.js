/**
 * Agent icon key → Lucide icon component mapping.
 * No emoji rendering. All icons are Lucide linear outline.
 */
import {
  Bot, ClipboardList, Palette, Code, Settings,
  FlaskConical, Rocket, Wrench, Terminal,
  Users, User
} from 'lucide-react'

const iconMap = {
  'agent_pm':       { icon: ClipboardList, color: '#f59e0b' },
  'agent_frontend': { icon: Code,           color: '#22d3ee' },
  'agent_backend':  { icon: Terminal,       color: '#6366f1' },
  'agent_tester':   { icon: FlaskConical,   color: '#8b5cf6' },
  'agent_devops':   { icon: Rocket,         color: '#f59e0b' },
  'agent_designer': { icon: Palette,        color: '#ec4899' },
  'agent_builder':  { icon: Wrench,         color: '#64748b' },
  'default':        { icon: Bot,            color: '#6366f1' },
  'group':          { icon: Users,          color: '#10b981' },
  'user':           { icon: User,           color: '#64748b' },
}

/**
 * @param {string} agentId - e.g. 'agent_frontend'
 * @returns {{ icon: React.Component, color: string }}
 */
export function getIconForAgent(agentId) {
  return iconMap[agentId] || iconMap['default']
}

/**
 * @param {string} iconKey - direct icon key
 * @returns {{ icon: React.Component, color: string }}
 */
export function getIconByKey(iconKey) {
  return iconMap[iconKey] || iconMap['default']
}

export default iconMap
