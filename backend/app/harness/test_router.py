import asyncio
import os
import sys
import json

# Setup import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Reconfigure stdout to support utf-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from app.core.router import smart_router, check_port_alive, ModelRoute
from app.core.llm_client import llm_client

async def run_router_testing():
    print("====================================================")
    print("[START] Plan C: Multi-model Smart Routing Scheduler Test Suite")
    print("====================================================\n")

    # 1. Test port sniffing logic (check_port_alive)
    print("[Step 1] Testing port sniffer connection handling...")
    # Port 99999 is invalid/closed
    assert not check_port_alive("127.0.0.1", 9999, timeout=0.1)
    print("  SUCCESS: check_port_alive returned False for a closed port.")

    # Configure mock global llm settings
    llm_client.configure(
        provider="openai",
        api_key="sk-test-key-global",
        base_url="https://api.openai.com/v1",
        model="gpt-4o"
    )

    # 2. Test Smart Router configuration persistence
    print("\n[Step 2] Testing Smart Router persistence and serialization...")
    smart_router.auto_routing = True
    smart_router.manual_routes = {
        "agent_designer": {
            "provider": "openai",
            "base_url": "https://api.custom-designer.com/v1",
            "model": "designer-model",
            "api_key": "designer-key"
        }
    }
    smart_router.save_config()
    print("  SUCCESS: Router configuration saved to router_config.json.")

    # Re-instantiate or trigger load config to verify persistence
    smart_router._load_config()
    assert smart_router.auto_routing is True
    assert "agent_designer" in smart_router.manual_routes
    assert smart_router.manual_routes["agent_designer"]["model"] == "designer-model"
    print("  SUCCESS: Router configuration loaded from file successfully.")

    # 3. Test Routing Tiers (Plan C Auto Routing Decisions)
    print("\n[Step 3] Testing dynamic auto-routing tiers and level mappings...")
    
    # L1 Planning layer (agent_pm, agent_builder) -> global model (cloud)
    route_pm = smart_router.get_route_for_agent("agent_pm")
    assert route_pm.provider == "openai"
    assert route_pm.model == "gpt-4o"
    print("  SUCCESS: L1 Agent (agent_pm) routed to cloud flagship model (gpt-4o).")

    # L2 Coding layer (agent_frontend, agent_backend) -> local probed or fallback
    # If no local services are running on ports 11434 / 1234, it should heal and fallback to global
    route_frontend = smart_router.get_route_for_agent("agent_frontend")
    print(f"  Info: agent_frontend routed model is: {route_frontend.model} ({route_frontend.provider})")
    
    # 4. Test Manual routing overrides
    print("\n[Step 4] Testing Manual Routing overrides when auto routing is disabled...")
    smart_router.auto_routing = False
    
    # Override for agent_designer is active
    route_designer = smart_router.get_route_for_agent("agent_designer")
    assert route_designer.provider == "openai"
    assert route_designer.model == "designer-model"
    assert route_designer.base_url == "https://api.custom-designer.com/v1"
    print("  SUCCESS: Manual route override for agent_designer is applied successfully.")

    # Fallback to global if agent has no manual route defined
    route_tester = smart_router.get_route_for_agent("agent_tester")
    assert route_tester.model == "gpt-4o"
    print("  SUCCESS: Non-overridden agent (agent_tester) fallback to global verified.")

    # Reset router configuration to default
    smart_router.auto_routing = True
    smart_router.manual_routes = {}
    smart_router.save_config()

    print("\n====================================================")
    print("🎉 SUCCESS: Plan C Smart Router regression test suite finished with 100% PASS!")
    print("====================================================")

if __name__ == "__main__":
    asyncio.run(run_router_testing())
