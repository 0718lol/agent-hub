import asyncio
import json
import logging
import re
from app.core.database import get_messages, get_project_memory, save_memory_item
from app.core.llm_client import llm_client
from app.core.websocket import manager

logger = logging.getLogger("memory_engine")

async def trigger_background_reflection(conversation_id: str):
    """
    Asynchronously reviews conversation history and updates the white-box long-term memory.
    Runs non-blocking, then broadcasts updates to the active websocket.
    """
    if not llm_client.is_configured():
        logger.info("LLM Client is not configured. Skipping background memory reflection.")
        return

    try:
        # 1. Fetch conversation messages
        messages = get_messages(conversation_id, limit=40)
        if len(messages) < 2:
            return  # Not enough conversation turns to reflect upon

        history_str = ""
        for msg in messages:
            sender = msg.get("sender", "user")
            text = msg.get("content", {}).get("text", "") if isinstance(msg.get("content"), dict) else ""
            if text:
                history_str += f"{sender}: {text}\n"

        # 2. Fetch existing memory
        existing_mem = get_project_memory(conversation_id)
        existing_mem_simple = {k: v["value"] for k, v in existing_mem.items()}

        # 3. Formulate reflection system prompt
        system_prompt = f"""
你是有着极高架构视野与代码分析能力的“项目长期记忆架构师 (Long-term Memory Architect)”。
你的任务是深入审视最新的对话历史，并提炼、压缩出白盒项目记忆。

项目记忆由以下 4 个约定的 Key 组成（不能多也不能少）：
1. `tech_stack` (项目技术栈与接口契约): 归纳使用的技术、版本、自定义接口路由（API）、本地特定端口等开发规约。
2. `user_preference` (用户编码与设计偏好): 归纳用户明确指出或隐性流露的喜好（如“喜欢毛玻璃暗黑风”、“使用 Tailwind 进行三栏布局”、“后端必须进行严格的防御性异常处理”）。
3. `implemented_features` (已实现特性与模块列表): 归纳在此会话（项目）中已成功建立、修改的文件及具体功能点，避免后续 Agent 重复开发或污染文件。
4. `pending_todos` (遗留待开发任务与 Bug): 归纳后续规划、未完成的特性，或者讨论中悬而未决的代码 Bug。

请将历史背景与最新进展完美融合。请不要遗漏任何现存的关键记忆，但要根据最新对话完成增量更新、合并或整理（比如将已实现的 Todo 移入已实现特性中）。

【当前已存在的白盒记忆】：
{json.dumps(existing_mem_simple, ensure_ascii=False, indent=2)}

【最新的项目交互历史】：
---
{history_str}
---

【输出规范】：
请直接输出包含这四个 Keys 的 JSON 字典，不要添加任何铺垫、解释，禁止使用 ```json 等 Markdown 语法包裹！
示例输出格式：
{{
  "tech_stack": "React 18, FastAPI, SQLite 数据库, 探针已接入本地 Ollama (11434)",
  "user_preference": "喜欢深 slate 暗黑渐变背景与玻璃拟态卡片，编写 Python 代码时需带有详尽注释",
  "implemented_features": "- 完成方案 A 物理沙盒隔离化部署接口\\n- 前端 DeployPanel 增加「📂 打开本地部署文件夹」宽幅交互按钮",
  "pending_todos": "- 连接分层 Prompt 引擎与长期记忆表\\n- 在 SettingsPanel 面板绘制「💡 记忆控制台」以供用户人工覆写"
}}
"""

        # 4. Notify WebSocket that AI is reflecting
        await manager.broadcast(conversation_id, {
            "type": "reflecting",
            "conversation_id": conversation_id,
            "status": "active",
            "message": "🧠 本地探针：AI 记忆反思专家正在整理本轮对话并沉淀至白盒长期记忆库..."
        })

        # 5. Call LLM to synthesize memory
        response_text = ""
        async for chunk in llm_client.chat_stream([], system=system_prompt):
            response_text += chunk

        # Clean markdown code blocks if the LLM wrapped them
        clean_json = response_text.strip()
        if clean_json.startswith("```"):
            # Strip first line which might be ```json or ```
            clean_json = re.sub(r"^```\w*\n", "", clean_json)
            # Strip trailing ```
            clean_json = re.sub(r"\n```$", "", clean_json)
            clean_json = clean_json.strip()

        # 6. Parse JSON and upsert to database
        updated_data = json.loads(clean_json)
        keys_saved = []
        for key in ["tech_stack", "user_preference", "implemented_features", "pending_todos"]:
            if key in updated_data and updated_data[key]:
                save_memory_item(conversation_id, key, str(updated_data[key]), source="system")
                keys_saved.append(key)

        # 7. Broadcast reflected memory update
        fresh_memory = get_project_memory(conversation_id)
        await manager.broadcast(conversation_id, {
            "type": "reflecting",
            "conversation_id": conversation_id,
            "status": "done",
            "message": f"✅ AI 长期记忆沉淀完成！本次成功反思归纳了以下项目节点: {', '.join(keys_saved)}"
        })
        await manager.broadcast(conversation_id, {
            "type": "memory_reflected",
            "conversation_id": conversation_id,
            "memory": fresh_memory
        })

    except json.JSONDecodeError as jde:
        logger.error(f"Failed to parse reflected memory JSON: {jde}. Raw reply was: {response_text}")
        await manager.broadcast(conversation_id, {
            "type": "reflecting",
            "conversation_id": conversation_id,
            "status": "error",
            "message": "⚠️ 长期记忆提炼失败：大模型输出 JSON 格式解析异常。"
        })
    except Exception as e:
        logger.error(f"Error in background memory reflection: {e}")
        await manager.broadcast(conversation_id, {
            "type": "reflecting",
            "conversation_id": conversation_id,
            "status": "error",
            "message": f"⚠️ 长期记忆提炼出错: {str(e)[:100]}"
        })
