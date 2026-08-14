import React, { useEffect, useState } from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import AuthPage from './components/Auth/AuthPage.jsx'
import './styles/global.css'

// 新 Coze 主题
import './styles/theme-coze-light.css'
import './styles/theme-coze-dark.css'

// 初始化 data-theme 属性
import { useThemeStore } from './stores/themeStore'
const initialTheme = useThemeStore.getState().theme
document.documentElement.setAttribute('data-theme', initialTheme)

// 订阅 store 变更，同步到 DOM
useThemeStore.subscribe((state) => {
  document.documentElement.setAttribute('data-theme', state.theme)
})

const nativeFetch = window.fetch.bind(window)
window.fetch = async (...args) => {
  const response = await nativeFetch(...args)
  const target = typeof args[0] === 'string' ? args[0] : args[0]?.url || ''
  if (response.status === 401 && !target.includes('/api/auth/')) {
    window.dispatchEvent(new Event('agenthub:auth-required'))
  }
  return response
}

function Root() {
  const [state, setState] = useState({ loading: true, user: null })

  useEffect(() => {
    fetch('/api/auth/status')
      .then((response) => response.json())
      .then((data) => setState({ loading: false, user: data.authenticated ? data.user : null }))
      .catch(() => setState({ loading: false, user: null }))
    const requireAuth = () => setState({ loading: false, user: null })
    window.addEventListener('agenthub:auth-required', requireAuth)
    return () => window.removeEventListener('agenthub:auth-required', requireAuth)
  }, [])

  if (state.loading) return <div className="auth-loading">AgentHub</div>
  if (!state.user) return <AuthPage onAuthenticated={(user) => setState({ loading: false, user })} />
  return <App currentUser={state.user} />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><ErrorBoundary><Root /></ErrorBoundary></React.StrictMode>,
)
