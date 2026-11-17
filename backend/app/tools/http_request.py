"""HTTP request tool -- allows agents to make HTTP calls to APIs."""

import ipaddress
import logging
import socket
import time
from urllib.parse import urljoin, urlparse

from .registry import AgentTool, ToolResult, register_tool

logger = logging.getLogger("tool_http_request")

# Maximum response body size to return (prevent huge payloads)
_MAX_BODY_SIZE = 8000
_MAX_STREAM_BYTES = 128 * 1024

# Maximum redirects to follow manually (SSRF-safe)
_MAX_REDIRECTS = 5

_LOOPBACK_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "[::1]",
    "[0:0:0:0:0:0:0:1]",
    "[::ffff:127.0.0.1]",
})

# Hosts that are always blocked (even if not in private IP ranges)
_BLOCKED_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",  # nosec B104 — SSRF blocklist entry, not a bind address
    "metadata.google.internal",
    "169.254.169.254",
    "[::1]",
    "[0:0:0:0:0:0:0:1]",
    "[::ffff:127.0.0.1]",
})


def _is_private_ip(addr: str) -> bool:
    """Check if an IP address string is private/loopback/link-local/reserved."""
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


def _try_parse_decimal_ip(hostname: str):
    """Try to parse hostname as a decimal/binary integer IP.

    Examples:
      2130706433 -> 127.0.0.1
      0x7f000001 -> 127.0.0.1

    Returns the dotted notation if parseable, else None.
    """
    try:
        val = int(hostname, 0)  # supports decimal, 0x hex, 0o octal, 0b binary
    except (ValueError, TypeError):
        return None

    # Try IPv4 (32-bit)
    if 0 <= val <= 0xFFFFFFFF:
        try:
            return str(ipaddress.IPv4Address(val))
        except (ValueError, OverflowError):
            pass

    # Try IPv6 (128-bit)
    if 0 <= val <= 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF:
        try:
            return str(ipaddress.IPv6Address(val))
        except (ValueError, OverflowError):
            pass

    return None


def validate_outbound_url(
    url: str,
    *,
    allow_loopback: bool = False,
    resolve_dns: bool = True,
) -> str | None:
    """Validate an outbound HTTP(S) URL against SSRF policies.

    When allow_loopback=True (e.g. administrator configuring local Ollama/OpenCode),
    loopback addresses (localhost / 127.0.0.1 / ::1) are permitted, while cloud
    metadata (169.254.169.254), 0.0.0.0, and RFC1918 LAN addresses remain blocked.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "URL 必须以 http:// 或 https:// 开头"
    raw_host = (parsed.hostname or "").strip()
    hostname = raw_host.strip("[]")

    if not hostname:
        return "URL has no hostname"

    lowered = hostname.lower()
    if allow_loopback and lowered in _LOOPBACK_HOSTS:
        return None

    if lowered in _BLOCKED_HOSTS or lowered.endswith((".internal", ".local")):
        return "安全策略禁止访问内部地址: " + hostname

    try:
        ip = ipaddress.ip_address(hostname)
        if allow_loopback and ip.is_loopback:
            return None
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            return "安全策略禁止访问私有/保留 IP: " + hostname
    except ValueError:
        pass

    parsed_ip = _try_parse_decimal_ip(hostname)
    if parsed_ip:
        try:
            ip = ipaddress.ip_address(parsed_ip)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
                return "安全策略禁止访问十进制 IP 绕过: " + hostname + " -> " + parsed_ip
        except ValueError:
            pass

    if not resolve_dns:
        return None

    try:
        resolved = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in resolved:
            resolved_ip = sockaddr[0]
            if allow_loopback:
                try:
                    if ipaddress.ip_address(resolved_ip).is_loopback:
                        continue
                except ValueError:
                    pass
            if _is_private_ip(resolved_ip):
                return "安全策略禁止访问解析到私有 IP 的域名: " + hostname + " -> " + resolved_ip
    except (socket.gaierror, OSError):
        pass  # DNS failure, let request fail naturally

    return None


def _validate_url_against_ssrf(url: str):
    """Validate a URL against SSRF policies.

    Returns None if the URL is safe, or an error message string if blocked.
    """
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return "URL 必须以 http:// 或 https:// 开头"
    return validate_outbound_url(
        url if parsed.scheme else f"http://{url}",
        allow_loopback=False,
    )


class HttpRequestTool(AgentTool):
    name = "http_request"
    description = "发送 HTTP 请求（GET/POST/PUT/DELETE），用于调用 API 或获取网页内容"
    icon = "\U0001f310"
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

        # SSRF protection: validate initial URL
        ssrf_error = _validate_url_against_ssrf(url)
        if ssrf_error:
            return ToolResult(success=False, error=ssrf_error)

        method = params.get("method", "GET").upper()
        if method not in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
            return ToolResult(success=False, error="不支持的 HTTP 方法: " + method)

        headers = params.get("headers", {})
        body = params.get("body")
        timeout = min(max(int(params.get("timeout", 15)), 1), 60)

        start = time.time()
        try:
            # Manual redirect handling: follow_redirects=False, validate each Location
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                current_url = url
                status_code = 0
                resp_headers: dict = {}
                raw_chunks: list[bytes] = []
                bytes_read = 0
                stream_capped = False

                for _ in range(_MAX_REDIRECTS + 1):
                    kwargs = {"headers": headers}
                    if body and method in ("POST", "PUT", "PATCH") and current_url == url:
                        try:
                            import json
                            json_body = json.loads(body)
                            kwargs["json"] = json_body
                        except (json.JSONDecodeError, TypeError):
                            kwargs["content"] = body

                    async with client.stream(method, current_url, **kwargs) as resp:
                        status_code = resp.status_code
                        resp_headers = dict(resp.headers)

                        if status_code in (301, 302, 303, 307, 308):
                            location = resp.headers.get("location")
                            if not location:
                                break
                            redirect_url = urljoin(current_url, location)
                            ssrf_error = _validate_url_against_ssrf(redirect_url)
                            if ssrf_error:
                                return ToolResult(
                                    success=False,
                                    error="重定向目标被安全策略拦截: " + redirect_url + " (" + ssrf_error + ")"
                                )
                            if status_code == 303:
                                method = "GET"
                            current_url = redirect_url
                            continue

                        raw_chunks.clear()
                        bytes_read = 0
                        stream_capped = False
                        async for chunk in resp.aiter_bytes():
                            remaining = _MAX_STREAM_BYTES - bytes_read
                            if remaining <= 0:
                                stream_capped = True
                                break
                            if len(chunk) > remaining:
                                raw_chunks.append(chunk[:remaining])
                                bytes_read += remaining
                                stream_capped = True
                                break
                            raw_chunks.append(chunk)
                            bytes_read += len(chunk)
                        break

                elapsed = int((time.time() - start) * 1000)
                decoded_text = b"".join(raw_chunks).decode("utf-8", errors="replace")
                resp_body = decoded_text[:_MAX_BODY_SIZE]
                truncated = stream_capped or len(decoded_text) > _MAX_BODY_SIZE

                return ToolResult(
                    success=True,
                    data={
                        "status_code": status_code,
                        "headers": resp_headers,
                        "body": resp_body,
                        "truncated": truncated,
                        "content_length": len(decoded_text),
                    },
                    usage={"time_ms": elapsed},
                )

        except httpx.TimeoutException:
            return ToolResult(success=False, error="请求超时 (" + str(timeout) + "s)")
        except httpx.ConnectError as e:
            return ToolResult(success=False, error="连接失败: " + str(e))
        except Exception as e:
            logger.error("HTTP request failed: %s", e)
            return ToolResult(success=False, error="请求失败: " + str(e))


# Auto-register on import
register_tool(HttpRequestTool())
