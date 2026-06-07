import React from 'react'
import { labelStyle, inputStyle, makeBtnStyle } from './sharedStyles'

export default function OtherTab({
  rtTools, rtLoading, handleToggleRtTool, rtTestName, setRtTestName,
  rtTestParams, setRtTestParams, handleTestRtTool, saving, rtTestResult,
  kbStats, kbLoading, fetchKnowledgeDocs, kbUploading, handleKbUpload,
  kbDocs, handleKbDelete, kbQuery, setKbQuery, handleKbQuery, kbResults,
}) {
  const btnStyle = makeBtnStyle(saving)

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)',
        fontSize: 13, color: 'var(--accent)',
      }}>
        Agent 可通过 <code>[tool_call:name]</code> 标签调用以下工具，系统自动执行并返回结果
      </div>

      {/* Tool List */}
      <div style={{ marginBottom: 20 }}>
        <label style={labelStyle}>已注册工具 ({rtTools.length})</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {rtLoading ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 12 }}>加载中...</div>
          ) : rtTools.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: 16, fontSize: 12 }}>暂无工具</div>
          ) : (
            rtTools.map((tool) => (
              <div key={tool.name} style={{
                padding: '12px 14px', borderRadius: 10, background: 'var(--bg-secondary)',
                border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {tool.icon} {tool.name}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                    {tool.description}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{
                    fontSize: 10, padding: '2px 8px', borderRadius: 4,
                    background: tool.enabled ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)',
                    color: tool.enabled ? 'var(--green)' : 'var(--red)',
                    border: `1px solid ${tool.enabled ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)'}`,
                  }}>{tool.enabled ? '启用' : '禁用'}</span>
                  <button onClick={() => handleToggleRtTool(tool.name)} style={{
                    padding: '4px 10px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
                    background: tool.enabled ? 'rgba(239, 68, 68, 0.08)' : 'rgba(16, 185, 129, 0.08)',
                    border: `1px solid ${tool.enabled ? 'rgba(239, 68, 68, 0.25)' : 'rgba(16, 185, 129, 0.25)'}`,
                    color: tool.enabled ? 'var(--red)' : 'var(--green)',
                  }}>{tool.enabled ? '禁用' : '启用'}</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Test Tool */}
      <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>工具测试</label>
        <div style={{ marginBottom: 10 }}>
          <select
            value={rtTestName}
            onChange={(e) => setRtTestName(e.target.value)}
            style={{ ...inputStyle, marginBottom: 8 }}
          >
            <option value="">选择工具...</option>
            {rtTools.filter(t => t.enabled).map((t) => (
              <option key={t.name} value={t.name}>{t.icon} {t.name}</option>
            ))}
          </select>
          <textarea
            value={rtTestParams}
            onChange={(e) => setRtTestParams(e.target.value)}
            style={{ ...inputStyle, minHeight: 60, resize: 'vertical', fontFamily: 'monospace', fontSize: 12 }}
            placeholder='参数 JSON，如: {"query": "FastAPI 教程"}'
          />
        </div>
        <button onClick={handleTestRtTool} disabled={saving || !rtTestName} style={{
          ...btnStyle, background: 'var(--green)',
          opacity: (saving || !rtTestName) ? 0.6 : 1,
        }}>执行测试</button>
        {rtTestResult && (
          <div style={{
            marginTop: 12, padding: '10px', borderRadius: 8,
            background: rtTestResult.success ? 'rgba(16, 185, 129, 0.06)' : 'rgba(239, 68, 68, 0.08)',
            border: `1px solid ${rtTestResult.success ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.25)'}`,
            maxHeight: '25vh', overflowY: 'auto',
          }}>
            <div style={{ fontSize: 11, color: rtTestResult.success ? 'var(--green)' : 'var(--red)', fontWeight: 600, marginBottom: 4 }}>
              {rtTestResult.success ? '✅ 成功' : '❌ 失败'} {rtTestResult.usage?.time_ms ? `(${rtTestResult.usage.time_ms}ms)` : ''}
            </div>
            <pre style={{
              fontSize: 11, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              margin: 0, maxHeight: '20vh', overflow: 'auto',
            }}>
              {JSON.stringify(rtTestResult.data || rtTestResult.error, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* ===== 知识库管理 ===== */}
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: 'rgba(16, 185, 129, 0.06)', border: '1px solid rgba(16, 185, 129, 0.3)',
        fontSize: 13, color: 'var(--green)', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <span>知识库已索引 <b>{kbStats.total_chunks || 0}</b> 个知识块，Agent 回复时自动检索注入</span>
        <button onClick={fetchKnowledgeDocs} disabled={kbLoading} style={{
          padding: '4px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
          background: 'var(--green)', color: 'white', border: 'none', cursor: 'pointer',
          opacity: kbLoading ? 0.6 : 1,
        }}>{kbLoading ? '...' : '刷新'}</button>
      </div>

      {/* Upload */}
      <div style={{ marginBottom: 20 }}>
        <label style={labelStyle}>上传文档 (支持 txt/md/pdf/docx/json/csv)</label>
        <label style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
          borderRadius: 10, border: '2px dashed var(--border)', cursor: 'pointer',
          background: kbUploading ? 'var(--bg-tertiary)' : 'white', transition: 'all 0.2s',
        }}>
          <input type="file" accept=".txt,.md,.pdf,.docx,.json,.csv" onChange={handleKbUpload} style={{ display: 'none' }} />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
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
                  background: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.25)', color: 'var(--red)',
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
            padding: '8px 16px', borderRadius: 8, background: 'var(--accent)',
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
                  padding: '8px 10px', borderRadius: 6, background: 'var(--bg-primary)', border: '1px solid var(--border)',
                  marginBottom: 6, fontSize: 12, color: 'var(--text-secondary)',
                }}>
                  <div style={{ fontSize: 10, color: 'var(--text-secondary)', marginBottom: 4 }}>
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
