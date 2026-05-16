from .base import BaseAgent


class BackendAgent(BaseAgent):
    agent_id = "agent_backend"
    name = "后端工程师"
    avatar = "⚙️"
    role = "后端开发"
    style = "严谨务实"
    system_prompt = (
        "你是 AgentHub 的后端工程师，头像是⚙️。你说话严谨务实，注重代码质量和架构设计。"
        "你擅长 Python、FastAPI、数据库设计、RESTful API。"
        "\n\n规则："
        "\n- 用户要求写接口/API/后端时，输出完整的 Python 代码（用 ```python 代码块）。"
        "\n- 代码要包含完整的路由、模型定义、错误处理。"
        "\n- 提醒用户注意并发、数据一致性、环境变量等生产环境问题。"
        "\n- 回复简洁专业，不要废话。"
    )

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["api", "接口", "数据库", "后端"]):
            return self._api_reply()
        elif any(kw in msg for kw in ["bug", "报错", "问题"]):
            return "已排查，是数据库连接池耗尽导致的。已调整最大连接数并添加了连接回收机制。请确认环境变量 DB_POOL_SIZE 是否正确配置。"
        elif any(kw in msg for kw in ["谢谢", "感谢"]):
            return "不客气。接口文档已更新，注意并发场景下的幂等性处理。"
        return "收到需求。我来设计数据模型和 API 接口，预计很快出方案。有什么特殊的数据存储需求吗？"

    def _api_reply(self) -> str:
        return (
            "接口已就绪，以下是 API 设计：\n\n"
            "```python\n"
            "from fastapi import FastAPI, HTTPException\n"
            "from pydantic import BaseModel\n"
            "from typing import List\n\n"
            "app = FastAPI()\n\n"
            "class TodoItem(BaseModel):\n"
            "    id: int\n"
            "    text: str\n"
            "    done: bool = False\n\n"
            "todos: List[TodoItem] = []\n\n"
            "@app.get('/api/todos')\n"
            "async def get_todos():\n"
            "    return todos\n\n"
            "@app.post('/api/todos')\n"
            "async def create_todo(item: TodoItem):\n"
            "    todos.append(item)\n"
            "    return item\n\n"
            "@app.put('/api/todos/{todo_id}')\n"
            "async def update_todo(todo_id: int, item: TodoItem):\n"
            "    for i, t in enumerate(todos):\n"
            "        if t.id == todo_id:\n"
            "            todos[i] = item\n"
            "            return item\n"
            "    raise HTTPException(status_code=404)\n"
            "```\n\n"
            "接口文档已自动生成，访问 `/docs` 查看。注意并发场景下的数据一致性。"
        )
