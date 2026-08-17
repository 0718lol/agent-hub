import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useAgentStore } from './agentStore'

describe('agentStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useAgentStore.setState({
      agents: [
        { agent_id: 'agent_pm', name: 'PM 小助手', role: '产品经理', status: 'idle' },
        { agent_id: 'agent_frontend', name: '前端工程师', role: '前端开发', status: 'idle' },
      ],
      deletedPresetIds: [],
      _ownerId: null,
    })
    vi.restoreAllMocks()
  })

  // ---------- setAgentStatus ----------

  it('should set agent status', () => {
    useAgentStore.getState().setAgentStatus('agent_pm', 'running')
    const agent = useAgentStore.getState().agents.find(a => a.agent_id === 'agent_pm')
    expect(agent.status).toBe('running')
  })

  it('should not affect other agents when setting status', () => {
    useAgentStore.getState().setAgentStatus('agent_pm', 'running')
    const frontend = useAgentStore.getState().agents.find(a => a.agent_id === 'agent_frontend')
    expect(frontend.status).toBe('idle')
  })

  // ---------- getAgent ----------

  it('should return agent by id', () => {
    const agent = useAgentStore.getState().getAgent('agent_pm')
    expect(agent).toBeDefined()
    expect(agent.name).toBe('PM 小助手')
  })

  it('should return undefined for non-existent agent', () => {
    const agent = useAgentStore.getState().getAgent('agent_nonexistent')
    expect(agent).toBeUndefined()
  })

  // ---------- addCustomAgent ----------

  it('should add custom agent to agents list', () => {
    const agent = { agent_id: 'agent_custom_new', name: 'Custom Agent', role: 'Custom Role', custom: true }
    useAgentStore.getState().addCustomAgent(agent)
    const added = useAgentStore.getState().agents.find(a => a.agent_id === 'agent_custom_new')
    expect(added).toBeDefined()
    expect(added.name).toBe('Custom Agent')
    expect(added.status).toBe('idle') // should be set to idle by addCustomAgent
  })

  it('should preserve existing agents when adding custom agent', () => {
    const beforeCount = useAgentStore.getState().agents.length
    useAgentStore.getState().addCustomAgent({ agent_id: 'agent_custom_001', name: 'Test' })
    expect(useAgentStore.getState().agents.length).toBe(beforeCount + 1)
    expect(useAgentStore.getState().agents.find(a => a.agent_id === 'agent_pm')).toBeDefined()
  })

  // ---------- loadCustomAgents ----------

  it('should load custom agents from API and merge with existing', async () => {
    const mockAgents = [
      { agent_id: 'agent_custom_001', name: 'Custom Agent 1' },
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockAgents,
    })
    await useAgentStore.getState().loadCustomAgents()
    const state = useAgentStore.getState()
    expect(state.agents.find(a => a.agent_id === 'agent_custom_001')).toBeDefined()
    // Original agents should still be present
    expect(state.agents.find(a => a.agent_id === 'agent_pm')).toBeDefined()
  })

  it('should not add duplicate agents from API', async () => {
    const mockAgents = [
      { agent_id: 'agent_pm', name: 'PM Duplicate' }, // already exists
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockAgents,
    })
    await useAgentStore.getState().loadCustomAgents()
    const pmAgents = useAgentStore.getState().agents.filter(a => a.agent_id === 'agent_pm')
    expect(pmAgents.length).toBe(1)
    expect(pmAgents[0].name).toBe('PM 小助手') // original name preserved
  })

  it('should handle fetch error gracefully', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 500,
    })
    const beforeAgents = useAgentStore.getState().agents
    await useAgentStore.getState().loadCustomAgents()
    // Should not crash, agents should remain unchanged
    expect(useAgentStore.getState().agents).toEqual(beforeAgents)
  })

  it('should handle network error gracefully', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new Error('Network error'))
    const beforeAgents = useAgentStore.getState().agents
    await useAgentStore.getState().loadCustomAgents()
    expect(useAgentStore.getState().agents).toEqual(beforeAgents)
  })

  // ---------- removeAgent (custom) ----------

  it('should remove custom agent from list', async () => {
    useAgentStore.getState().addCustomAgent({ agent_id: 'agent_imported_remove_me', name: 'ToRemove', custom: true })
    expect(useAgentStore.getState().agents.find(a => a.agent_id === 'agent_imported_remove_me')).toBeDefined()
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({ ok: true })
    await useAgentStore.getState().removeAgent('agent_imported_remove_me')
    expect(useAgentStore.getState().agents.find(a => a.agent_id === 'agent_imported_remove_me')).toBeUndefined()
  })

  it('should keep custom agent when backend deletion fails', async () => {
    useAgentStore.getState().addCustomAgent({ agent_id: 'imported-agent', name: 'KeepMe', custom: true })
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({ ok: false })
    expect(await useAgentStore.getState().removeAgent('imported-agent')).toBe(false)
    expect(useAgentStore.getState().agents.find(a => a.agent_id === 'imported-agent')).toBeDefined()
  })

  // ---------- removeAgent (preset) ----------

  it('should mark preset agent as deleted without removing from list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({ ok: true })
    // Mock localStorage
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
    await useAgentStore.getState().removeAgent('agent_pm')
    expect(useAgentStore.getState().deletedPresetIds).toContain('agent_pm')
    setItemSpy.mockRestore()
  })

  it('should isolate deleted presets by tenant', () => {
    localStorage.setItem('agent-hub-deleted-presets:tenant-a', JSON.stringify(['agent_pm']))
    localStorage.setItem('agent-hub-deleted-presets:tenant-b', JSON.stringify(['agent_frontend']))

    useAgentStore.getState().setOwner('tenant-a')
    expect(useAgentStore.getState().deletedPresetIds).toEqual(['agent_pm'])
    useAgentStore.getState().setOwner('tenant-b')
    expect(useAgentStore.getState().deletedPresetIds).toEqual(['agent_frontend'])
  })
})
