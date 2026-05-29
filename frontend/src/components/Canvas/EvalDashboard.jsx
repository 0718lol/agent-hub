import React, { useState, useEffect, useCallback } from 'react'
import { Download, Code, FileCode, Terminal, ExternalLink, Box, X } from 'lucide-react'

// Unified Line-by-Line Diff Algorithm (Zero Dependency, Lookahead)
const getUnifiedDiff = (oldText, newText) => {
  const oldLines = oldText ? oldText.split('\n') : []
  const newLines = newText ? newText.split('\n') : []
  const diff = []
  
  let i = 0, j = 0
  while (i < oldLines.length || j < newLines.length) {
    if (i < oldLines.length && j < newLines.length) {
      if (oldLines[i] === newLines[j]) {
        diff.push({ type: 'normal', text: oldLines[i], lineNumOld: i + 1, lineNumNew: j + 1 })
        i++; j++
      } else {
        // Lookahead to check for shifts or modifications
        let foundMatch = false
        const maxLookahead = 8
        for (let look = 1; look < maxLookahead; look++) {
          if (i + look < oldLines.length && oldLines[i + look] === newLines[j]) {
            for (let d = 0; d < look; d++) {
              diff.push({ type: 'delete', text: oldLines[i + d], lineNumOld: i + d + 1 })
            }
            i += look
            foundMatch = true
            break
          }
          if (j + look < newLines.length && oldLines[i] === newLines[j + look]) {
            for (let a = 0; a < look; a++) {
              diff.push({ type: 'add', text: newLines[j + a], lineNumNew: j + a + 1 })
            }
            j += look
            foundMatch = true
            break
          }
        }
        if (!foundMatch) {
          diff.push({ type: 'delete', text: oldLines[i], lineNumOld: i + 1 })
          diff.push({ type: 'add', text: newLines[j], lineNumNew: j + 1 })
          i++; j++
        }
      }
    } else if (i < oldLines.length) {
      diff.push({ type: 'delete', text: oldLines[i], lineNumOld: i + 1 })
      i++
    } else if (j < newLines.length) {
      diff.push({ type: 'add', text: newLines[j], lineNumNew: j + 1 })
      j++
    }
  }
  return diff
}

/**
 * EvalDashboard — Evaluation metrics visualization panel.
 * Shows: Agent scores, Best-of-N stats, Quality Gate pass rates,
 * Sandbox execution stats, and recent traces.
 * Refactored to include: Agentic Deliverables Versioning & Line Diff.
 */
export default function EvalDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [benchStatus, setBenchStatus] = useState(null)
  const [benchRunning, setBenchRunning] = useState(false)
  
  // Artifacts State
  const [artifacts, setArtifacts] = useState([])
  const [selectedArtifact, setSelectedArtifact] = useState(null)

  // Drawer Version details state
  const [previewVersionLabel, setPreviewVersionLabel] = useState('')
  const [diffMode, setDiffMode] = useState(false)
  const [compareVersionLabel, setCompareVersionLabel] = useState('')

  const fetchMetrics = useCallback(async () => {
    try {
      const resp = await fetch('/api/metrics')
      const d = await resp.json()
      setData(d)
    } catch {}
    setLoading(false)
  }, [])

  const fetchArtifacts = useCallback(async () => {
    try {
      const resp = await fetch('/api/artifacts?limit=15')
      const arr = await resp.json()
      setArtifacts(arr)
    } catch {}
  }, [])

  useEffect(() => {
    fetchMetrics()
    fetchArtifacts()
    const interval = setInterval(() => {
      fetchMetrics()
      fetchArtifacts()
    }, 5000)
    return () => clearInterval(interval)
  }, [fetchMetrics, fetchArtifacts])

  // Monitor selected artifact to set default preview versions
  useEffect(() => {
    if (selectedArtifact && selectedArtifact.history && selectedArtifact.history.length > 0) {
      setPreviewVersionLabel(selectedArtifact.history[0].version_label)
      setDiffMode(false)
      if (selectedArtifact.history.length > 1) {
        setCompareVersionLabel(selectedArtifact.history[1].version_label)
      } else {
        setCompareVersionLabel('')
      }
    }
  }, [selectedArtifact])

  const startBenchmark = async () => {
    setBenchRunning(true)
    try {
      await fetch('/api/benchmark/run', { method: 'POST' })
      const poll = setInterval(async () => {
        const resp = await fetch('/api/benchmark/status')
        const status = await resp.json()
        setBenchStatus(status)
        if (status.status === 'completed' || status.status === 'idle') {
          clearInterval(poll)
          setBenchRunning(false)
          fetchMetrics()
          fetchArtifacts()
        }
      }, 2000)
    } catch {
      setBenchRunning(false)
    }
  }

  const downloadFile = (artifact) => {
    // Downloads latest version of file
    const blob = new Blob([artifact.code], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = artifact.name
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return <div style={{ padding: 24, color: 'var(--text-muted)' }}>加载评估数据...</div>
  }

  return (
    <div style={{ padding: 20, overflow: 'auto', height: '100%', position: 'relative' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: 16, color: 'var(--text-primary)' }}>📊 评估 Dashboard</h3>
        <button
          onClick={startBenchmark}
          disabled={benchRunning}
          style={{
            padding: '6px 16px', borderRadius: 8, fontSize: 12, fontWeight: 600,
            background: benchRunning ? 'var(--bg-tertiary)' : 'var(--accent)',
            border: 'none', color: 'white', cursor: benchRunning ? 'not-allowed' : 'pointer',
          }}
        >
          {benchRunning ? `⏳ 运行中 ${benchStatus?.progress || 0}/${benchStatus?.total || 0}` : '🚀 一键 Benchmark'}
        </button>
      </div>

      {/* Overview cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
        <StatCard title="总请求" value={data?.total_requests || 0} color="var(--accent)" />
        <StatCard
          title="质量门通过率"
          value={`${data?.quality_gate?.pass_rate || 0}%`}
          color="#10b981"
        />
        <StatCard
          title="Best-of-N 提升"
          value={data?.best_of_n?.improvement ? `+${data.best_of_n.improvement}分` : 'N/A'}
          color="#f59e0b"
        />
        <StatCard
          title="沙盒成功率"
          value={data?.sandbox?.success_rate ? `${data.sandbox.success_rate}%` : 'N/A'}
          color="#8b5cf6"
        />
      </div>

      {/* Artifacts Deliverable Showcase (Prefect Inspired) */}
      {artifacts.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <SectionTitle>📦 智能体交付产物 (Generated Artifacts)</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
            {artifacts.map((art) => {
              return (
                <div key={art.name} style={{
                  padding: 12, borderRadius: 10,
                  background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  transition: 'all 0.2s',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                    <div style={{
                      width: 32, height: 32, borderRadius: 6,
                      background: 'rgba(99, 102, 241, 0.1)',
                      color: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0
                    }}>
                      <FileCode size={16} />
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }} title={art.name}>
                          {art.name}
                        </div>
                        {art.total_versions > 1 && (
                          <span style={{
                            fontSize: 10, padding: '1px 5px', borderRadius: 4,
                            background: 'rgba(99,102,241,0.1)', color: '#818cf8', fontWeight: 600
                          }}>
                            v{art.total_versions}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                        由 {art.agent_id.replace('agent_', '')} 交付
                      </div>
                      <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
                        {art.quality_score !== null && (
                          <span style={{
                            fontSize: 10, padding: '1px 5px', borderRadius: 4,
                            background: art.quality_score >= 80 ? 'rgba(16,185,129,0.06)' : art.quality_score >= 60 ? 'rgba(245,158,11,0.06)' : 'rgba(239,68,68,0.06)',
                            color: art.quality_score >= 80 ? '#10b981' : art.quality_score >= 60 ? '#f59e0b' : '#ef4444',
                            border: art.quality_score >= 80 ? '1px solid rgba(16,185,129,0.15)' : art.quality_score >= 60 ? '1px solid rgba(245,158,11,0.15)' : '1px solid rgba(239,68,68,0.15)',
                            fontWeight: 500
                          }}>
                            ⭐ {art.quality_score}分
                          </span>
                        )}
                        {art.sandbox_status && (
                          <span style={{
                            fontSize: 10, padding: '1px 5px', borderRadius: 4,
                            background: art.sandbox_status === 'success' ? 'rgba(16,185,129,0.06)' : art.sandbox_status === 'failed' ? 'rgba(239,68,68,0.06)' : 'rgba(156,163,175,0.06)',
                            color: art.sandbox_status === 'success' ? '#10b981' : art.sandbox_status === 'failed' ? '#ef4444' : 'var(--text-muted)',
                            border: art.sandbox_status === 'success' ? '1px solid rgba(16,185,129,0.15)' : art.sandbox_status === 'failed' ? '1px solid rgba(239,68,68,0.15)' : '1px solid rgba(156,163,175,0.15)',
                            fontWeight: 500
                          }}>
                            {art.sandbox_status === 'success' ? '✅ 沙盒安全' : art.sandbox_status === 'failed' ? '⚠️ 运行报错' : '⏳ 未测试'}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                    <button
                      onClick={() => setSelectedArtifact(art)}
                      title="查看代码版本与对比"
                      style={{
                        padding: 6, borderRadius: 6, border: 'none', background: 'rgba(255,255,255,0.03)',
                        color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex'
                      }}
                    >
                      <Code size={13} />
                    </button>
                    <button
                      onClick={() => downloadFile(art)}
                      title="下载最新版本"
                      style={{
                        padding: 6, borderRadius: 6, border: 'none', background: 'rgba(16,185,129,0.1)',
                        color: '#10b981', cursor: 'pointer', display: 'flex'
                      }}
                    >
                      <Download size={13} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Agent Performance Table */}
      {data?.agent_summary && Object.keys(data.agent_summary).length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <SectionTitle>Agent 性能排行</SectionTitle>
          <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--border)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'var(--bg-secondary)' }}>
                  <th style={thStyle}>Agent</th>
                  <th style={thStyle}>平均分</th>
                  <th style={thStyle}>延迟</th>
                  <th style={thStyle}>Token</th>
                  <th style={thStyle}>调用次数</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.agent_summary).map(([id, s]) => (
                  <tr key={id} style={{ borderTop: '1px solid var(--border)' }}>
                    <td style={tdStyle}>{id.replace('agent_', '')}</td>
                    <td style={tdStyle}>
                      <ScoreBar score={s.avg_score} />
                    </td>
                    <td style={tdStyle}>{s.avg_latency_ms}ms</td>
                    <td style={tdStyle}>{s.total_tokens.toLocaleString()}</td>
                    <td style={tdStyle}>{s.call_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Benchmark Results */}
      {benchStatus?.results?.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <SectionTitle>Benchmark 结果对比</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {benchStatus.results.map((r) => (
              <div key={r.case_id} style={{
                padding: 12, borderRadius: 10,
                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>{r.case_name}</span>
                  <span style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 4,
                    background: r.improvement > 0 ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                    color: r.improvement > 0 ? '#10b981' : '#ef4444',
                  }}>
                    {r.improvement > 0 ? '+' : ''}{r.improvement}分
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-muted)' }}>
                  <span>普通: <b style={{ color: 'var(--text-primary)' }}>{r.normal_score}</b>分 ({r.normal_duration_ms}ms)</span>
                  <span>Best-of-{r.bon_n}: <b style={{ color: '#10b981' }}>{r.bon_score}</b>分 ({r.bon_duration_ms}ms)</span>
                </div>
              </div>
            ))}
          </div>
          {benchStatus.summary && (
            <div style={{
              marginTop: 12, padding: 12, borderRadius: 10,
              background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)',
            }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--accent)', marginBottom: 6 }}>📈 总结</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
                普通生成平均: <b>{benchStatus.summary.normal_avg_score}</b>分 →
                Best-of-N 平均: <b>{benchStatus.summary.bon_avg_score}</b>分 |
                平均提升: <b style={{ color: '#10b981' }}>+{benchStatus.summary.avg_improvement}</b>分 |
                最大提升案例: {benchStatus.summary.best_improvement_case}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Recent Traces */}
      {data?.recent_traces?.length > 0 && (
        <div>
          <SectionTitle>最近执行 Trace</SectionTitle>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {data.recent_traces.slice(-5).reverse().map((trace) => (
              <div key={trace.task_id} style={{
                padding: 10, borderRadius: 8,
                background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                fontSize: 11,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 500 }}>
                    {trace.user_input}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>{trace.total_duration_ms}ms</span>
                </div>
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                  {trace.steps.map((step, i) => (
                    <span key={i} style={{
                      padding: '2px 6px', borderRadius: 4, fontSize: 10,
                      background: step.status === 'success' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                      color: step.status === 'success' ? '#10b981' : '#ef4444',
                    }}>
                      {step.agent_id.replace('agent_', '')} {step.duration_ms}ms
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state */}
      {(!data?.agent_summary || Object.keys(data.agent_summary).length === 0) && artifacts.length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13,
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
          <div>还没有评估数据</div>
          <div style={{ marginTop: 8, fontSize: 12 }}>与 Agent 对话或运行 Benchmark 后，数据将自动展示</div>
        </div>
      ) : null}

      {/* Code Preview Drawer Modal (Overlay) */}
      {selectedArtifact && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(13,17,23,0.96)', zIndex: 100, padding: 20,
          display: 'flex', flexDirection: 'column',
          borderLeft: '1px solid var(--border)',
          fontFamily: 'var(--font-ui)',
        }}>
          {/* Title bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                🔍 {selectedArtifact.name}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
                语言: {selectedArtifact.language} | 共 {selectedArtifact.total_versions} 个历史版本
              </div>
            </div>
            <button
              onClick={() => setSelectedArtifact(null)}
              style={{
                background: 'none', border: 'none', color: 'var(--text-muted)',
                cursor: 'pointer', padding: 4, borderRadius: 4, display: 'flex'
              }}
            >
              <X size={18} />
            </button>
          </div>

          {/* Version Selector Toolbar */}
          <div style={{
            display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12,
            padding: '8px 12px', background: 'rgba(255, 255, 255, 0.02)',
            borderRadius: 6, border: '1px solid rgba(255, 255, 255, 0.05)',
            fontSize: 12
          }}>
            {/* Base Version */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ color: 'var(--text-muted)' }}>{diffMode ? "对比版本 (新):" : "当前版本:"}</span>
              <select
                value={previewVersionLabel}
                onChange={(e) => setPreviewVersionLabel(e.target.value)}
                style={{
                  background: '#1d2129', border: '1px solid var(--border)',
                  color: 'var(--text-primary)', padding: '2px 8px', borderRadius: 4, outline: 'none'
                }}
              >
                {selectedArtifact.history.map(h => (
                  <option key={h.version_label} value={h.version_label}>
                    {h.version_label} ({h.agent_id.replace('agent_', '')})
                  </option>
                ))}
              </select>
            </div>

            {/* Diff Switch (only if we have more than 1 version) */}
            {selectedArtifact.total_versions > 1 && (
              <>
                <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.08)' }} />
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: 'var(--text-secondary)' }}>
                  <input
                    type="checkbox"
                    checked={diffMode}
                    onChange={(e) => setDiffMode(e.target.checked)}
                    style={{ cursor: 'pointer' }}
                  />
                  <span>开启 Diff 版本对比</span>
                </label>
              </>
            )}

            {/* Target Compare Version */}
            {diffMode && selectedArtifact.total_versions > 1 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 'auto' }}>
                <span style={{ color: 'var(--text-muted)' }}>基准版本 (旧):</span>
                <select
                  value={compareVersionLabel}
                  onChange={(e) => setCompareVersionLabel(e.target.value)}
                  style={{
                    background: '#1d2129', border: '1px solid var(--border)',
                    color: 'var(--text-primary)', padding: '2px 8px', borderRadius: 4, outline: 'none'
                  }}
                >
                  {selectedArtifact.history.map(h => (
                    <option key={h.version_label} value={h.version_label} disabled={h.version_label === previewVersionLabel}>
                      {h.version_label} ({h.agent_id.replace('agent_', '')})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          
          {/* Main Code Viewport */}
          <div style={{
            flex: 1, borderRadius: 8, overflow: 'hidden',
            border: '1px solid var(--border)', background: '#0d1117'
          }}>
            {!diffMode ? (
              // Standard Code Mode
              <pre style={{
                margin: 0, padding: 14, height: '100%', overflow: 'auto',
                fontSize: 12, fontFamily: "'JetBrains Mono', monospace",
                color: '#e6edf3', lineHeight: 1.5,
              }}>
                <code>
                  {selectedArtifact.history.find(h => h.version_label === previewVersionLabel)?.code || ""}
                </code>
              </pre>
            ) : (
              // Diff Comparison Mode
              (() => {
                const newCode = selectedArtifact.history.find(h => h.version_label === previewVersionLabel)?.code || ""
                const oldCode = selectedArtifact.history.find(h => h.version_label === compareVersionLabel)?.code || ""
                const diffLines = getUnifiedDiff(oldCode, newCode)
                return (
                  <div style={{
                    height: '100%', overflow: 'auto', padding: 12,
                    fontFamily: "'JetBrains Mono', monospace", fontSize: 12, lineHeight: 1.6,
                    color: '#e6edf3'
                  }}>
                    {diffLines.map((line, idx) => {
                      let bgColor = 'transparent'
                      let textColor = '#e6edf3'
                      let sign = ' '
                      if (line.type === 'add') {
                        bgColor = 'rgba(16,185,129,0.12)'
                        textColor = '#4ade80'
                        sign = '+'
                      } else if (line.type === 'delete') {
                        bgColor = 'rgba(239,68,68,0.12)'
                        textColor = '#f87171'
                        sign = '-'
                      }
                      
                      return (
                        <div key={idx} style={{
                          display: 'flex', background: bgColor, color: textColor,
                          padding: '1px 6px', borderRadius: 2
                        }}>
                          {/* Line numbers gutter */}
                          <span style={{
                            width: 32, userSelect: 'none', color: 'rgba(255,255,255,0.2)',
                            textAlign: 'right', marginRight: 10, fontSize: 10
                          }}>
                            {line.type === 'delete' ? line.lineNumOld : line.type === 'add' ? '' : line.lineNumOld}
                          </span>
                          <span style={{
                            width: 32, userSelect: 'none', color: 'rgba(255,255,255,0.2)',
                            textAlign: 'right', marginRight: 14, fontSize: 10
                          }}>
                            {line.type === 'add' ? line.lineNumNew : line.type === 'delete' ? '' : line.lineNumNew}
                          </span>
                          {/* Sign */}
                          <span style={{ width: 14, userSelect: 'none', opacity: 0.6, fontWeight: 'bold' }}>{sign}</span>
                          {/* Text content */}
                          <span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{line.text}</span>
                        </div>
                      )
                    })}
                  </div>
                )
              })()
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Sub-components
function StatCard({ title, value, color }) {
  return (
    <div style={{
      padding: 14, borderRadius: 10,
      background: 'var(--bg-secondary)', border: '1px solid var(--border)',
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}

function SectionTitle({ children }) {
  return <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 10 }}>{children}</div>
}

function ScoreBar({ score }) {
  const color = score >= 80 ? '#10b981' : score >= 60 ? '#f59e0b' : '#ef4444'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 60, height: 6, borderRadius: 3, background: 'var(--bg-tertiary)' }}>
        <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', borderRadius: 3, background: color }} />
      </div>
      <span style={{ color, fontWeight: 600 }}>{score}</span>
    </div>
  )
}

const thStyle = { padding: '8px 12px', textAlign: 'left', fontSize: 11, color: 'var(--text-muted)', fontWeight: 500 }
const tdStyle = { padding: '8px 12px', color: 'var(--text-primary)' }

