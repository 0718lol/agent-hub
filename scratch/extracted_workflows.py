
    # 删除数据库记录
    delete_knowledge_doc(doc_id)
    return {"status": "ok", "message": "知识文档已删除"}


@app.post("/api/knowledge/query")
async def query_knowledge(body: dict):
    from app.core.rag_engine import rag_engine
    query = body.get("query", "")
    top_k = body.get("top_k", 5)
    if not query.strip():
        return {"status": "error", "message": "查询内容不能为空"}

    hits = rag_engine.query(query, top_k=top_k)
    return {"status": "ok", "results": hits}


# ---- Langflow Workflow Serialization & Compiler REST APIs ----

@app.get("/api/workflow/export/{conversation_id}")
async def export_workflow(conversation_id: str):
    """Export current workflow configuration, custom agents, and settings as JSON."""
    hil = get_hil_settings()
    custom_agents_data = []
    for ca in get_custom_agents():
        custom_agents_data.append(ca)
        
    workflow_data = {
        "conversation_id": conversation_id,
        "llm": {
            "provider": llm_client.provider,
            "base_url": llm_client.base_url,
            "model": llm_client.model,
            "temperature": llm_client.temperature,
            "max_tokens": llm_client.max_tokens,
        },
        "hil": hil,
        "custom_agents": custom_agents_data
    }
    return workflow_data


@app.post("/api/workflow/import")
async def import_workflow(body: dict):
    """Import and reconstruct workflow custom agents and settings from JSON config."""
    custom_agents = body.get("custom_agents", [])
    imported_count = 0
    for ca in custom_agents:
        aid = ca.get("agent_id")
        if aid:
            await agent_registry.register_custom_agent(ca)
            imported_count += 1
            
    hil = body.get("hil")
    if hil:
        save_hil_settings(hil)
        
    llm = body.get("llm")
    if llm:
        llm_client.configure(
            provider=llm.get("provider", "openai"),
            api_key=llm_client.api_key, # preserve current api key
            base_url=llm.get("base_url", ""),
            model=llm.get("model", ""),
            temperature=llm.get("temperature"),
            max_tokens=llm.get("max_tokens"),
        )
        _save_llm_config()
        
    return {"status": "ok", "imported_agents_count": imported_count}


@app.post("/api/workflow/compile/{conversation_id}")
async def compile_workflow(conversation_id: str):
    """Compile visually designed multi-agent team and guards into a standalone, 0-dependency Python script."""
    # Serialize agents data
    agents_str_dict = {}
    for aid, agent in AGENTS.items():
        agents_str_dict[aid] = {
            "name": agent.name,
            "avatar": agent.avatar,
            "role": agent.role,
            "style": agent.style,
            "system_prompt": agent.system_prompt,
            "description": agent.description
        }
        
    hil = get_hil_settings()
    
    # Standalone code template
    code_content = f"""# -*- coding: utf-8 -*-
\"\"\"
Generated Standalone StateGraph Agent Team - Compiler Plan L
Powered by AgentHub Visual-to-Code Compiler
\"\"\"

import asyncio
import json
import os
import re
import sys
import logging
import argparse
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("exported_team")

# ---- EMBEDDED STATEGRAPH ENGINE ----
class StateGraph:
    def __init__(self):
        self.nodes = {{}}
        self.edges = {{}}
        self.conditional_edges = {{}}
        self.guards = {{}}
        
    def add_node(self, name, func):
        self.nodes[name] = func
        
    def add_edge(self, from_node, to_node):
        self.edges[from_node] = to_node
        
    def add_conditional_edge(self, from_node, router_func):
        self.conditional_edges[from_node] = router_func

    def add_guard(self, node_name, guard_func, error_fallback_node=None):
        if node_name not in self.guards:
            self.guards[node_name] = []
        self.guards[node_name].append((guard_func, error_fallback_node))
        
    async def run(self, initial_state, human_input_mode="NEVER", cooldown_steps=2):
        state = initial_state.copy()
        state.setdefault("completed_nodes", [])
        current_node = "agent_pm"
        
        print("\\n=== [StateGraph] Starting Standalone Execution ===")
        
        while current_node and current_node != "END":
            print(f"\\n🟢 [StateGraph] Active Node: {{current_node.upper()}}")
            
            # Execute Node
            node_func = self.nodes.get(current_node)
            if not node_func:
                break
                
            if isinstance(node_func, StateGraph):
                update = await node_func.run(state, human_input_mode, cooldown_steps)
            else:
                update = await node_func(state)
                
            if update and isinstance(update, dict):
                state.update(update)
            if current_node not in state["completed_nodes"]:
                state["completed_nodes"].append(current_node)
                
            # Resolve Next Node
            next_node = None
            if current_node in self.conditional_edges:
                router = self.conditional_edges[current_node]
                if asyncio.iscoroutinefunction(router):
                    next_node = await router(state)
                else:
                    res = router(state)
                    if asyncio.iscoroutine(res):
                        next_node = await res
                    else:
                        next_node = res
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                
            # Transition Guards Check
            if next_node and next_node != "END" and next_node in self.guards:
                failed_fallback = None
                for guard, fallback in self.guards[next_node]:
                    if not guard(state):
                        failed_fallback = fallback or "agent_pm"
                        break
                if failed_fallback:
                    print(f"\\n⚠️ [状态守卫强拦截] 智能体 {{next_node.upper()}} 未满足准入前置条件！")
                    print(f"🔄 已安全自动重定向至纠偏节点 {{failed_fallback.upper()}}。")
                    next_node = failed_fallback
                    
            # Human-in-the-loop Intercept Check
            if next_node and (human_input_mode == "ALWAYS" or (human_input_mode == "COOLDOWN" and len(state.get("completed_nodes", [])) % cooldown_steps == 0)):
                next_desc = next_node.upper() if next_node != "END" else "结束流程 (END)"
                print(f"\\n⏳ [HIL 拦截] 智能体 {{current_node.upper()}} 运行完毕。是否批准其结果并推进至 {{next_desc}}？")
                print("  1. Approve (批准并推进)")
                print("  2. Terminate (终止流程)")
                print("  3. Feedback (输入修改意见)")
                
                choice = input("请选择 (1-3): ").strip()
                if choice == "2":
                    next_node = "END"
                elif choice == "3" or choice not in ("1", "2"):
                    feedback = input("请输入你的修改意见: ").strip() if choice == "3" else choice
                    print(f"🔄 [HIL 反馈] 注入修改意见，重跑 {{current_node.upper()}}...")
                    state[f"{{current_node}}_feedback"] = feedback
                    next_node = current_node
                    if current_node in state["completed_nodes"]:
                        state["completed_nodes"].remove(current_node)
                        
            current_node = next_node
            
        print("\\n=== [StateGraph] Finished Standalone Execution ===\\n")
        return state


# ---- EXPORTED CONFIGURATION ----
AGENTS = {json.dumps(agents_str_dict, ensure_ascii=False, indent=4)}
LLM_CONFIG = {{
    "provider": "{llm_client.provider}",
    "base_url": "{llm_client.base_url}",
    "model": "{llm_client.model}",
    "api_key": "{llm_client.api_key if llm_client.api_key else ''}"
}}

# ---- STANDALONE LLM CHAT CLIENT ----
class StandaloneLLMClient:
    async def chat_stream(self, messages, system=""):
        url = LLM_CONFIG["base_url"] or "https://api.openai.com/v1"
        key = LLM_CONFIG["api_key"]
        
        headers = {{
            "Authorization": f"Bearer {{key}}",
            "Content-Type": "application/json"
        }}
        
        payload_messages = []
        if system:
            payload_messages.append({{"role": "system", "content": system}})
        payload_messages.extend(messages)
        
        payload = {{
            "model": LLM_CONFIG["model"] or "gpt-4o",
            "messages": payload_messages,
            "stream": True
        }}
        
        target_url = url.rstrip("/") + "/chat/completions"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", target_url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        yield f"\\n[LLM API Error {{response.status_code}}]\\n"
                        return
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                text = chunk["choices"][0]["delta"].get("content", "")
                                if text:
                                    yield text
                            except Exception:
                                pass
        except Exception as e:
            yield f"\\n[API Call Exception: {{e}}]\\n"

standalone_llm = StandaloneLLMClient()

# ---- RUNNER HELPERS ----
async def stream_agent_reply(agent_id, user_text, context=""):
    agent = AGENTS[agent_id]
    print(f"🤖 **{{agent['name']}}** ({{agent['role']}}) 正在思考...")
    
    messages = []
    if context:
        messages.append({{"role": "user", "content": f"PM 任务拆解：\\n{{context}}\\n\\n需求：{{user_text}}"}} )
    else:
        messages.append({{"role": "user", "content": user_text}})
        
    full_prompt = agent["system_prompt"]
    
    full_response = ""
    async for chunk in standalone_llm.chat_stream(messages, system=full_prompt):
        sys.stdout.write(chunk)
        sys.stdout.flush()
        full_response += chunk
    print()
    
    assigned_agents = []
    for match in re.finditer(r'\\[assign:(\\w+)\\]', full_response):
        assigned_agents.append(match.group(1))
        
    return assigned_agents, full_response


# ---- STANDALONE DAG RUN DEFINITION ----
async def main_flow(task_text, human_input_mode, cooldown_steps):
    graph = StateGraph()
    
    async def run_pm(state):
        feedback = state.get("agent_pm_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        assigned, pm_res = await stream_agent_reply("agent_pm", prompt)
        return {{"pm_response": pm_res, "assigned_agents": assigned, "agent_pm_feedback": ""}}
        
    async def run_designer(state):
        feedback = state.get("agent_designer_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_designer", prompt, context=state.get("pm_response", ""))
        return {{"designer_response": res, "agent_designer_feedback": ""}}

    async def run_frontend(state):
        feedback = state.get("agent_frontend_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_frontend", prompt, context=state.get("pm_response", ""))
        return {{"frontend_response": res, "agent_frontend_feedback": ""}}

    async def run_backend(state):
        feedback = state.get("agent_backend_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_backend", prompt, context=state.get("pm_response", ""))
        return {{"backend_response": res, "agent_backend_feedback": ""}}

    async def run_tester(state):
        feedback = state.get("agent_tester_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_tester", prompt, context=state.get("pm_response", ""))
        return {{"tester_response": res, "agent_tester_feedback": ""}}

    async def run_devops(state):
        feedback = state.get("agent_devops_feedback", "")
        prompt = task_text
        if feedback:
            prompt = f"{{task_text}}\\n\\n🔄 人工反馈：\\n{{feedback}}"
        _, res = await stream_agent_reply("agent_devops", prompt, context=state.get("pm_response", ""))
        return {{"devops_response": res, "agent_devops_feedback": ""}}

    graph.add_node("agent_pm", run_pm)
    graph.add_node("agent_designer", run_designer)
    graph.add_node("agent_frontend", run_frontend)
    graph.add_node("agent_backend", run_backend)
    graph.add_node("agent_tester", run_tester)
    graph.add_node("agent_devops", run_devops)

    async def select_next_speaker(state):
        assigned = state.get("assigned_agents", [])
        candidates = assigned if assigned else ["agent_designer", "agent_frontend", "agent_backend", "agent_tester", "agent_devops"]
        remaining = [c for c in candidates if c not in state.get("completed_nodes", [])]
        
        if not remaining:
            return "END"
            
        # 💡 [Heuristic Lightweight Router Intercept (0 Latency, 0 Token Cost)]
        rule_speaker = None
        
        # Rule A: Single Choice
        if len(remaining) == 1:
            rule_speaker = remaining[0]
            print(f"\\n💡 [Heuristic Speaker Selection] Rule A: only one candidate remaining -> Selected '{{rule_speaker}}'")
            
        # Rule B: Linear SDLC Waterfall Inference
        else:
            completed = state.get("completed_nodes", [])
            last_completed = completed[-1] if completed else None
            
            if last_completed == "agent_pm":
                if "agent_designer" in remaining:
                    rule_speaker = "agent_designer"
                elif "agent_frontend" in remaining:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining:
                    rule_speaker = "agent_backend"
            elif last_completed == "agent_designer":
                if "agent_frontend" in remaining:
                    rule_speaker = "agent_frontend"
                elif "agent_backend" in remaining:
                    rule_speaker = "agent_backend"
            elif last_completed in ("agent_frontend", "agent_backend"):
                frontend_done = "agent_frontend" in completed or "agent_frontend" not in remaining
                backend_done = "agent_backend" in completed or "agent_backend" not in remaining
                if frontend_done and backend_done:
                    if "agent_tester" in remaining:
                        rule_speaker = "agent_tester"
                else:
                    other = "agent_backend" if last_completed == "agent_frontend" else "agent_frontend"
                    if other in remaining:
                        rule_speaker = other
            elif last_completed == "agent_tester":
                if "agent_devops" in remaining:
                    rule_speaker = "agent_devops"
            elif last_completed == "agent_devops":
                rule_speaker = "END"
                
            if rule_speaker:
                print(f"\\n💡 [Heuristic Speaker Selection] Rule B: SDLC Waterfall Inference -> Selected '{{rule_speaker}}'")
                
        if rule_speaker:
            return rule_speaker

        print("\\n🤖 [Speaker Selection] Non-deterministic state branching. Dispatching LLM Coordinator...")
        
        candidates_info = ""
        for cid in remaining:
            if cid in AGENTS:
                candidates_info += f"- ID: {{cid}}\\n  Name: {{AGENTS[cid]['name']}}\\n  Description: {{AGENTS[cid]['description']}}\\n\\n"
                
        system_prompt = f\"\"\"你是一个智能体群聊协调器 (Group Chat Coordinator)。
根据当前的对话历史和各个候选智能体 (Agents) 的角色描述，判断下一个最适合发言的智能体是谁。

候选智能体列表：
{{candidates_info}}

规则：
1. 只能从上面的候选智能体 ID 中选择一个，或者输出 "END" 表示对话已圆满结束（所有开发/部署任务均已妥善完成，没有遗留问题）。
2. 请只输出下一个发言的智能体 ID（例如 "agent_frontend"）或 "END"，不要附带任何其他解释、标点或 markdown 格式。
3. 必须客观分析当前对话进度。
\"\"\"
        user_prompt = f"请决定下一个最适合发言的智能体。"
        
        selected = ""
        try:
            async for chunk in standalone_llm.chat_stream([{{"role": "user", "content": user_prompt}}], system=system_prompt):
                selected += chunk
            selected = selected.strip().strip("'\\"`").strip()
        except Exception:
            selected = ""
            
        if selected in remaining:
            return selected
        elif selected == "END":
            return "END"
        else:
            return remaining[0]

    graph.add_conditional_edge("agent_pm", select_next_speaker)
    graph.add_conditional_edge("agent_designer", select_next_speaker)
    graph.add_conditional_edge("agent_frontend", select_next_speaker)
    graph.add_conditional_edge("agent_backend", select_next_speaker)
    graph.add_conditional_edge("agent_tester", select_next_speaker)
    graph.add_edge("agent_devops", "END")

    graph.add_guard("agent_devops", lambda s: "agent_tester" in s.get("completed_nodes", []), "agent_tester")
    graph.add_guard("agent_tester", lambda s: any(n in s.get("completed_nodes", []) for n in ["agent_frontend", "agent_backend"]), "agent_frontend")

    await graph.run({{}}, human_input_mode=human_input_mode, cooldown_steps=cooldown_steps)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Exported Standalone Agent Team")
    parser.add_argument("--task", type=str, required=True, help="Task prompt for the agent team")
    parser.add_argument("--hil", type=str, default="{hil.get('human_input_mode', 'NEVER')}", choices=["NEVER", "ALWAYS", "COOLDOWN"], help="Human-in-the-loop mode")
    parser.add_argument("--cooldown", type=int, default={hil.get('cooldown_steps', 2)}, help="Cooldown steps for HIL")
    
    args = parser.parse_args()
    
    asyncio.run(main_flow(args.task, args.hil, args.cooldown))
"""
    return {"status": "ok", "filename": "exported_team.py", "code": code_content}
