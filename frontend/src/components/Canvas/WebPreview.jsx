import React, { useRef, useCallback } from 'react'
import { useCanvasStore } from '../../stores/canvasStore'
import { PREVIEW_HTML } from './previewHtml'

export function normalizePreviewHtml(html) {
  const source = String(html || '')
  if (!source) return source
  const isPosterLike = /海报|宣传|poster|slogan|优雅|自信|光芒|女性|舞台|蔡徐坤|马龙|张继科|一球定乾坤/i.test(source)
  if (!isPosterLike && !source.includes('class="slogan"') && !source.includes("class='slogan'")) return source

  const guardCss = `
<style id="agenthub-preview-guard">
html,body{min-height:100%;overflow:auto!important}
.poster,.canvas,.stage,.hero,.wrap,.container,.card,.visual{
  overflow:visible!important;
}
.poster{
  box-shadow:none!important;
  outline:none!important;
}
.poster,.frame,.border,.shell,.screen{
  border-color:rgba(255,255,255,.18)!important;
}
.bottom,.footer,.caption,.copy,.content,.text,.title,.title-wrap{
  position:relative!important;
  z-index:20!important;
}
.bottom{padding:0 24px 24px!important}
.slogan{
  display:block!important;
  max-width:calc(100% - 48px)!important;
  margin:0 auto!important;
  padding:4px 0!important;
  font-size:clamp(18px,3vw,28px)!important;
  line-height:1.25!important;
  letter-spacing:0!important;
  white-space:normal!important;
  overflow-wrap:anywhere;
  word-break:keep-all!important;
  overflow:visible!important;
}
.info,.meta,.tags{flex-wrap:wrap!important}
.deco,.glow,.spot,.orb,.blob,.ring,.shade,.overlay,.mask,[class*="borderGlow"],[class*="black"]{
  pointer-events:none!important;
  opacity:.16!important;
}
.stage::before,.stage::after,.hero::before,.hero::after,.poster::before,.poster::after{
  pointer-events:none!important;
  z-index:0!important;
}
.player svg,.hero svg,.visual svg{filter:none!important}
.top,.hero,.bottom,.stage,.main,.headline{z-index:10!important}
.top,.hero,.bottom,.headline,.copy{text-shadow:none!important}
.top h1,.title-wrap h1,.name,.fest,.sub,.year,.champion,.badge,.slogan,.headline,.copy{
  text-shadow:none!important;
  overflow:visible!important;
}
</style>`

  if (source.includes('</head>')) {
    return source.replace('</head>', `${guardCss}</head>`)
  }
  return `${source}${guardCss}`
}

export default function WebPreview() {
  const previewHtml = useCanvasStore((s) => s.previewHtml)
  const html = normalizePreviewHtml(previewHtml || PREVIEW_HTML.todo)
  const iframeRef = useRef(null)

  // Click on iframe area to give it keyboard focus (critical for games)
  const handleFocus = useCallback(() => {
    if (iframeRef.current) {
      iframeRef.current.focus()
    }
  }, [])

  return (
    <div className="web-preview">
      <div className="preview-url-bar">
        <span style={{ color: '#10b981', fontSize: 12 }}>●</span>
        <input value="http://localhost:3000/preview" readOnly />
        <button
          onClick={handleFocus}
          style={{
            background: 'rgba(99,102,241,0.15)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: 4,
            color: '#a5b4fc',
            fontSize: 11,
            padding: '2px 8px',
            cursor: 'pointer',
            marginLeft: 6,
          }}
          title="点击聚焦预览窗口，激活键盘操作"
        >
          🎮 聚焦
        </button>
      </div>
      <iframe
        ref={iframeRef}
        className="preview-iframe"
        srcDoc={html}
        sandbox="allow-scripts allow-popups allow-forms"
        title="Preview"
        tabIndex={0}
        onClick={handleFocus}
        style={{ outline: 'none' }}
      />
    </div>
  )
}
