from .base import BaseAgent


class FrontendAgent(BaseAgent):
    agent_id = "agent_frontend"
    name = "前端工程师"
    avatar = "🎨"
    role = "前端开发"
    style = "活泼，爱用 emoji"

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["组件", "页面", "界面", "ui", "样式", "布局", "设计稿"]):
            return self._code_reply()
        elif any(kw in msg for kw in ["宣传", "广告", "营销", "推广", "落地页", "landing"]):
            return self._promo_reply(message)
        elif any(kw in msg for kw in ["登录", "注册", "login"]):
            return self._login_reply()
        elif any(kw in msg for kw in ["bug", "报错", "问题", "修复"]):
            return "让我看看 👀 嗯找到问题了！是 CSS 层级的问题，已经修复了 ✅ 加了个 z-index 就搞定了～"
        elif any(kw in msg for kw in ["谢谢", "感谢", "不错"]):
            return "哈哈不客气！有前端需求随时找我，写 UI 我最在行了 💪✨"
        return "收到！前端这边我来搞定 🎨 有什么具体的设计要求吗？比如配色、布局风格之类的～"

    def _promo_reply(self, message: str) -> str:
        return (
            "宣传页面我来搞定！✨ 给你写个超酷的营销落地页 🎉\n\n"
            "```jsx\n"
            "import React from 'react';\n\n"
            "const PromoPage = () => (\n"
            "  <div className=\"promo-page\">\n"
            "    <header className=\"hero\">\n"
            "      <h1>🍦 巧乐兹 — 一口甜蜜，满心欢喜</h1>\n"
            "      <p>经典巧克力脆层 × 绵密冰淇淋</p>\n"
            "      <button className=\"cta\">立即尝鲜 →</button>\n"
            "    </header>\n"
            "    <section className=\"features\">\n"
            "      <div className=\"card\">🍫 浓郁巧克力</div>\n"
            "      <div className=\"card\">🥛 新鲜奶源</div>\n"
            "      <div className=\"card\">✨ 多种口味</div>\n"
            "    </section>\n"
            "    <footer>© 2026 巧乐兹 — 让每一口都是享受</footer>\n"
            "  </div>\n"
            ");\n"
            "```\n\n"
            "这是页面预览：\n\n"
            "[mockup:promo]\n\n"
            "配色用了暖色系渐变，突出甜蜜感 🍫 页面是响应式的，手机端也 OK～"
        )

    def _login_reply(self) -> str:
        return (
            "登录页搞定啦！✨\n\n"
            "```jsx\n"
            "import React, { useState } from 'react';\n\n"
            "const LoginPage = () => {\n"
            "  const [form, setForm] = useState({ username: '', password: '' });\n"
            "  const handleSubmit = (e) => {\n"
            "    e.preventDefault();\n"
            "    console.log('Login:', form);\n"
            "  };\n\n"
            "  return (\n"
            "    <form onSubmit={handleSubmit} className=\"login-form\">\n"
            "      <h2>欢迎回来 👋</h2>\n"
            "      <input placeholder=\"用户名\" value={form.username}\n"
            "        onChange={e => setForm({...form, username: e.target.value})} />\n"
            "      <input type=\"password\" placeholder=\"密码\" value={form.password}\n"
            "        onChange={e => setForm({...form, password: e.target.value})} />\n"
            "      <button type=\"submit\">登录</button>\n"
            "    </form>\n"
            "  );\n"
            "};\n"
            "```\n\n"
            "[mockup:login]\n\n"
            "简洁大气的登录页，加了微妙的阴影效果 🔥"
        )

    def _code_reply(self) -> str:
        return (
            "搞定！给你写了个组件 ✨\n\n"
            "```jsx\n"
            "import React, { useState } from 'react';\n\n"
            "const TodoApp = () => {\n"
            "  const [todos, setTodos] = useState([]);\n"
            "  const [input, setInput] = useState('');\n\n"
            "  const addTodo = () => {\n"
            "    if (!input.trim()) return;\n"
            "    setTodos([...todos, { id: Date.now(), text: input, done: false }]);\n"
            "    setInput('');\n"
            "  };\n\n"
            "  return (\n"
            "    <div className=\"todo-app\">\n"
            "      <h1>Todo List ✅</h1>\n"
            "      <input value={input} onChange={e => setInput(e.target.value)} />\n"
            "      <button onClick={addTodo}>添加</button>\n"
            "      {todos.map(t => <div key={t.id}>{t.text}</div>)}\n"
            "    </div>\n"
            "  );\n"
            "};\n"
            "```\n\n"
            "这是组件的 UI 预览：\n\n"
            "[mockup:todo]\n\n"
            "代码已经写好了，可以直接预览看看效果 🚀"
        )
