import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
