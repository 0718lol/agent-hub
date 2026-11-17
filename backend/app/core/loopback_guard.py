"""Loopback Host, Origin, and Fetch-Metadata guard for passwordless Personal Workbench mode."""
from __future__ import annotations

import urllib.parse

from app.core.config import settings


def _allowed_hosts() -> set[str]:
    hosts = {"127.0.0.1", "localhost", "::1", "test", "testserver"}
    configured = (settings.host or "").strip().strip("[]").lower()
    if configured and configured not in {"0.0.0.0", "::"}:  # nosec B104
        hosts.add(configured)
    for origin in settings.allowed_origins:
        parsed = urllib.parse.urlparse(origin)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    return hosts


def verify_loopback_headers(headers, *, is_api_or_write: bool) -> str | None:
    """Return an error reason if the request violates local loopback CSRF / DNS-rebinding rules."""
    allowed_hosts = _allowed_hosts()
    raw_host = (headers.get("host") or "").strip()
    if raw_host:
        try:
            parsed_host = urllib.parse.urlsplit(f"//{raw_host}")
            host_name = (parsed_host.hostname or "").lower()
        except ValueError:
            return "非法的 Host 请求头"
        if host_name not in allowed_hosts:
            return "拒绝非本机 Host 访问（防 DNS Rebinding）"

    if not is_api_or_write:
        return None

    sec_site = (headers.get("sec-fetch-site") or "").strip().lower()
    if sec_site == "cross-site":
        return "已拦截外部网页跨站请求"

    origin = (headers.get("origin") or "").strip()
    if origin:
        if origin.lower() == "null":
            return "已拦截未知来源请求"
        parsed_origin = urllib.parse.urlparse(origin)
        origin_host = (parsed_origin.hostname or "").lower()
        if parsed_origin.scheme not in {"http", "https"} or origin_host not in allowed_hosts:
            return "已拦截外部网页跨源请求"
    return None
