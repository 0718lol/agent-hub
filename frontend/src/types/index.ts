/**
 * TypeScript type definitions for AgentHub frontend.
 * Provides type safety for Zustand stores, WebSocket messages, and API responses.
 */

// ============================================================
// Core domain types
// ============================================================

/** A single chat message */
export interface Message {
  id: string
  sender: string
  content: MessageContent
  streaming?: boolean
  timestamp: string
}

/** Message content — can be simple text or structured with code/metadata */
export interface MessageContent {
  text: string
  language?: string
  code?: string
  preview?: string
  tool_call?: ToolCallInfo
  tool_result?: ToolResultInfo
}

export interface ToolCallInfo {
  name: string
  args: Record<string, unknown>
}

export interface ToolResultInfo {
  name: string
  result: unknown
  error?: string
}

/** A conversation (single-agent or group) */
export interface Conversation {
  id: string
  type: 'single' | 'group'
  name: string
  avatar: string | null
  role?: string
  agentId?: string
  agents?: string[]
  messages: Message[]
  pinned: boolean
  unread: boolean
  archived?: boolean
  updatedAt: number
  preview?: string
}

// ============================================================
// Chat store types
// ============================================================

export interface ChatStoreState {
  conversations: Conversation[]
  activeConversationId: string
  typingAgents: Record<string, Set<string>>
  thinkingAgents: Record<string, Record<string, string>>
  generatingConvs: Set<string>
  allRead: Record<string, boolean>
  pinnedMessages: Record<string, string[]>
}

export interface ChatStoreActions {
  setActiveConversation: (id: string) => void
  togglePin: (conversationId: string) => void
  archiveConversation: (conversationId: string) => void
  reorderConversations: (fromIndex: number, toIndex: number) => void
  togglePinMessage: (conversationId: string, messageId: string) => void
  setTyping: (conversationId: string, agentId: string, isTyping: boolean) => void
  setThinking: (conversationId: string, agentId: string, text: string) => void
  setGenerating: (conversationId: string, isGenerating: boolean) => void
  markRead: (conversationId: string) => void
  markSent: (conversationId: string) => void
  loadMessages: (conversationId: string) => Promise<void>
  addMessage: (conversationId: string, message: Partial<Message> & { sender: string; content: MessageContent }) => void
  clearMessages: (conversationId: string) => void
  updateLastAgentMessage: (conversationId: string, senderId: string, text: string, streaming: boolean) => void
  addConversation: (conv: Partial<Conversation> & { id: string; name: string; type: Conversation['type'] }) => void
  removeConversation: (convId: string) => void
  getActiveConversation: () => Conversation | undefined
}

export type ChatStore = ChatStoreState & ChatStoreActions

// ============================================================
// WebSocket message types
// ============================================================

/** Client → Server messages */
export type ClientWSMessage =
  | { type: 'message'; sender: string; content: MessageContent }
  | { type: 'stop' }
  | { type: 'read' }
  | { type: 'harness_verdict'; verdict: string; conversation_id: string }

/** Server → Client messages */
export type ServerWSMessage =
  | { type: 'message'; conversation_id: string; sender: string; content: MessageContent; stream: boolean }
  | { type: 'typing'; conversation_id: string; agent_id: string; is_typing: boolean }
  | { type: 'thinking'; conversation_id: string; agent_id: string; text: string }
  | { type: 'code'; conversation_id: string; sender: string; content: MessageContent }
  | { type: 'preview'; conversation_id: string; html: string }
  | { type: 'generating'; conversation_id: string; is_generating: boolean }
  | { type: 'task_status'; conversation_id: string; agent_id: string; status: 'doing' | 'done' | 'error' }
  | { type: 'deploy_status'; conversation_id: string; status: string; output: string }
  | { type: 'quality_report'; conversation_id: string; agent_id: string; report: QualityReport }
  | { type: 'agent_created'; agent: AgentInfo }
  | { type: 'agent_deleted'; agent_id: string }
  | { type: 'read'; conversation_id: string; reader: string }
  | { type: 'candidates_report'; conversation_id: string; agent_id: string; candidates: CandidateSummary[] }

export interface QualityReport {
  score: number
  passed: boolean
  issues: string[]
  suggestions: string[]
}

export interface CandidateSummary {
  index: number
  score: number
  preview: string
}

export interface AgentInfo {
  agent_id: string
  name: string
  avatar: string
  role: string
  style: string
  description?: string
}

// ============================================================
// API response types
// ============================================================

export interface HealthResponse {
  status: string
  agents: string[]
}

export interface ConversationListResponse {
  conversations: Conversation[]
}

export interface MessageListResponse {
  messages: Message[]
}

export interface UploadResponse {
  status: 'uploaded'
  original_name: string
  stored_name: string
  url: string
  content_type: string
  size: number
  is_image: boolean
}

export interface QualityGateSettings {
  enabled: boolean
  max_retries: number
  use_llm_judge: boolean
  best_of_n: number
}

export interface BenchmarkCase {
  id: string
  name: string
  category: string
}

export interface BenchmarkStatus {
  status: 'idle' | 'running' | 'completed'
  results?: BenchmarkResult[]
}

export interface BenchmarkResult {
  case_id: string
  score: number
  duration_ms: number
  passed: boolean
}

// ============================================================
// Canvas store types
// ============================================================

export interface DAGNode {
  id: string
  label: string
  type: 'agent' | 'tool' | 'output'
  x: number
  y: number
  status?: 'idle' | 'doing' | 'done' | 'error'
}

export interface DAGEdge {
  from: string
  to: string
  label?: string
}

export interface TaskItem {
  id: string
  title: string
  agent: string
  status: 'todo' | 'doing' | 'done'
  description?: string
}

// ============================================================
// Theme store types
// ============================================================

export type ThemeName = 'tech-dark' | 'vibrant'

export interface ThemeStoreState {
  theme: ThemeName
}

export interface ThemeStoreActions {
  setTheme: (theme: ThemeName) => void
  toggleTheme: () => void
}

export type ThemeStore = ThemeStoreState & ThemeStoreActions
