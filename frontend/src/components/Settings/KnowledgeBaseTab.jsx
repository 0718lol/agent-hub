import React from 'react'

export default function KnowledgeBaseTab({
  isDark, saving, kbStats, kbLoading, fetchKnowledgeDocs,
  kbUploading, handleKbUpload, kbDocs, handleKbDelete,
  kbQuery, setKbQuery, handleKbQuery, kbResults,
}) {
  const labelStyle = {
    fontSize: 13,
    color: 'var(--text-muted)',
    marginBottom: 6,
    display: 'block',
    fontWeight: 500,
  }

  const inputStyle = {
    width: '100%',
    padding: '10px 14px',
    background: 'var(--bg-secondary)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    color: 'var(--text-primary)',
    fontSize: 13,
    outline: 'none',
    fontFamily: 'inherit',
  }

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: isDark ? 'rgba(34,197,94,0.08)' : '#f0fdf4', border: `1px solid ${isDark ? 'rgba(34,197,94,0.2)' : '#bbf7d0'}`,
        fontSize: 13, color: isDark ? '#86efac' : '#166534', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span>知识库已索引 <b>{kbStats.total_chunks || 0}</b> 个知识块，Agent 回复时自动检索注入</span>
        <button onClick={fetchKnowledgeDocs} disabled={kbLoading} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
          background: '#16a34a', color: 'white', border: 'none', cursor: 'pointer',
          opacity: kbLoading ? 0.6 : 1,
        }}>{kbLoading ? '...' : '刷新'}</button>
      </div>

      {/* Upload */}
      <div style={{ marginBottom: 20 }}>
        <label style={labelStyle}>上传文档 (支持 txt/md/pdf/docx/json/csv)</label>
        <label style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
          borderRadius: 10, border: `2px dashed ${isDark ? 'rgba(255,255,255,0.15)' : '#d1d5db'}`, cursor: 'pointer',
          background: kbUploading ? 'var(--bg-secondary)' : 'var(--bg-secondary)', transition: 'all 0.2s',
        }}>
          <input type="file" accept=".txt,.md,.pdf,.docx,.json,.csv" onChange={handleKbUpload} style={{ display: 'none' }} />
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            {kbUploading ? '正在处理...' : '点击选择文件上传到知识库'}
          </span>
        </label>
      </div>

      {/* Document List */}
      <div style={{ marginBottom: 20 }}>
        <label style={labelStyle}>已入库文档</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: '25vh', overflowY: 'auto' }}>
          {kbDocs.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '16px 0', fontSize: 12 }}>
              暂无文档，请上传文件到知识库
            </div>
          ) : (
            kbDocs.map((doc) => (
              <div key={doc.id} style={{
                padding: '10px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>{doc.filename}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                    {doc.chunk_count} 块 | {doc.char_count} 字符
                  </div>
                </div>
                <button onClick={() => handleKbDelete(doc.id)} disabled={saving} style={{
                  padding: '4px 10px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                  background: isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2', border: `1px solid ${isDark ? 'rgba(239,68,68,0.25)' : '#fecaca'}`, color: isDark ? '#f87171' : '#dc2626',
                }}>删除</button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Test Query */}
      <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>检索测试</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={kbQuery}
            onChange={(e) => setKbQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleKbQuery()}
            style={{ ...inputStyle, flex: 1 }}
            placeholder="输入查询语句测试知识库检索..."
          />
          <button onClick={handleKbQuery} disabled={saving || !kbQuery.trim()} style={{
            padding: '8px 16px', borderRadius: 8, background: '#4f46e5',
            border: 'none', color: 'white', fontSize: 12, fontWeight: 600, cursor: 'pointer',
            opacity: saving ? 0.6 : 1,
          }}>检索</button>
        </div>
        {kbResults && (
          <div style={{ marginTop: 12, maxHeight: '20vh', overflowY: 'auto' }}>
            {kbResults.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>未找到相关内容</div>
            ) : (
              kbResults.map((r, i) => (
                <div key={i} style={{
                  padding: '8px 10px', borderRadius: 6, background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  marginBottom: 6, fontSize: 12, color: 'var(--text-primary)',
                }}>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>
                    相关度: {r.score} | 来源: {r.metadata?.filename || '未知'}
                  </div>
                  {r.text?.slice(0, 200)}{r.text?.length > 200 ? '...' : ''}
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </>
  )
}
