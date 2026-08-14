import React, { useState } from 'react'
import { ArrowRight, Bot, LockKeyhole, UserRound } from 'lucide-react'

async function submitCredentials(mode, username, password) {
  const response = await fetch(`/api/auth/${mode}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || '请求失败，请稍后重试')
  return data
}

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setError('')
    if (mode === 'register' && password !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }
    setSubmitting(true)
    try {
      const data = await submitCredentials(mode, username.trim(), password)
      onAuthenticated(data.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  const switchMode = (nextMode) => {
    setMode(nextMode)
    setError('')
    setPassword('')
    setConfirmPassword('')
  }

  return (
    <main className="auth-shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="auth-brand">
          <span className="auth-brand-mark"><Bot size={24} /></span>
          <div><h1 id="auth-title">AgentHub</h1><p>多 Agent 协作平台</p></div>
        </div>
        <div className="auth-segments" role="tablist" aria-label="账户入口">
          <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>登录</button>
          <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>注册</button>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label><span>用户名</span><div className="auth-input-wrap"><UserRound size={17} /><input autoComplete="username" autoFocus value={username} onChange={(event) => setUsername(event.target.value)} placeholder="2-32 个字符" required /></div></label>
          <label><span>密码</span><div className="auth-input-wrap"><LockKeyhole size={17} /><input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位" minLength={8} required /></div></label>
          {mode === 'register' && <label><span>确认密码</span><div className="auth-input-wrap"><LockKeyhole size={17} /><input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="再次输入密码" minLength={8} required /></div></label>}
          {error && <div className="auth-error" role="alert">{error}</div>}
          <button className="auth-submit" type="submit" disabled={submitting}><span>{submitting ? '请稍候' : mode === 'login' ? '进入 AgentHub' : '创建账户'}</span>{!submitting && <ArrowRight size={17} />}</button>
        </form>
      </section>
    </main>
  )
}
