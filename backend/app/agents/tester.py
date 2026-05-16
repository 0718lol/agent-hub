from .base import BaseAgent


class TesterAgent(BaseAgent):
    agent_id = "agent_tester"
    name = "测试工程师"
    avatar = "🧪"
    role = "测试"
    style = "爱挑毛病"

    def _generate_reply(self, message: str, context: list = None) -> str:
        msg = message.lower()
        if any(kw in msg for kw in ["测试", "用例", "验证"]):
            return self._test_reply()
        elif any(kw in msg for kw in ["bug", "问题", "修复"]):
            return "我复现了这个问题。边界情况没处理：当输入为空字符串时会崩溃。另外并发请求下有数据竞争风险，建议加锁。"
        return "收到。我先看看代码，找找有没有边界情况没覆盖到。你们先别急着上线 😏"

    def _test_reply(self) -> str:
        return (
            "测试用例写好了，发现几个问题：\n\n"
            "**通过的用例：**\n"
            "✅ 创建 Todo — 正常输入\n"
            "✅ 删除 Todo — 存在的 ID\n"
            "✅ 获取列表 — 空列表\n\n"
            "**失败的用例：**\n"
            "❌ 创建 Todo — 输入为空时未校验\n"
            "❌ 删除 Todo — 不存在的 ID 返回 500 而非 404\n"
            "❌ 并发创建 — 同时提交 10 个请求有 2 个丢失\n\n"
            "```python\n"
            "import pytest\n"
            "from httpx import AsyncClient\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_create_todo_empty_input():\n"
            "    async with AsyncClient(app=app) as client:\n"
            "        resp = await client.post('/api/todos', json={'text': ''})\n"
            "        assert resp.status_code == 422\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_delete_nonexistent():\n"
            "    async with AsyncClient(app=app) as client:\n"
            "        resp = await client.delete('/api/todos/999')\n"
            "        assert resp.status_code == 404\n"
            "```\n\n"
            "建议修复后再进入下一轮测试。"
        )
