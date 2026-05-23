/**
 * Emoji → Lucide SVG icon mapping.
 * Data stores still use emoji strings. This utility renders them as crisp SVG icons.
 */
import {
  Bot, User, Settings, MessageSquare, Send, Rocket, Target, Ruler,
  CheckCircle, AlertTriangle, Check, ClipboardList, Palette,
  Code, FlaskConical, Wrench, Users, Terminal, FileText,
  Sparkles, Zap
} from 'lucide-react'

const emojiMap = {
  '🤖': { icon: Bot, color: '#6366f1' },
  '👤': { icon: User, color: '#64748b' },
  '⚙️': { icon: Settings, color: '#64748b' },
  '💬': { icon: MessageSquare, color: '#6366f1' },
  '➤': { icon: Send, color: 'currentColor' },
  '🚀': { icon: Rocket, color: '#f59e0b' },
  '🎯': { icon: Target, color: '#ef4444' },
  '📐': { icon: Ruler, color: '#6366f1' },
  '✅': { icon: CheckCircle, color: '#10b981' },
  '⚠️': { icon: AlertTriangle, color: '#f59e0b' },
  '✓': { icon: Check, color: 'currentColor' },
  '✓✓': { icon: Check, color: 'currentColor' },
  '📋': { icon: ClipboardList, color: '#f59e0b' },
  '🎨': { icon: Palette, color: '#ec4899' },
  '🧪': { icon: FlaskConical, color: '#8b5cf6' },
  '🔧': { icon: Wrench, color: '#64748b' },
  '💻': { icon: Code, color: '#22d3ee' },
  '👥': { icon: Users, color: '#10b981' },
  '🖥': { icon: Terminal, color: '#22d3ee' },
  '📄': { icon: FileText, color: '#64748b' },
  '✨': { icon: Sparkles, color: '#fbbf24' },
  '⚡': { icon: Zap, color: '#f59e0b' },
}

const fallback = { icon: Bot, color: '#6366f1' }

/**
 * Get the Lucide icon component and color for a given emoji.
 * @param {string} emoji - The emoji string from store data
 * @returns {{ icon: React.Component, color: string }}
 */
export function getIconForEmoji(emoji) {
  return emojiMap[emoji] || fallback
}

export default emojiMap
