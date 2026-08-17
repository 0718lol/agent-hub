import { create } from 'zustand'

const STORAGE_KEY = 'agent-hub-tabs-v2'
const MAX_TABS = 8

const DEFAULT_TAB = { id: 'tab_conv_pm', convId: 'conv_pm', title: 'PM 小助手', agentId: 'agent_pm' }

function tenantStorageKey(ownerId) {
  return `${STORAGE_KEY}:${ownerId}`
}

function loadSavedTabs(ownerId) {
  try {
    const key = tenantStorageKey(ownerId)
    let raw = localStorage.getItem(key)
    if (!raw) {
      raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        localStorage.setItem(key, raw)
        localStorage.removeItem(STORAGE_KEY)
      }
    }
    if (raw) {
      const data = JSON.parse(raw)
      if (data.openTabs?.length > 0) return data
    }
  } catch (_e) { /* ignore parse errors */ }
  return null
}

const initialLastActive = new Map([[DEFAULT_TAB.id, Date.now()]])

export const useTabStore = create((set, get) => ({
  openTabs: [DEFAULT_TAB],
  activeTabId: DEFAULT_TAB.id,
  lastActive: initialLastActive,
  _ownerId: null,
  _synced: false,

  setOwner: (ownerId) => {
    if (!ownerId || get()._ownerId === ownerId) return
    const saved = loadSavedTabs(ownerId)
    const openTabs = saved?.openTabs?.length ? saved.openTabs : [DEFAULT_TAB]
    const activeTabId = openTabs.some((tab) => tab.id === saved?.activeTabId)
      ? saved.activeTabId
      : openTabs[0].id
    const lastActive = new Map(openTabs.map((tab) => [tab.id, Date.now()]))
    set({ openTabs, activeTabId, lastActive, _ownerId: ownerId, _synced: false })
  },

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

  /**
   * 对话加载后调用。用有效 convId 列表清理幽灵标签。
   * 幂等：只在首次调用时执行清理，之后的调用直接跳过。
   */
  syncWithConversations: (validConvIds) => {
    const state = get()
    if (state._synced) return

    const validSet = new Set(validConvIds)
    validSet.add('conv_pm')

    // 只保留 convId 有效且不重复的标签
    const seen = new Set()
    const cleanTabs = []
    for (const tab of state.openTabs) {
      if (validSet.has(tab.convId) && !seen.has(tab.convId)) {
        seen.add(tab.convId)
        cleanTabs.push(tab)
      }
    }

    if (!seen.has('conv_pm')) {
      cleanTabs.unshift(DEFAULT_TAB)
    }

    let activeTabId = state.activeTabId
    if (!cleanTabs.find((t) => t.id === activeTabId)) {
      activeTabId = cleanTabs[0].id
    }

    const newLastActive = new Map()
    cleanTabs.forEach((t) => newLastActive.set(t.id, state.lastActive.get(t.id) || Date.now()))

    set({ openTabs: cleanTabs, activeTabId, lastActive: newLastActive, _synced: true })
    get()._persist()
  },

  _persist: () => {
    try {
      const { openTabs, activeTabId, _ownerId } = get()
      if (!_ownerId) return
      localStorage.setItem(tenantStorageKey(_ownerId), JSON.stringify({ openTabs, activeTabId }))
    } catch (_e) { /* ignore storage errors */ }
  },
}))
