"""Web search tool — uses DuckDuckGo for zero-config internet search."""

import time
import logging
from typing import Optional
from pydantic import BaseModel, Field
from .registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("tool_web_search")


class WebSearchInput(BaseModel):
    query: str = Field(..., description="搜索关键词")
    max_results: Optional[int] = Field(5, description="最大返回结果数 (1-10)")


class WebSearchTool(AgentTool):
    name = "web_search"
    description = "搜索互联网获取最新信息、新闻、技术文档等"
    icon = "🔍"
    params_model = WebSearchInput
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数 (1-10)",
            },
        },
        "required": ["query"],
    }

    async def execute(self, params: dict) -> ToolResult:
        query = params.get("query", "").strip()
        if not query:
            return ToolResult(success=False, error="搜索关键词不能为空")

        max_results = min(max(int(params.get("max_results", 5)), 1), 10)
        start = time.time()

        try:
            from duckduckgo_search import DDGS
        except ImportError:
            return ToolResult(
                success=False,
                error="duckduckgo-search 未安装，请运行: pip install duckduckgo-search"
            )

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    })

            elapsed = int((time.time() - start) * 1000)

            if not results:
                return ToolResult(
                    success=True,
                    data={"results": [], "message": f"未找到'{query}'相关结果"},
                    usage={"time_ms": elapsed},
                )

            return ToolResult(
                success=True,
                data={"results": results, "query": query},
                usage={"time_ms": elapsed, "results_count": len(results)},
            )

        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return ToolResult(success=False, error=f"搜索失败: {str(e)}")


# Auto-register on import
register_tool(WebSearchTool())
