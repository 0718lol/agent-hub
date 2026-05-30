import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './styles/global.css'

// 全局 API Token 拦截注入层 (Fetch Interceptor)
const originalFetch = window.fetch;
window.fetch = async (url, options = {}) => {
  const token = localStorage.getItem('agenthub_api_secret');
  const urlStr = typeof url === 'string' ? url : (url instanceof URL ? url.toString() : '');
  if (token && (urlStr.startsWith('/api') || urlStr.includes('/api/'))) {
    if (options.headers instanceof Headers) {
      options.headers.set('Authorization', `Bearer ${token}`);
    } else {
      options.headers = {
        ...options.headers,
        'Authorization': `Bearer ${token}`
      };
    }
  }
  return originalFetch(url, options);
};

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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
