import sys
import os
import json
import asyncio
import traceback

# Setup import path to make 'app' discoverable
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.llm_client import llm_client
from app.tools.judge_tools import QualityJudgeTool, ComplexityJudgeTool, AlignmentJudgeTool

async def handle_request(req: dict) -> dict:
    method = req.get("method")
    params = req.get("params", {})
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "agenthub-judges",
                    "version": "1.0.0"
                }
            },
            "id": req_id
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": "agenthub_quality_judge",
                        "description": "评估代码质量。结合 Python 静态语法检查与 LLM 逻辑、健壮性及架构评分（0-100 分），提供完整的评审意见。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "原始需求或开发任务描述"},
                                "solution": {"type": "string", "description": "开发出的代码方案或实现内容"}
                            },
                            "required": ["task", "solution"]
                        }
                    },
                    {
                        "name": "agenthub_complexity_judge",
                        "description": "评估任务复杂度。分析技术深度、方案多样性、实现难度与潜在风险，返回维度评分（0-100 分）和分析理由。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "user_input": {"type": "string", "description": "需要评估的开发任务或业务需求"}
                            },
                            "required": ["user_input"]
                        }
                    },
                    {
                        "name": "agenthub_alignment_judge",
                        "description": "评估代码实现与原始需求的对齐度。检查功能覆盖率、技术栈匹配度及是否存在未授权的偏离倾向（0-100 分）。",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "原始需求或任务规范说明"},
                                "solution": {"type": "string", "description": "开发出的代码方案或实现内容"}
                            },
                            "required": ["task", "solution"]
                        }
                    }
                ]
            },
            "id": req_id
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        # Ensure the LLM client is configured
        if not llm_client.is_configured():
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "llm_config.json"))
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        llm_client.configure(
                            provider=cfg.get("provider", "openai"),
                            api_key=cfg.get("api_key", ""),
                            base_url=cfg.get("base_url", ""),
                            model=cfg.get("model", ""),
                            temperature=cfg.get("temperature", 0.5),
                            max_tokens=cfg.get("max_tokens", 8192)
                        )
                except Exception:
                    pass

        try:
            if tool_name == "agenthub_quality_judge":
                tool = QualityJudgeTool()
                res = await tool.run(arguments, llm_client=llm_client)
            elif tool_name == "agenthub_complexity_judge":
                tool = ComplexityJudgeTool()
                res = await tool.run(arguments, llm_client=llm_client)
            elif tool_name == "agenthub_alignment_judge":
                tool = AlignmentJudgeTool()
                res = await tool.run(arguments, llm_client=llm_client)
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: tool {tool_name}"
                    },
                    "id": req_id
                }

            # Format JudgeResult to standard MCP content output
            score_text = f"【决策结论】: {res.decision}\n【综合得分】: {res.score}分\n【评审结论】: {res.reason}"
            signals_text = f"\n【维度数据】: {json.dumps(res.signals, ensure_ascii=False, indent=2)}"
            
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"{score_text}\n{signals_text}"
                        }
                    ]
                },
                "id": req_id
            }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "result": {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error executing tool {tool_name}: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                        }
                    ]
                },
                "id": req_id
            }

    else:
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            },
            "id": req_id
        }

async def main():
    # Make sure stdin/stdout are using utf-8 without Windows-specific line ending conversions
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8')
    
    # Run standard input reading loop
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        line_str = line.decode("utf-8").strip()
        if not line_str:
            continue
        try:
            req = json.loads(line_str)
            resp = await handle_request(req)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal JSON-RPC parse error: {str(e)}"
                },
                "id": None
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
