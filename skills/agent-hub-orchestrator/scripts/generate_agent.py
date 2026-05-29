#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AgentHub Custom Agent Generator.
Scaffolds a new, structurally sound agent inheriting from BaseAgent and integrating
smoothly with our Pydantic-based strong typing system.
"""

import os
import sys

AGENT_TEMPLATE = '''import logging
from typing import AsyncGenerator
from app.agents.base import BaseAgent
from pydantic import BaseModel, Field

logger = logging.getLogger("{class_name}")

class {class_name}Input(BaseModel):
    task_desc: str = Field(description="任务的具体开发细节描述")
    strict_mode: bool = Field(default=True, description="是否开启防御性异常拦截校验")

class {class_name}(BaseAgent):
    agent_id = "{agent_id}"
    name = "{name}"
    avatar = "{avatar}"
    role = "{role}"
    style = "{style}"
    
    # 强类型参数契约校验绑定
    params_model = {class_name}Input
    
    system_prompt = """
你是 {name}，具备卓越的 {role} 能力。
请使用 {style} 的风格来指导和回答用户的问题。

【职责约束】
1. 你的每一次输出必须严谨、高内聚；
2. 如果触发工具调用，请务必使用完整闭合的标签。
"""

    def __init__(self):
        super().__init__()
        self.description = "{role}"

    async def stream_reply(self, message: str, context: list = None,
                           history: list = None, attachments: list = None,
                           conversation_id: str = "") -> AsyncGenerator[str, None]:
        """
        核心流式回复拦截管道。
        在此注入专属于 {name} 的高吞吐量推理和多路 AST 工具自愈拦截逻辑。
        """
        logger.info(f"[{self.name}] starting stream_reply inside conversation {conversation_id}")
        
        # 继承 BaseAgent 的高级多工具多轮 Tool-Calling 循环
        async for chunk in super().stream_reply(
            message=message,
            context=context,
            history=history,
            attachments=attachments,
            conversation_id=conversation_id
        ):
            yield chunk
'''

def main():
    print("=" * 60)
    print("AgentHub - Structural Custom Agent Scaffolder")
    print("=" * 60)

    # 1. Gather input parameters
    agent_id = input("1. Enter Agent ID (e.g. agent_architect): ").strip()
    if not agent_id.startswith("agent_"):
        agent_id = f"agent_{agent_id}"
        
    name = input("2. Enter Agent Name (e.g. Architect): ").strip()
    avatar = input("3. Enter Avatar Emoji (e.g. 🤖): ").strip()
    role = input("4. Enter Role Description (e.g. Design Architecture): ").strip()
    style = input("5. Enter Personality Style (e.g. Professional): ").strip()

    # Formulate Class Name
    clean_id = agent_id.replace("agent_", "")
    class_name = "".join(part.capitalize() for part in clean_id.split("_")) + "Agent"

    # Fill template
    code = AGENT_TEMPLATE.format(
        agent_id=agent_id,
        name=name,
        avatar=avatar,
        role=role,
        style=style,
        class_name=class_name
    )

    # Resolve destination path - 3 levels up to workspace root, then backend/app/agents/
    backend_agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend", "app", "agents"))
    if not os.path.exists(backend_agents_dir):
        print(f"[Error]: app/agents/ directory not found at {backend_agents_dir}!")
        return

    dest_file = os.path.join(backend_agents_dir, f"{clean_id}.py")
    
    if os.path.exists(dest_file):
        overwrite = input(f"[Warning]: File {os.path.basename(dest_file)} already exists! Overwrite? (y/n): ").strip().lower()
        if overwrite != "y":
            print("[Error]: Operation cancelled.")
            return

    try:
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(code)
            
        print("\n" + "=" * 60)
        print("SUCCESS: Custom Agent class scaffolded perfectly!")
        print(f"  - Class name:     {class_name}")
        print(f"  - Output file:    {dest_file}")
        print("  - Action Needed:  Import and register your new agent class inside")
        print("                    [app/services/agent_registry.py] to activate it!")
        print("=" * 60)
    except Exception as e:
        print(f"[Error] Error writing class file: {e}")

if __name__ == "__main__":
    main()
