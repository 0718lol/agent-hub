import { PREVIEW_HTML } from './previewHtml'

const DEFAULT_PROMO_SUBJECT = '巧乐兹'

export function extractPromoSubject(text = '') {
  const match = String(text).match(/([^\s，。！？]{2,20}?)(?:宣传|海报|广告|落地页|页面|设计)/)
  if (!match) return DEFAULT_PROMO_SUBJECT
  return match[1]
    .replace(/^(这是|给我|帮我|请|麻烦|做|生成|设计|制作|来|整)(一张|一个|个)?/g, '')
    .replace(/^的+|的+$/g, '') || DEFAULT_PROMO_SUBJECT
}

export function buildPromoPreviewHtml(subject = DEFAULT_PROMO_SUBJECT) {
  const safeSubject = String(subject || DEFAULT_PROMO_SUBJECT).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]))
  return PREVIEW_HTML.promo.replaceAll(DEFAULT_PROMO_SUBJECT, safeSubject)
}
