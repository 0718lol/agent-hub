import React from 'react'
import styles from './SettingsPanel.module.css'

export default function SecurityTab({
  isDark, securityToken, setSecurityToken, showToken, setShowToken, setMsg,
}) {
  return (
    <>
      <div className={styles.tabInfoBox} style={{
        background: isDark ? 'rgba(245,158,11,0.08)' : '#fef3c7', border: `1px solid ${isDark ? 'rgba(245,158,11,0.25)' : '#fde68a'}`,
        color: isDark ? '#fbbf24' : '#b45309',
      }}>
        🔒 全局安全门禁与 API/WebSocket 会话密钥管理
      </div>

      <div className={styles.securityCard}>
        <label className={styles.sectionTitle}>API Secret 密钥配置</label>
        
        <div style={{ marginBottom: 16 }}>
          <label className={styles.label}>全局访问密钥 (AGENTHUB_API_SECRET)</label>
          <div className={styles.tokenInputRow}>
            <input
              value={securityToken}
              onChange={(e) => setSecurityToken(e.target.value)}
              type={showToken ? "text" : "password"}
              placeholder="输入系统接口鉴权 Token..."
              className={styles.inputSecondary}
              style={{ flex: 1 }}
            />
            <button
              onClick={() => setShowToken(!showToken)}
              className={styles.toggleVisibilityBtn}
              type="button"
              title={showToken ? "隐藏密码" : "显示密码"}
            >
              {showToken ? '👁️' : '👁️‍🗨️'}
            </button>
          </div>
          <p className={styles.helpText}>
            密钥将保存在您的浏览器本地 LocalStorage 中。在开启后端 <code>AGENTHUB_API_SECRET</code> 保护时，前端所有的 Fetch 和 WebSocket 请求将自动注入此凭证以完成双向身份鉴权。
          </p>
        </div>

        <div className={styles.btnRow}>
          <button
            onClick={() => {
              localStorage.setItem('agenthub_api_secret', securityToken);
              setMsg('安全凭证保存成功！所有 API 与实时会话已安全对齐。');
            }}
            className={styles.saveBtn}
            style={{ flex: 1 }}
          >
            保存密钥
          </button>
          <button
            onClick={() => {
              localStorage.removeItem('agenthub_api_secret');
              setSecurityToken('');
              setMsg('安全凭证已成功清除，浏览器当前处于无凭证访问状态。');
            }}
            className={styles.saveBtn}
            style={{ flex: 1, background: 'var(--bg-secondary)', border: '1px solid var(--border)', color: 'var(--text-primary)' }}
          >
            清除密钥
          </button>
        </div>
      </div>

      <div className={styles.securityNote}>
        <b>💡 物理安全说明：</b>
        <br />
        - 当密钥清除且后端未设置密钥时，系统默认激活 <b>Localhost 纯物理环回防火墙</b>，阻止任何外界物理设备访问此编排系统。
        <br />
        - 非 Docker 终端命令执行（RCE防护）已自动接入脚本安全包裹隔离保护。
      </div>
    </>
  )
}
