import React from 'react'
import { labelStyle, inputStyle, makeBtnStyle } from './sharedStyles'

export default function SecurityTab({
  securityToken, setSecurityToken, showToken, setShowToken, saving,
  authStatus, handleLogin, handleLogout, notificationStatus,
  testingNotification, handleTestNotification,
}) {
  const btnStyle = makeBtnStyle(saving)

  return (
    <>
      <div style={{
        padding: '10px 14px', borderRadius: 8, marginBottom: 20,
        background: 'rgba(245, 158, 11, 0.15)', border: '1px solid rgba(245, 158, 11, 0.2)',
        fontSize: 13, color: 'var(--orange)',
      }}>
        🔒 全局安全门禁与 API/WebSocket 会话密钥管理
      </div>

      <div style={{ padding: '16px', borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>浏览器安全会话</label>
        {authStatus.auth_mode === 'proxy' ? (
          <div style={{ fontSize: 13, color: authStatus.authenticated ? 'var(--green)' : 'var(--orange)' }}>
            {authStatus.authenticated ? `统一身份认证已生效 · ${authStatus.role || 'user'}` : '等待统一身份认证'}
          </div>
        ) : <>
          <div style={{ marginBottom: 16 }}>
          <label style={labelStyle}>访问密钥</label>
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
                background: 'var(--bg-tertiary)',
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
            密钥只在本次登录请求中发送，不会保存在浏览器脚本存储中。登录后使用最长 8 小时的 HttpOnly 会话 Cookie，JavaScript 无法读取该凭证。
          </p>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={handleLogin}
            disabled={saving || (authStatus.auth_required && !securityToken)}
            style={{ ...btnStyle, flex: 1, background: 'var(--accent)' }}
          >
            {authStatus.authenticated ? '刷新登录' : '登录'}
          </button>
          <button
            onClick={handleLogout}
            style={{ ...btnStyle, flex: 1, background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
          >
            退出会话
          </button>
          </div>
        </>}
      </div>

      <div style={{ padding: 16, borderRadius: 12, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
        <label style={{ ...labelStyle, fontWeight: 600, marginBottom: 12 }}>审批通知通道</label>
        {['slack', 'telegram'].map((channel) => (
          <div key={channel} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
            <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>{channel === 'slack' ? 'Slack' : 'Telegram'}</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 11, color: notificationStatus[channel] ? 'var(--green)' : 'var(--text-muted)' }}>
                {notificationStatus[channel] ? '已配置' : '未配置'}
              </span>
              <button type="button" onClick={() => handleTestNotification(channel)} disabled={!notificationStatus[channel] || testingNotification === channel}
                style={{ ...btnStyle, padding: '5px 10px', background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}>
                {testingNotification === channel ? '发送中...' : '测试'}
              </button>
            </div>
          </div>
        ))}
        <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 10 }}>
          通道凭证由服务端环境变量配置，页面只显示状态，不会返回 Token 或 Webhook URL。
        </p>
      </div>

      <div style={{ padding: '14px', borderRadius: 10, background: 'var(--bg-secondary)', border: '1px solid var(--border)', fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
        <b>💡 物理安全说明：</b>
        <br />
        - 后端未设置密钥时，接口鉴权会被关闭，适合仅限本机的开发环境；部署到局域网或公网前必须设置 <code>AGENTHUB_API_SECRET</code> 并限制访问来源。
        <br />
        - 非 Docker 终端命令执行（RCE防护）已自动接入脚本安全包裹隔离保护。
      </div>
    </>
  )
}
