import { describe, it, expect } from 'vitest'
import { normalizePreviewHtml } from './WebPreview'

describe('normalizePreviewHtml', () => {
  it('adds safety guard for poster-like layouts', () => {
    const input = `<!DOCTYPE html><html><head><title>优雅自信光芒女性海报</title></head><body><div class="poster"><div class="black-frame"></div><div class="headline"><h1>她的光芒</h1></div></div></body></html>`
    const output = normalizePreviewHtml(input)

    expect(output).toContain('agenthub-preview-guard')
    expect(output).toContain('.bottom,.footer,.caption,.copy,.content,.text,.title,.title-wrap')
    expect(output).toContain('overflow:visible!important')
    expect(output).toContain('.deco,.glow,.spot,.orb,.blob,.ring,.shade,.overlay,.mask')
  })

  it('removes heavy dark poster layers for music posters', () => {
    const input = `<!DOCTYPE html><html><head><title>蔡徐坤 · 音乐节海报</title></head><body><div class="poster"><div class="deco"></div><div class="stage"></div></div></body></html>`
    const output = normalizePreviewHtml(input)

    expect(output).toContain('agenthub-preview-guard')
    expect(output).toContain('.deco,.glow,.spot,.orb,.blob,.ring,.shade,.overlay,.mask')
    expect(output).toContain('box-shadow:none!important')
  })
})
