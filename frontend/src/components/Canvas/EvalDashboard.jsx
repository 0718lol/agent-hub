import React, { useState, useEffect, useCallback } from 'react'

/**
 * EvalDashboard — Evaluation metrics visualization panel.
 * Shows: Agent scores, Best-of-N stats, Quality Gate pass rates,
 * Sandbox execution stats, and recent traces.
 */
export default function EvalDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [benchStatus, setBenchStatus] = useState(null)
  const [benchRunning, setBenchRunning] = useState(false)

  const fetchMetrics = useCallback(async () => {
    try {
      const resp = await fetch('/api/metrics')
      const d = await resp.json()
      setData(d)
    } catch {}
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchMetrics()
    const interval = setInterval(fetchMetrics, 5000)
    return () => clearInterval(interval)
  }, [fetchMetrics])

  const startBenchmark = async () => {
    setBenchRunning(true)
    try {
      await fetch('/api/benchmark/run', { method: 'POST' })
      // Start polling
      const poll = setInterval(async () => {
        const resp = await fetch('/api/benchmark/status')
        const status = await resp.json()
        setBenchStatus(status)
        if (status.status === 'completed' || status.status === 'idle') {
          clearInterval(poll)
          setBenchRunning(false)
          fetchMetrics()
        }
      }, 2000)
    } catch {
      setBenchRunning(false)
    }
  }

  if (loading) {
    return <div style={{ padding: 24, color: 'var(--text-muted)' }}>加载评估数据...</div>
  }

  return (
    <div style={{ padding: 20, overflow: 'auto', height: '100%' }}>
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
      {!data?.agent_summary || Object.keys(data.agent_summary).length === 0 ? (
        <div style={{
          padding: 40, textAlign: 'center', color: 'var(--text-muted)', fontSize: 13,
        }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
          <div>还没有评估数据</div>
          <div style={{ marginTop: 8, fontSize: 12 }}>与 Agent 对话或运行 Benchmark 后，数据将自动展示</div>
        </div>
      ) : null}
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
