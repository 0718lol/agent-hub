import React from 'react'

export default function SecurityTab({
  isDark, securityToken, setSecurityToken, showToken, setShowToken, setMsg,
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

  const btnStyle = {
    width: '100%',
    padding: '12px',
    borderRadius: 10,
    background: '#4f46e5',
    border: 'none',
    color: 'white',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all 0.2s',
  }

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: isDark ? 'rgba(245,158,11,0.08)' : '#fef3c7', border: `1px solid ${isDark ? 'rgba(245,158,11,0.25)' : '#fde68a'}`,
        fontSize: 13, color: isDark ? '#fbbf24' : '#b45309',
      }}>
        🔒 全局安全门禁与 API/WebSocket 会话密钥管理
      </div>

      <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>API Secret 密钥配置</label>
        
        <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>全局访问密钥 (AGENTHUB_API_SECRET)</label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              value={securityToken}
              onChange={(e) => setSecurityToken(e.target.value)}
              type={showToken ? "text" : "password"}
              placeholder="输入系统接口鉴权 Token..."
              style={{ ...inputStyle, flex: 1 }}
            />
            <button
              onClick={() => setShowToken(!showToken)}
              style={{
                padding: '10px 12px',
                background: 'var(--bg-secondary)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                cursor: 'pointer',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
              type="button"
              title={showToken ? "隐藏密码" : "显示密码"}
            >
              {showToken ? '👁️' : '👁️‍🗨️'}
            </button>
          </div>
          <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6, lineHeight: 1.4 }}>
            密钥将保存在您的浏览器本地 LocalStorage 中。在开启后端 <code>AGENTHUB_API_SECRET</code> 保护时，前端所有的 Fetch 和 WebSocket 请求将自动注入此凭证以完成双向身份鉴权。
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => {
              localStorage.setItem('agenthub_api_secret', securityToken);
              setMsg('安全凭证保存成功！所有 API 与实时会话已安全对齐。');
            }}
            style={{ ...btnStyle, flex: 1, background: '#4f46e5' }}
          >
            保存密钥
          </button>
          <button
            onClick={() => {
              localStorage.removeItem('agenthub_api_secret');
              setSecurityToken('');
              setMsg('安全凭证已成功清除，浏览器当前处于无凭证访问状态。');
            }}
            style={{ ...btnStyle, flex: 1, background: 'var(--bg-secondary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
          >
            清除密钥
          </button>
        </div>
      </div>

      <div style={{ padding: '14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.5 }}>
        <b>💡 物理安全说明：</b>
        <br />
        - 当密钥清除且后端未设置密钥时，系统默认激活 <b>Localhost 纯物理环回防火墙</b>，阻止任何外界物理设备访问此编排系统。
        <br />
        - 非 Docker 终端命令执行（RCE防护）已自动接入脚本安全包裹隔离保护。
      </div>
    </>
  )
}
