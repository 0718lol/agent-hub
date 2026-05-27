import React, { useRef, useState, useCallback } from 'react'
import { Upload, X, FileText, AlertTriangle } from 'lucide-react'
import { uploadWithStore } from '../../utils/uploader'

export default function FileUploader({ onUploaded, onClose }) {
  const fileInputRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const handleFile = useCallback(async (file) => {
    setError('')
    setUploading(true)
    try {
      const result = await uploadWithStore(file)
      if (onUploaded) onUploaded(result)
    } catch (err) {
      setError(err.message || '上传失败')
    }
    setUploading(false)
  }, [onUploaded])

  const handleChange = (e) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }

  return (
    <div className="file-uploader-overlay" onClick={onClose}>
      <div className="file-uploader" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="file-uploader-header">
          <span className="file-uploader-title">上传文件</span>
          <button className="file-uploader-close" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* 拖拽区域 */}
        <div
          className={`file-uploader-dropzone ${dragOver ? 'drag-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          {uploading ? (
            <div className="file-uploader-uploading">
              <div className="file-uploader-spinner" />
              <span>正在上传...</span>
            </div>
          ) : (
            <>
              <Upload size={32} className="file-uploader-icon" />
              <div className="file-uploader-hint">
                <span>拖拽文件到此处，或点击选择</span>
                <span className="file-uploader-subhint">
                  支持 TXT / MD / DOCX / PDF / 图片
                </span>
              </div>
            </>
          )}
        </div>

        {/* 错误提示 */}
        {error && (
          <div className="file-uploader-error">
            <AlertTriangle size={14} />
            <span>{error}</span>
          </div>
        )}

        {/* 底部操作 */}
        <div className="file-uploader-footer">
          <button className="file-uploader-btn" onClick={() => fileInputRef.current?.click()}>
            <FileText size={14} />
            选择文件
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".txt,.md,.docx,.pdf,.json,.csv,image/*"
            onChange={handleChange}
            style={{ display: 'none' }}
          />
        </div>
      </div>
    </div>
  )
}
