from .base import BaseAgent


class FrontendAgent(BaseAgent):
    agent_id = "agent_frontend"
    name = "前端工程师"
    avatar = "🎨"
    role = "前端开发"
    style = "活泼，爱用 emoji"

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["组件", "页面", "界面", "ui", "样式"]):
            return self._code_reply()
        elif any(kw in msg for kw in ["bug", "报错", "问题", "修复"]):
            return "让我看看 👀 嗯找到问题了！是 CSS 层级的问题，已经修复了 ✅ 加了个 z-index 就搞定了～"
        elif any(kw in msg for kw in ["谢谢", "感谢", "不错"]):
            return "哈哈不客气！有前端需求随时找我，写 UI 我最在行了 💪✨"
        return "收到！前端这边我来搞定 🎨 有什么具体的设计要求吗？比如配色、布局风格之类的～"

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
