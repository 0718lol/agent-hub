import { describe, expect, it } from 'vitest'
import { buildPromoPreviewHtml, extractPromoSubject } from './promoPreview'

describe('promoPreview', () => {
  it('builds subject-specific promo preview html', () => {
    const subject = extractPromoSubject('这是马龙打乒乓球的海报原型 [mockup:promo]')
    const html = buildPromoPreviewHtml(subject)

    expect(subject).toBe('马龙打乒乓球')
    expect(html).toContain('马龙打乒乓球')
    expect(html).not.toContain('巧乐兹')
  })
})
