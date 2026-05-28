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
                next_node = router(state)
                logger.info(f"[StateGraph] Conditional transition: {current_node} -> {next_node}")
            elif current_node in self.edges:
                next_node = self.edges[current_node]
                logger.info(f"[StateGraph] Static transition: {current_node} -> {next_node}")
                
            current_node = next_node
            
        logger.info("[StateGraph] Finished execution")
        return state
