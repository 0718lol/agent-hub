import { beforeEach, describe, expect, it } from 'vitest'
import { useTabStore } from './tabStore'

describe('tabStore tenant persistence', () => {
  beforeEach(() => {
    localStorage.clear()
    useTabStore.setState({
      openTabs: [{ id: 'tab_conv_pm', convId: 'conv_pm', title: 'PM 小助手', agentId: 'agent_pm' }],
      activeTabId: 'tab_conv_pm',
      lastActive: new Map([['tab_conv_pm', Date.now()]]),
      _ownerId: null,
      _synced: false,
    })
  })

  it('loads independent tabs when accounts switch in one browser', () => {
    localStorage.setItem('agent-hub-tabs-v2:tenant-a', JSON.stringify({
      openTabs: [{ id: 'tab_conv_a', convId: 'conv_a', title: 'A' }],
      activeTabId: 'tab_conv_a',
    }))
    localStorage.setItem('agent-hub-tabs-v2:tenant-b', JSON.stringify({
      openTabs: [{ id: 'tab_conv_b', convId: 'conv_b', title: 'B' }],
      activeTabId: 'tab_conv_b',
    }))

    useTabStore.getState().setOwner('tenant-a')
    expect(useTabStore.getState().activeTabId).toBe('tab_conv_a')
    useTabStore.getState().setOwner('tenant-b')
    expect(useTabStore.getState().activeTabId).toBe('tab_conv_b')
    expect(useTabStore.getState().openTabs.map((tab) => tab.convId)).toEqual(['conv_b'])
  })

  it('migrates legacy tabs to the first authenticated tenant once', () => {
    localStorage.setItem('agent-hub-tabs-v2', JSON.stringify({
      openTabs: [{ id: 'tab_conv_legacy', convId: 'conv_legacy', title: 'Legacy' }],
      activeTabId: 'tab_conv_legacy',
    }))

    useTabStore.getState().setOwner('tenant-a')
    expect(useTabStore.getState().activeTabId).toBe('tab_conv_legacy')
    expect(localStorage.getItem('agent-hub-tabs-v2')).toBeNull()
    expect(localStorage.getItem('agent-hub-tabs-v2:tenant-a')).not.toBeNull()
  })
})
