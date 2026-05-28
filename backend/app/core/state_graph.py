import asyncio
import logging
from typing import Callable, Any, Dict, List

logger = logging.getLogger("state_graph")

class StateGraph:
    """A lightweight, high-performance in-house StateGraph Engine
    inspired by LangGraph, tailored for AgentHub's WebSocket-driven DAG Canvas.
    """
    
    def __init__(self):
        self.nodes: Dict[str, Callable[[dict], Any]] = {}
        self.edges: Dict[str, str] = {}
        self.conditional_edges: Dict[str, Callable[[dict], str]] = {}
        
    def add_node(self, name: str, func: Callable[[dict], Any]):
        self.nodes[name] = func
        
    def add_edge(self, from_node: str, to_node: str):
        self.edges[from_node] = to_node
        
    def add_conditional_edge(self, from_node: str, router_func: Callable[[dict], str]):
        self.conditional_edges[from_node] = router_func
        
    async def run(self, initial_state: dict, conversation_id: str, stop_event: asyncio.Event = None) -> dict:
        from app.core.websocket import manager
        
        state = initial_state.copy()
        state.setdefault("completed_nodes", [])
        current_node = "agent_pm"
        
        # Reset all nodes to idle on start
        for nid in self.nodes:
            await manager.broadcast(conversation_id, {
                "type": "task_status",
                "conversation_id": conversation_id,
                "agent_id": nid,
                "status": "idle"
            })
            
        logger.info(f"[StateGraph] Starting execution from {current_node}")
        
        while current_node and current_node != "END":
            if stop_event and stop_event.is_set():
                logger.info("[StateGraph] Cancelled due to stop_event")
                break
                
            # 1. Update node status to active ('doing')
            await manager.broadcast(conversation_id, {
                "type": "task_status",
                "conversation_id": conversation_id,
                "agent_id": current_node,
                "status": "doing"
            })
            
            # 2. Execute Node
            node_func = self.nodes.get(current_node)
            if not node_func:
                logger.error(f"[StateGraph] Node '{current_node}' not found")
                break
                
            logger.info(f"[StateGraph] Executing node: {current_node}")
            try:
                # Node executes and returns a State Update dictionary
                update = await node_func(state)
                # Merge update into State
                state.update(update)
                if current_node not in state["completed_nodes"]:
                    state["completed_nodes"].append(current_node)
            except Exception as e:
                logger.error(f"[StateGraph] Error in node '{current_node}': {e}")
                # Set error status
                await manager.broadcast(conversation_id, {
                    "type": "task_status",
                    "conversation_id": conversation_id,
                    "agent_id": current_node,
                    "status": "failed"
                })
                break
                
            # 3. Update node status to complete ('done')
            await manager.broadcast(conversation_id, {
                "type": "task_status",
                "conversation_id": conversation_id,
                "agent_id": current_node,
                "status": "done"
            })
            
            # 4. Resolve next node
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
                logger.info(f"[StateGraph] Conditional transition: {current_node} -> {next_node}")
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                logger.info(f"[StateGraph] Static transition: {current_node} -> {next_node}")

            # 5. Human-in-the-loop Intercept Check
            if next_node and stop_event and not stop_event.is_set():
                import os
                import json
                
                # Load HIL settings safely
                hil_config_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hil_config.json")
                hil_settings = {"human_input_mode": "NEVER", "cooldown_steps": 2}
                try:
                    if os.path.exists(hil_config_path):
                        with open(hil_config_path, "r", encoding="utf-8") as f:
                            hil_settings = json.load(f)
                except Exception:
                    pass
                    
                human_input_mode = hil_settings.get("human_input_mode", "NEVER")
                cooldown_steps = hil_settings.get("cooldown_steps", 2)
                
                trigger = False
                if human_input_mode == "ALWAYS":
                    trigger = True
                elif human_input_mode == "COOLDOWN":
                    trigger = len(state.get("completed_nodes", [])) % cooldown_steps == 0
                    
                if trigger:
                    from app.tools.judge_tools import UserInteractionJudgeTool
                    from app.core.database import save_message
                    
                    current_agent_name = current_node.replace("agent_", "").upper()
                    next_agent_name = next_node.replace("agent_", "").upper()
                    next_desc = f"**{next_agent_name}**" if next_node != "END" else "**结束流程 (END)**"
                    
                    question = f"🎭 智能体 **{current_agent_name}** 已运行完毕。是否批准其结果并推进至 {next_desc}？"
                    options = [
                        "*Approve::批准并推进",
                        "Revise::输入修改反馈意见",
                        "Terminate::终止当前流程"
                    ]
                    
                    # Notify HIL starting
                    await manager.broadcast(conversation_id, {
                        "type": "message",
                        "conversation_id": conversation_id,
                        "sender": "system",
                        "content": {"text": f"⏳ Human-in-the-loop (HIL) 拦截已触发。等待人工审核..."},
                        "stream": False,
                    })
                    
                    tool = UserInteractionJudgeTool()
                    res = await tool.run({
                        "question": question,
                        "options": options,
                        "conversation_id": conversation_id
                    })
                    
                    decision = res.decision.strip()
                    if decision.lower() in ("approve", "yes", "y"):
                        logger.info("[HIL Intercept] Approved by user.")
                    elif decision.lower() in ("terminate", "end", "stop"):
                        logger.info("[HIL Intercept] Terminated by user.")
                        next_node = "END"
                    else:
                        # User provided custom feedback for revision
                        feedback = decision
                        logger.info(f"[HIL Intercept] Revision requested: {feedback}")
                        
                        # Save user feedback message to the chat
                        feedback_msg = f"🔄 [HIL 反馈] 针对 {current_agent_name} 的修改意见：\n{feedback}"
                        save_message(conversation_id, "user", {"text": feedback_msg}, streaming=False)
                        await manager.broadcast(conversation_id, {
                            "type": "message",
                            "conversation_id": conversation_id,
                            "sender": "user",
                            "content": {"text": feedback_msg},
                            "stream": False,
                        })
                        
                        # Set next_node back to current_node to re-run, and record feedback
                        state[f"{current_node}_feedback"] = feedback
                        next_node = current_node
                        
                        if current_node in state["completed_nodes"]:
                            state["completed_nodes"].remove(current_node)
                
            current_node = next_node
            
        logger.info("[StateGraph] Finished execution")
        return state
