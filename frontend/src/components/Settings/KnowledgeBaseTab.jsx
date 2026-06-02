import React from 'react'
import styles from './SettingsPanel.module.css'

export default function KnowledgeBaseTab({
  isDark, saving, kbStats, kbLoading, fetchKnowledgeDocs,
  kbUploading, handleKbUpload, kbDocs, handleKbDelete,
  kbQuery, setKbQuery, handleKbQuery, kbResults,
}) {
  return (
    <>
      <div className={styles.kbInfoBox} style={{
        background: isDark ? 'rgba(34,197,94,0.08)' : '#f0fdf4', border: `1px solid ${isDark ? 'rgba(34,197,94,0.2)' : '#bbf7d0'}`,
        color: isDark ? '#86efac' : '#166534',
      }}>
        <span>知识库已索引 <b>{kbStats.total_chunks || 0}</b> 个知识块，Agent 回复时自动检索注入</span>
        <button onClick={fetchKnowledgeDocs} disabled={kbLoading} className={styles.kbRefreshBtn}
          style={{ opacity: kbLoading ? 0.6 : 1 }}>{kbLoading ? '...' : '刷新'}</button>
      </div>

      {/* Upload */}
      <div style={{ marginBottom: 20 }}>
        <label className={styles.label}>上传文档 (支持 txt/md/pdf/docx/json/csv)</label>
        <label className={styles.uploadArea} style={{ border: `2px dashed ${isDark ? 'rgba(255,255,255,0.15)' : '#d1d5db'}`, background: 'var(--bg-secondary)' }}>
          <input type="file" accept=".txt,.md,.pdf,.docx,.json,.csv" onChange={handleKbUpload} style={{ display: 'none' }} />
          <span className={styles.uploadText}>
            {kbUploading ? '正在处理...' : '点击选择文件上传到知识库'}
          </span>
        </label>
      </div>

      {/* Document List */}
      <div style={{ marginBottom: 20 }}>
        <label className={styles.label}>已入库文档</label>
        <div className={styles.scrollList}>
          {kbDocs.length === 0 ? (
            <div className={styles.emptyText}>
              暂无文档，请上传文件到知识库
            </div>
          ) : (
            kbDocs.map((doc) => (
              <div key={doc.id} className={styles.docItem}>
                <div>
                  <div className={styles.docName}>{doc.filename}</div>
                  <div className={styles.docMeta}>
                    {doc.chunk_count} 块 | {doc.char_count} 字符
                  </div>
                </div>
                <button onClick={() => handleKbDelete(doc.id)} disabled={saving} className={styles.deleteBtn} style={{
                  background: isDark ? 'rgba(239,68,68,0.12)' : '#fef2f2', border: `1px solid ${isDark ? 'rgba(239,68,68,0.25)' : '#fecaca'}`, color: isDark ? '#f87171' : '#dc2626',
                }}>删除</button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Test Query */}
      <div className={styles.searchCard}>
        <label className={styles.sectionTitle}>检索测试</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={kbQuery}
            onChange={(e) => setKbQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleKbQuery()}
            className={styles.inputSecondary}
            style={{ flex: 1 }}
            placeholder="输入查询语句测试知识库检索..."
          />
          <button onClick={handleKbQuery} disabled={saving || !kbQuery.trim()} className={styles.smallBtn} style={{
            background: '#4f46e5', color: 'white', padding: '8px 16px', borderRadius: 8, fontSize: 12,
            opacity: saving ? 0.6 : 1,
          }}>检索</button>
        </div>
        {kbResults && (
          <div className={styles.searchResults}>
            {kbResults.length === 0 ? (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: 8 }}>未找到相关内容</div>
            ) : (
              kbResults.map((r, i) => (
                <div key={i} className={styles.searchResult}>
                  <div className={styles.resultMeta}>
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
