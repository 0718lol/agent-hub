import { create } from 'zustand'

const STORAGE_KEY = 'agent-hub-tabs'
const MAX_TABS = 8

function loadTabs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const data = JSON.parse(raw)
      if (data.openTabs?.length > 0) return data
    }
  } catch {}
  return null
}

const DEFAULT_TAB = { id: 'tab_conv_pm', convId: 'conv_pm', title: 'PM 小助手', agentId: 'agent_pm' }
const saved = loadTabs()

// lastActive: Map<tabId, timestamp> — 不存 localStorage，每次启动重置
const initialLastActive = new Map()
if (saved?.openTabs) {
  saved.openTabs.forEach((t) => initialLastActive.set(t.id, Date.now()))
} else {
  initialLastActive.set(DEFAULT_TAB.id, Date.now())
}

export const useTabStore = create((set, get) => ({
  openTabs: saved?.openTabs || [DEFAULT_TAB],
  activeTabId: saved?.activeTabId || 'tab_conv_pm',
  lastActive: initialLastActive,

  openTab: (convId, title, agentId) => {
    const tabId = `tab_${convId}`
    const state = get()
    const existing = state.openTabs.find((t) => t.id === tabId)
    if (existing) {
      const newLastActive = new Map(state.lastActive)
      newLastActive.set(tabId, Date.now())
      set({ activeTabId: tabId, lastActive: newLastActive })
    } else {
      let openTabs = state.openTabs
      const newLastActive = new Map(state.lastActive)
      // 超过最大标签数，关闭最久未活跃的标签
      if (openTabs.length >= MAX_TABS) {
        let oldestId = null
        let oldestTime = Infinity
        for (const [id, ts] of newLastActive) {
          if (id !== state.activeTabId && ts < oldestTime) {
            oldestTime = ts
            oldestId = id
          }
        }
        if (oldestId) {
          openTabs = openTabs.filter((t) => t.id !== oldestId)
          newLastActive.delete(oldestId)
        }
      }
      const newTab = { id: tabId, convId, title: title || convId, agentId: agentId || null }
      newLastActive.set(tabId, Date.now())
      set({ openTabs: [...openTabs, newTab], activeTabId: tabId, lastActive: newLastActive })
    }
    get()._persist()
  },

  closeTab: (tabId) => {
    const state = get()
    const idx = state.openTabs.findIndex((t) => t.id === tabId)
    if (idx < 0) return

    const remaining = state.openTabs.filter((t) => t.id !== tabId)
    const newLastActive = new Map(state.lastActive)
    newLastActive.delete(tabId)

    if (remaining.length === 0) {
      newLastActive.set(DEFAULT_TAB.id, Date.now())
      set({ openTabs: [DEFAULT_TAB], activeTabId: DEFAULT_TAB.id, lastActive: newLastActive })
    } else {
      let newActive = state.activeTabId
      if (state.activeTabId === tabId) {
        const nextIdx = Math.min(idx, remaining.length - 1)
        newActive = remaining[nextIdx].id
      }
      newLastActive.set(newActive, Date.now())
      set({ openTabs: remaining, activeTabId: newActive, lastActive: newLastActive })
    }
    get()._persist()
  },

  setActiveTab: (tabId) => {
    const state = get()
    const newLastActive = new Map(state.lastActive)
    newLastActive.set(tabId, Date.now())
    set({ activeTabId: tabId, lastActive: newLastActive })
    get()._persist()
  },

  reorderTabs: (fromIndex, toIndex) => {
    set((state) => {
      const list = [...state.openTabs]
      const [moved] = list.splice(fromIndex, 1)
      list.splice(toIndex, 0, moved)
      return { openTabs: list }
    })
    get()._persist()
  },

  updateTabTitle: (convId, title) => {
    const tabId = `tab_${convId}`
    set((state) => ({
      openTabs: state.openTabs.map((t) => t.id === tabId ? { ...t, title } : t),
    }))
    get()._persist()
  },

  _persist: () => {
    try {
      const { openTabs, activeTabId } = get()
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ openTabs, activeTabId }))
    } catch {}
  },
}))
