"""HTTP request tool — allows agents to make HTTP calls to APIs."""

import time
import logging
from .registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("tool_http_request")

# Maximum response body size to return (prevent huge payloads)
_MAX_BODY_SIZE = 8000


class HttpRequestTool(AgentTool):
    name = "http_request"
    description = "发送 HTTP 请求（GET/POST/PUT/DELETE），用于调用 API 或获取网页内容"
    icon = "🌐"
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "请求 URL（必须以 http:// 或 https:// 开头）",
            },
            "method": {
                "type": "string",
                "description": "HTTP 方法: GET, POST, PUT, DELETE",
            },
            "headers": {
                "type": "object",
                "description": "请求头（键值对）",
            },
            "body": {
                "type": "string",
                "description": "请求体（JSON 字符串或纯文本）",
            },
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒），默认 15",
            },
        },
        "required": ["url"],
    }

    async def execute(self, params: dict) -> ToolResult:
        import httpx

        url = params.get("url", "").strip()
        if not url:
            return ToolResult(success=False, error="URL 不能为空")
        if not url.startswith(("http://", "https://")):
            return ToolResult(success=False, error="URL 必须以 http:// 或 https:// 开头")

        method = params.get("method", "GET").upper()
        if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
            return ToolResult(success=False, error=f"不支持的 HTTP 方法: {method}")

        headers = params.get("headers", {})
        body = params.get("body", None)
        timeout = min(max(int(params.get("timeout", 15)), 1), 60)

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                kwargs = {"headers": headers}
                if body and method in ("POST", "PUT", "PATCH"):
                    # Try to send as JSON if possible
                    try:
                        import json
                        json_body = json.loads(body)
                        kwargs["json"] = json_body
                    except (json.JSONDecodeError, TypeError):
                        kwargs["content"] = body

                resp = await client.request(method, url, **kwargs)

            elapsed = int((time.time() - start) * 1000)

            # Truncate body if too large
            resp_body = resp.text[:_MAX_BODY_SIZE]
            truncated = len(resp.text) > _MAX_BODY_SIZE

            return ToolResult(
                success=True,
                data={
                    "status_code": resp.status_code,
                    "headers": dict(resp.headers),
                    "body": resp_body,
                    "truncated": truncated,
                    "content_length": len(resp.text),
                },
                usage={"time_ms": elapsed},
            )

        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"请求超时 ({timeout}s)")
        except httpx.ConnectError as e:
            return ToolResult(success=False, error=f"连接失败: {str(e)}")
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            return ToolResult(success=False, error=f"请求失败: {str(e)}")


# Auto-register on import
register_tool(HttpRequestTool())
