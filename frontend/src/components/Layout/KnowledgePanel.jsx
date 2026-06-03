import React, { useState, useEffect, useRef } from 'react'
import { BookOpen, ChevronRight, ArrowLeft, Plus, Trash2, Upload, Search, FolderOpen, FileText, Loader, MoreHorizontal, X, Pencil } from 'lucide-react'

export default function KnowledgePanel({ onClose }) {
  const [bases, setBases] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedKb, setSelectedKb] = useState(null) // null = 列表视图
  const [kbDetail, setKbDetail] = useState(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // 新建知识库
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  // 检索测试
  const [query, setQuery] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching] = useState(false)

  // 上传
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)

  // 更多菜单 & 删除确认 & 重命名
  const [moreMenuOpen, setMoreMenuOpen] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(null) // kb_id or null
  const [renameDialog, setRenameDialog] = useState(null) // { id, name, description } or null
  const [renameName, setRenameName] = useState('')
  const [renameDesc, setRenameDesc] = useState('')

  const fetchBases = async () => {
    setLoading(true)
    try {
      const resp = await fetch('/api/knowledge')
      const data = await resp.json()
      setBases(data.bases || [])
    } catch {}
    setLoading(false)
  }

  const fetchDetail = async (kbId) => {
    setDetailLoading(true)
    try {
      const resp = await fetch(`/api/knowledge/${kbId}`)
      const data = await resp.json()
      setKbDetail(data)
    } catch {}
    setDetailLoading(false)
  }

  useEffect(() => {
    if (!selectedKb) {
      fetchBases()
    } else {
      fetchDetail(selectedKb)
    }
  }, [selectedKb])

  const [createError, setCreateError] = useState('')

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreateError('')
    try {
      const resp = await fetch('/api/knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim(), description: newDesc.trim() }),
      })
      if (!resp.ok) {
        const errText = await resp.text().catch(() => resp.statusText)
        setCreateError(`服务器错误 (${resp.status}): ${errText}`)
        return
      }
      const data = await resp.json()
      if (data.status === 'created') {
        setShowCreate(false)
        setNewName('')
        setNewDesc('')
        fetchBases()  // 刷新列表
        setSelectedKb(data.id)
      } else {
        setCreateError(data.detail || data.error || '创建失败')
      }
    } catch (e) {
      setCreateError(`网络错误: ${e.message}`)
    }
  }

  const handleDeleteKb = async (kbId) => {
    try {
      await fetch(`/api/knowledge/${kbId}`, { method: 'DELETE' })
      setSelectedKb(null)
      setKbDetail(null)
      setDeleteConfirm(null)
      setMoreMenuOpen(false)
      fetchBases()
    } catch {}
  }

  const handleRename = async () => {
    if (!renameDialog || !renameName.trim()) return
    try {
      const resp = await fetch(`/api/knowledge/${renameDialog.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: renameName.trim(), description: renameDesc.trim() }),
      })
      const data = await resp.json()
      if (data.status === 'updated') {
        setRenameDialog(null)
        setMoreMenuOpen(false)
        // 更新详情
        if (kbDetail) setKbDetail({ ...kbDetail, name: renameName.trim(), description: renameDesc.trim() })
        fetchBases()
      }
    } catch {}
  }

  const handleDeleteDoc = async (docId) => {
    if (!selectedKb) return
    try {
      await fetch(`/api/knowledge/${selectedKb}/files/${docId}`, { method: 'DELETE' })
      fetchDetail(selectedKb)
    } catch {}
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !selectedKb) return
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      await fetch(`/api/knowledge/${selectedKb}/files`, {
        method: 'POST',
        body: formData,
      })
      fetchDetail(selectedKb)
    } catch {}
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleSearch = async () => {
    if (!query.trim() || !selectedKb) return
    setSearching(true)
    try {
      const resp = await fetch(`/api/knowledge/${selectedKb}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), top_k: 5 }),
      })
      const data = await resp.json()
      setSearchResults(data.results || [])
    } catch {}
    setSearching(false)
  }

  // ---- 二级视图：知识库详情 ----
  if (selectedKb && kbDetail) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
        {/* 头部 */}
        <div style={{
          padding: '12px 16px', borderBottom: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0, position: 'relative',
        }}>
          <button
            onClick={() => { setSelectedKb(null); setKbDetail(null); setSearchResults(null); setMoreMenuOpen(false) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex', padding: 2 }}
          >
            <ArrowLeft size={16} />
          </button>
          <FolderOpen size={16} color="var(--accent)" />
          <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {kbDetail.name}
          </span>
          {selectedKb !== '__default__' && (
            <div style={{ position: 'relative' }}>
              <button
                onClick={() => setMoreMenuOpen(!moreMenuOpen)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  color: 'var(--text-muted)', display: 'flex', padding: 4, borderRadius: 4,
                }}
              >
                <MoreHorizontal size={16} />
              </button>
              {moreMenuOpen && (
                <div style={{
                  position: 'absolute', top: '100%', right: 0, marginTop: 4,
                  background: 'var(--bg-primary)', border: '1px solid var(--border)',
                  borderRadius: 8, padding: 4, minWidth: 120,
                  boxShadow: '0 4px 16px rgba(0,0,0,0.12)', zIndex: 10,
                }}>
                  <button
                    onClick={() => {
                      setRenameDialog({ id: selectedKb, name: kbDetail.name, description: kbDetail.description || '' })
                      setRenameName(kbDetail.name)
                      setRenameDesc(kbDetail.description || '')
                      setMoreMenuOpen(false)
                    }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                      padding: '8px 12px', border: 'none', background: 'none',
                      borderRadius: 6, cursor: 'pointer', fontSize: 13,
                      color: 'var(--text-primary)',
                    }}
                  >
                    <Pencil size={14} /> 重命名
                  </button>
                  <button
                    onClick={() => { setDeleteConfirm(selectedKb); setMoreMenuOpen(false) }}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                      padding: '8px 12px', border: 'none', background: 'none',
                      borderRadius: 6, cursor: 'pointer', fontSize: 13,
                      color: 'var(--red, #ef4444)',
                    }}
                  >
                    <Trash2 size={14} /> 删除
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 内容 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
          {/* 统计 */}
          <div style={{
            fontSize: 11, color: 'var(--text-muted)', marginBottom: 16,
            padding: '8px 12px', background: 'var(--bg-secondary)', borderRadius: 6,
            border: '1px solid var(--border)',
          }}>
            {kbDetail.docs?.length || 0} 个文件 · {kbDetail.docs?.reduce((s, d) => s + (d.chunk_count || 0), 0)} 知识块
            {kbDetail.description && ` · ${kbDetail.description}`}
          </div>

          {/* 文件列表 */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>文件列表</div>
            {detailLoading ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 11 }}>加载中...</div>
            ) : (kbDetail.docs?.length || 0) === 0 ? (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 11 }}>暂无文件，请上传文档</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {kbDetail.docs.map((doc) => (
                  <div key={doc.id} style={{
                    padding: '8px 10px', borderRadius: 6,
                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <FileText size={12} /> {doc.filename}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>
                        {doc.chunk_count} 块 · {doc.char_count} 字符
                      </div>
                    </div>
                    <button
                      onClick={() => handleDeleteDoc(doc.id)}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        color: 'var(--red)', display: 'flex', padding: 2,
                      }}
                      title="删除文件"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 上传区 */}
          <div style={{ marginBottom: 16 }}>
            <input
              ref={fileInputRef}
              type="file"
              accept=".txt,.md,.pdf,.docx,.json,.csv"
              onChange={handleUpload}
              style={{ display: 'none' }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              style={{
                width: '100%', padding: '12px', borderRadius: 8,
                border: '2px dashed var(--border)', background: 'var(--bg-primary)',
                cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                fontSize: 12, color: 'var(--text-muted)',
              }}
            >
              {uploading ? (
                <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> 上传中...</>
              ) : (
                <><Upload size={14} /> 上传文件 (txt/md/pdf/docx/json/csv)</>
              )}
            </button>
          </div>

          {/* 检索测试 */}
          <div style={{
            padding: '12px', borderRadius: 8,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>检索测试</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10, lineHeight: 1.5 }}>
              输入一段查询语句，测试知识库能否检索到相关文档片段。用于验证上传的文件是否被正确索引和分块。
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                style={{
                  flex: 1, padding: '7px 10px',
                  background: 'var(--bg-primary)', border: '1px solid var(--border)',
                  borderRadius: 6, fontSize: 12, color: 'var(--text-primary)', outline: 'none',
                }}
                placeholder="输入查询语句..."
              />
              <button
                onClick={handleSearch}
                disabled={searching || !query.trim()}
                style={{
                  padding: '7px 12px', borderRadius: 6, fontSize: 11,
                  background: 'var(--accent)', border: 'none', color: 'white',
                  cursor: searching || !query.trim() ? 'default' : 'pointer',
                  opacity: searching || !query.trim() ? 0.5 : 1,
                  display: 'flex', alignItems: 'center', gap: 4,
                }}
              >
                {searching ? <Loader size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Search size={11} />}
                检索
              </button>
            </div>
            {searchResults && (
              <div style={{ marginTop: 10 }}>
                {searchResults.length === 0 ? (
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>未找到相关内容</div>
                ) : (
                  searchResults.map((r, i) => (
                    <div key={i} style={{
                      padding: '6px 8px', borderRadius: 6, background: 'var(--bg-primary)',
                      border: '1px solid var(--border)', marginBottom: 6, fontSize: 11, color: 'var(--text-secondary)',
                    }}>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 3 }}>
                        相关度: {r.score} | 来源: {r.metadata?.filename || '未知'}
                      </div>
                      {r.text?.slice(0, 150)}{r.text?.length > 150 ? '...' : ''}
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* 重命名弹窗 */}
        {renameDialog && (
          <div
            style={{
              position: 'absolute', inset: 0, zIndex: 20,
              background: 'rgba(0,0,0,0.4)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', padding: 16,
            }}
            onClick={() => setRenameDialog(null)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--bg-primary)', borderRadius: 12, padding: 20,
                width: '100%', maxWidth: 320, border: '1px solid var(--border)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 14 }}>
                重命名知识库
              </div>
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>名称</div>
                <input
                  autoFocus
                  value={renameName}
                  onChange={(e) => setRenameName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleRename()}
                  style={{
                    width: '100%', padding: '8px 10px',
                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                    borderRadius: 6, fontSize: 13, color: 'var(--text-primary)', outline: 'none',
                  }}
                />
              </div>
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>描述</div>
                <textarea
                  value={renameDesc}
                  onChange={(e) => setRenameDesc(e.target.value)}
                  style={{
                    width: '100%', padding: '8px 10px', minHeight: 60, resize: 'vertical',
                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                    borderRadius: 6, fontSize: 12, color: 'var(--text-primary)', outline: 'none',
                    fontFamily: 'inherit',
                  }}
                />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setRenameDialog(null)}
                  style={{
                    padding: '7px 16px', borderRadius: 6, fontSize: 12,
                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                    color: 'var(--text-secondary)', cursor: 'pointer',
                  }}
                >
                  取消
                </button>
                <button
                  onClick={handleRename}
                  disabled={!renameName.trim()}
                  style={{
                    padding: '7px 16px', borderRadius: 6, fontSize: 12,
                    background: renameName.trim() ? 'var(--accent)' : 'var(--bg-tertiary)',
                    border: 'none',
                    color: renameName.trim() ? 'white' : 'var(--text-muted)',
                    cursor: renameName.trim() ? 'pointer' : 'default', fontWeight: 500,
                  }}
                >
                  确认
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 删除确认弹窗 */}
        {deleteConfirm && (
          <div
            style={{
              position: 'absolute', inset: 0, zIndex: 20,
              background: 'rgba(0,0,0,0.4)', display: 'flex',
              alignItems: 'center', justifyContent: 'center', padding: 16,
            }}
            onClick={() => setDeleteConfirm(null)}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: 'var(--bg-primary)', borderRadius: 12, padding: 20,
                width: '100%', maxWidth: 320, border: '1px solid var(--border)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                确认删除知识库？
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                「{kbDetail.name}」
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 16 }}>
                包含 {kbDetail.docs?.length || 0} 个文件、{kbDetail.docs?.reduce((s, d) => s + (d.chunk_count || 0), 0)} 个知识块。删除后不可恢复。
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  onClick={() => setDeleteConfirm(null)}
                  style={{
                    padding: '7px 16px', borderRadius: 6, fontSize: 12,
                    background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                    color: 'var(--text-secondary)', cursor: 'pointer',
                  }}
                >
                  取消
                </button>
                <button
                  onClick={() => handleDeleteKb(deleteConfirm)}
                  style={{
                    padding: '7px 16px', borderRadius: 6, fontSize: 12,
                    background: 'var(--red, #ef4444)', border: 'none',
                    color: 'white', cursor: 'pointer', fontWeight: 500,
                  }}
                >
                  确认删除
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // ---- 一级视图：知识库列表 ----
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 头部 */}
      <div style={{
        padding: '12px 16px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
      }}>
        <BookOpen size={16} color="var(--accent)" />
        <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>知识库管理</span>
        <button
          onClick={() => setShowCreate(true)}
          style={{
            marginLeft: 'auto', padding: '4px 10px', borderRadius: 6, fontSize: 11,
            background: 'var(--accent)', border: 'none', color: 'white',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
          }}
        >
          <Plus size={12} /> 新建
        </button>
      </div>

      {/* 内容 */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 16px' }}>
        {/* 新建表单 */}
        {showCreate && (
          <div style={{
            padding: '12px', marginBottom: 16, borderRadius: 8,
            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>新建知识库</div>
            <input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              style={{
                width: '100%', padding: '7px 10px', marginBottom: 6,
                background: 'var(--bg-primary)', border: '1px solid var(--border)',
                borderRadius: 6, fontSize: 12, color: 'var(--text-primary)', outline: 'none',
              }}
              placeholder="知识库名称"
              autoFocus
            />
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              style={{
                width: '100%', padding: '7px 10px', marginBottom: 8, minHeight: 84, resize: 'vertical',
                background: 'var(--bg-primary)', border: '1px solid var(--border)',
                borderRadius: 6, fontSize: 12, color: 'var(--text-primary)', outline: 'none',
                fontFamily: 'inherit',
              }}
              placeholder="描述（可选）"
            />
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                onClick={handleCreate}
                disabled={!newName.trim()}
                style={{
                  flex: 1, padding: '7px', borderRadius: 6, fontSize: 12,
                  background: newName.trim() ? 'var(--accent)' : 'var(--bg-tertiary)',
                  border: 'none', color: newName.trim() ? 'white' : 'var(--text-muted)',
                  cursor: newName.trim() ? 'pointer' : 'default', fontWeight: 500,
                }}
              >
                创建
              </button>
              <button
                onClick={() => { setShowCreate(false); setNewName(''); setNewDesc(''); setCreateError('') }}
                style={{
                  padding: '7px 16px', borderRadius: 6, fontSize: 12,
                  background: 'var(--bg-primary)', border: '1px solid var(--border)',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                }}
              >
                取消
              </button>
            </div>
            {createError && (
              <div style={{ fontSize: 11, color: 'var(--red, #ef4444)', marginTop: 6 }}>{createError}</div>
            )}
          </div>
        )}

        {/* 知识库列表 */}
        {loading ? (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 24, fontSize: 12 }}>加载中...</div>
        ) : bases.length === 0 ? (
          <div style={{
            textAlign: 'center', padding: '40px 20px',
            color: 'var(--text-muted)', fontSize: 12,
          }}>
            <BookOpen size={32} style={{ opacity: 0.3, marginBottom: 12 }} />
            <div style={{ marginBottom: 6, fontWeight: 500 }}>还没有知识库</div>
            <div style={{ fontSize: 11, lineHeight: 1.5 }}>
              知识库用于存储文档资料，Agent 回复时会自动检索相关知识增强回答质量
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {bases.map((kb) => (
              <div
                key={kb.id}
                onClick={() => setSelectedKb(kb.id)}
                style={{
                  padding: '12px', borderRadius: 8, cursor: 'pointer',
                  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  transition: 'border-color 0.15s',
                }}
                onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--accent)'}
                onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--border)'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <FolderOpen size={16} color="var(--accent)" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{kb.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                      {kb.total_chunks} 知识块 · {kb.doc_count} 个文件
                      {kb.description && ` · ${kb.description}`}
                    </div>
                  </div>
                  <ChevronRight size={14} color="var(--text-muted)" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 总计 */}
        {bases.length > 0 && (
          <div style={{
            marginTop: 16, fontSize: 11, color: 'var(--text-muted)', textAlign: 'center',
            padding: '8px 0', borderTop: '1px solid var(--border)',
          }}>
            总计: {bases.reduce((s, b) => s + b.total_chunks, 0)} 知识块 · {bases.length} 个知识库
          </div>
        )}
      </div>
    </div>
  )
}
