import React from 'react'
import { Database, KeyRound, LogOut, Send, ShieldCheck, UserRound } from 'lucide-react'
import { labelStyle, inputStyle, makeBtnStyle } from './sharedStyles'

export default function SecurityTab({
  authStatus,
  currentPassword,
  setCurrentPassword,
  newPassword,
  setNewPassword,
  confirmPassword,
  setConfirmPassword,
  saving,
  handleChangePassword,
  handleLogout,
  legacyTenants,
  legacyLoading,
  notificationStatus,
  testingNotification,
  handleTestNotification,
}) {
  const btnStyle = makeBtnStyle(saving)
  const user = authStatus.user

  return (
    <>
      <div style={{ padding: 16, borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 14 }}>
          <ShieldCheck size={18} color="var(--green)" />
          <span style={{ ...labelStyle, fontWeight: 600, margin: 0 }}>账户安全</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <UserRound size={18} />
          <div>
            <div style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 600 }}>{user?.username || '当前账户'}</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{user?.is_admin ? '管理员账户' : '个人账户'}</div>
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          style={{ ...btnStyle, width: '100%', background: 'var(--bg-tertiary)', border: '1px solid var(--border)', color: 'var(--text-secondary)', display: 'flex', gap: 7, alignItems: 'center', justifyContent: 'center' }}
        >
          <LogOut size={15} />
          退出登录
        </button>
      </div>

      <form onSubmit={handleChangePassword} style={{ padding: 16, borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 14 }}>
          <KeyRound size={18} />
          <span style={{ ...labelStyle, fontWeight: 600, margin: 0 }}>修改密码</span>
        </div>
        <label style={{ ...labelStyle, display: 'block', marginBottom: 10 }}>
          当前密码
          <input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} style={{ ...inputStyle, width: '100%', marginTop: 6 }} required />
        </label>
        <label style={{ ...labelStyle, display: 'block', marginBottom: 10 }}>
          新密码
          <input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} style={{ ...inputStyle, width: '100%', marginTop: 6 }} minLength={8} required />
        </label>
        <label style={{ ...labelStyle, display: 'block', marginBottom: 14 }}>
          确认新密码
          <input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} style={{ ...inputStyle, width: '100%', marginTop: 6 }} minLength={8} required />
        </label>
        <button type="submit" disabled={saving} style={{ ...btnStyle, width: '100%', background: 'var(--accent)' }}>
          {saving ? '保存中...' : '更新密码'}
        </button>
      </form>

      {user?.is_admin && (
        <div style={{ padding: 16, borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 8 }}>
            <Database size={18} />
            <span style={{ ...labelStyle, fontWeight: 600, margin: 0 }}>旧租户恢复区</span>
          </div>
          <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5, margin: '0 0 12px' }}>
            旧数据保持隔离，不会自动并入任何账户。后续确认归属后再手动导入。
          </p>
          {legacyLoading && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>读取中...</div>}
          {!legacyLoading && legacyTenants.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>没有待恢复的旧租户</div>}
          {!legacyLoading && legacyTenants.map((tenant) => (
            <div key={tenant.legacy_tenant_id} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '9px 0', borderTop: '1px solid var(--border)' }}>
              <code style={{ fontSize: 11, overflowWrap: 'anywhere' }}>{tenant.legacy_tenant_id}</code>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{tenant.conversation_count} 个会话</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ padding: 16, borderRadius: 8, background: 'var(--bg-secondary)', border: '1px solid var(--border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12 }}>
          <Send size={18} />
          <span style={{ ...labelStyle, fontWeight: 600, margin: 0 }}>审批通知通道</span>
        </div>
        {['slack', 'telegram'].map((channel) => (
          <div key={channel} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
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
      </div>
    </>
  )
}
