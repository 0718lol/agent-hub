import React from 'react'
import { FileText, Image, Download } from 'lucide-react'

/**
 * 聊天消息中附件卡片组件。
 * 根据文件类型展示图片预览或文件信息卡片。
 */
export default function FileAttachmentCard({ attachment }) {
  const {
    original_name = 'unknown',
    url = '',
    content_type = '',
    size = 0,
    is_image = content_type.startsWith('image/'),
  } = attachment

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  // 图片附件 → 点击放大预览
  if (is_image && url) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="file-attachment-image"
        style={{ display: 'block', maxWidth: 280, borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--border)' }}
      >
        <img
          src={url}
          alt={original_name}
          style={{ width: '100%', maxHeight: 200, objectFit: 'cover', display: 'block' }}
        />
        <div className="file-attachment-image-footer">
          <Image size={12} />
          <span>{original_name}</span>
        </div>
      </a>
    )
  }

  // 文档附件 → 文件卡片
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="file-attachment-card"
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
        padding: '10px 14px', maxWidth: 320,
        background: 'var(--bg-secondary)', border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)', textDecoration: 'none',
        transition: 'background var(--duration-fast) var(--ease-in-out)',
      }}
    >
      <div style={{
        width: 40, height: 40, borderRadius: 'var(--radius-sm)',
        background: 'var(--accent-bg)', color: 'var(--accent)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <FileText size={20} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-primary)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {original_name}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
          {formatSize(size)}
        </div>
      </div>
      <Download size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
    </a>
  )
}
