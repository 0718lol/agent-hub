import React, { useState, useEffect, useRef } from 'react'
import { Upload } from 'lucide-react'

export default function AvatarUploadField({ value, onChange }) {
  const [preview, setPreview] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)
  const previewRef = useRef(null)

  useEffect(() => {
    return () => { if (previewRef.current) URL.revokeObjectURL(previewRef.current) }
  }, [])

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current)
      const url = URL.createObjectURL(file)
      previewRef.current = url
      setPreview(url)
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch('/api/upload', { method: 'POST', body: formData })
      const data = await resp.json()
      if (data.status === 'uploaded') onChange(data.url)
    } catch {}
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const avatarSrc = preview || (value && (value.startsWith('/') || value.startsWith('http')) ? value : null)

  return (
    <div>
      {avatarSrc && (
        <div style={{ marginBottom: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src={avatarSrc} alt="" style={{ width: 48, height: 48, borderRadius: 8, objectFit: 'cover', border: '2px solid var(--accent)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{uploading ? '上传中...' : '已设置头像'}</span>
        </div>
      )}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          onClick={() => fileRef.current?.click()}
          style={{
            flex: 'none', display: 'flex', alignItems: 'center', gap: 4,
            padding: '9px 12px', borderRadius: 8, fontSize: 12,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            color: 'var(--text-primary)', cursor: 'pointer', fontFamily: 'inherit',
          }}
          type="button"
        >
          <Upload size={14} />
          本地上传
        </button>
        <input
          value={preview ? '' : value || ''}
          onChange={(e) => { onChange(e.target.value); setPreview(null) }}
          placeholder="或输入 emoji / 图片 URL"
          style={{
            flex: 1, padding: '9px 12px',
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
            borderRadius: 8, fontSize: 13, color: 'var(--text-primary)',
            outline: 'none', fontFamily: 'inherit',
          }}
        />
        <input ref={fileRef} type="file" accept="image/*" onChange={handleUpload} style={{ display: 'none' }} />
      </div>
    </div>
  )
}
