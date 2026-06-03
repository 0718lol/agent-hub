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
        "\n\n【铁律 — 违反任何一条回复作废】"
        "\n1. 根据任务类型选择合适的输出格式："
        "\n   - API/接口 → ```python 代码块（FastAPI/Flask）"
        "\n   - 数据库 → ```sql 代码块"
        "\n   - 配置 → ```yaml 或 ```json 代码块"
        "\n   - 部署 → ```bash 或 ```dockerfile 代码块"
        "\n2. 代码必须是完整可运行的（import + 定义 + 路由）"
        "\n3. 不要问用户任何问题，直接实现"
        "\n4. 如果信息不足，用最合理的默认值补全（如 SQLite + FastAPI）"
        "\n\n输出格式："
        "\n[thinking]分析需求...[/thinking]"
        "\n2-3 句话摘要"
        "\n```（语言标记）"
        "\n（完整代码）"
        "\n```"
        "\n[assign:agent_tester]"
        "\n\n【ask_user 工具】仅在必须用户决策的关键分歧时使用一次。"
        "\n若用户消息以 [ask_user_reply] 开头，基于答案继续推进，不要重复提问。"
    )

    def _generate_reply(self, message: str, context: list | None = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["api", "接口", "数据库", "后端"]):
            return self._api_reply()
        elif any(kw in msg for kw in ["bug", "报错", "问题"]):
            return "已排查，是数据库连接池耗尽导致的。已调整最大连接数并添加了连接回收机制。请确认环境变量 DB_POOL_SIZE 是否正确配置。"
        elif any(kw in msg for kw in ["谢谢", "感谢"]):
            return "不客气。接口文档已更新，注意并发场景下的幂等性处理。"
        return (
            "收到需求。正在设计 RESTful API 和数据模型。\n\n"
            "```python\n"
            "from fastapi import FastAPI\n"
            "from pydantic import BaseModel\n\n"
            "app = FastAPI()\n\n"
            "class Item(BaseModel):\n"
            "    name: str\n"
            '    description: str = ""\n\n'
            '@app.post("/api/items")\n'
            "async def create_item(item: Item):\n"
            '    return {"status": "created", "item": item}\n\n'
            '@app.get("/api/items")\n'
            "async def list_items():\n"
            '    return {"items": []}\n'
            "```\n\n"
            "[assign:agent_tester]"
        )

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
