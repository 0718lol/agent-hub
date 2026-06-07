"""Browser agent tools for web browsing and documentation lookup.

Provides 3 tools:
- browser_open_url: Open a URL and return page title
- browser_get_content: Extract page text content
- browser_screenshot: Take a screenshot of current page
"""
import logging
import os
import uuid
from urllib.parse import urlparse

from app.tools.registry import AgentTool, register_tool

logger = logging.getLogger("browser_tools")

# URL safety configuration
BLOCKED_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "0x7f000001", "169.254.169.254"}  # nosec B104
BLOCKED_PROTOCOLS = {"file", "ftp", "data", "javascript", "vbscript"}
PRIVATE_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                    "172.30.", "172.31.", "192.168.", "169.254.")


def _is_safe_url(url: str) -> tuple:
    """Check if URL is safe to visit."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL"

    if not parsed.scheme or not parsed.hostname:
        return False, "Missing scheme or hostname"

    if parsed.scheme in BLOCKED_PROTOCOLS:
        return False, f"Blocked protocol: {parsed.scheme}"

    hostname = parsed.hostname.lower()

    if hostname in BLOCKED_HOSTS:
        return False, f"Blocked host: {hostname}"

    for prefix in PRIVATE_PREFIXES:
        if hostname.startswith(prefix):
            return False, f"Private IP range: {hostname}"

    return True, "OK"


def _get_browser_manager():
    """Get browser manager, initialize if needed."""
    from app.core.browser_manager import browser_manager
    return browser_manager


class BrowserOpenUrlTool(AgentTool):
    """Open a URL in the browser."""
    name = "browser_open_url"
    description = (
        "Open a URL in the browser. Use when you need to: "
        "read API documentation, check a website, look up solutions. "
        "Returns: page title, URL, and load status."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to open (must be a public website)",
            },
        },
        "required": ["url"],
    }

    async def execute(self, url: str = "") -> dict:
        """Open a URL and return page info."""
        if not url or not url.strip():
            return {"success": False, "error": "URL is required"}

        safe, reason = _is_safe_url(url)
        if not safe:
            return {"success": False, "error": f"URL blocked: {reason}"}

        try:
            manager = _get_browser_manager()
            page = await manager.new_page()

            try:
                response = await page.goto(url, wait_until="domcontentloaded")
                status = response.status if response else 0
                title = await page.title()

                for state in manager._pages:
                    if state.page == page:
                        state.url = url
                        state.last_used = __import__("time").time()
                        break

                logger.info(f"Opened: {url} (status={status})")
                return {"success": True, "title": title, "url": url, "status": status}
            except Exception as e:
                await manager.close_page(page)
                return {"success": False, "error": f"Failed to load: {str(e)[:200]}"}
        except Exception as e:
            return {"success": False, "error": f"Browser error: {str(e)[:200]}"}


class BrowserGetContentTool(AgentTool):
    """Extract text content from the current page."""
    name = "browser_get_content"
    description = (
        "Extract text content from the current browser page. "
        "Use after browser_open_url to get the page content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "selector": {
                "type": "string",
                "description": "CSS selector to extract specific content (optional)",
            },
        },
    }

    async def execute(self, selector: str = None) -> dict:
        """Extract page content."""
        try:
            manager = _get_browser_manager()
            page = await manager.get_current_page()

            if selector:
                element = await page.query_selector(selector)
                if not element:
                    return {"success": False, "error": f"Selector not found: {selector}"}
                text = await element.inner_text()
            else:
                text = await page.evaluate(
                    "() => {"
                    "document.querySelectorAll('script,style,nav,footer,aside,.ad,.sidebar')"
                    ".forEach(el => el.remove());"
                    "const m = document.querySelector('main,article,.content,.post,#content');"
                    "return m ? m.innerText : document.body.innerText;"
                    "}"
                )

            text = text.strip()
            if len(text) > 8000:
                text = text[:8000] + "\n... (truncated)"



            for state in manager._pages:
                if state.page == page:
                    state.last_used = __import__("time").time()
                    break

            logger.info(f"Extracted {len(text)} chars from {page.url}")
            return {"success": True, "content": text, "length": len(text), "url": page.url}
        except Exception as e:
            return {"success": False, "error": f"Content extraction failed: {str(e)[:200]}"}


class BrowserScreenshotTool(AgentTool):
    """Take a screenshot of the current page."""
    name = "browser_screenshot"
    description = "Take a screenshot of the current browser page."
    parameters = {"type": "object", "properties": {}}

    async def execute(self) -> dict:
        """Take a screenshot."""
        try:
            manager = _get_browser_manager()
            page = await manager.get_current_page()

            filename = f"screenshot_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(os.path.dirname(__file__), "..", "..", "data", "screenshots", filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            await page.screenshot(path=filepath, full_page=False)
            title = await page.title()
            url = page.url

            for state in manager._pages:
                if state.page == page:
                    state.last_used = __import__("time").time()
                    break

            logger.info(f"Screenshot saved: {filename}")
            return {"success": True, "path": filepath, "filename": filename, "title": title, "url": url}
        except Exception as e:
            return {"success": False, "error": f"Screenshot failed: {str(e)[:200]}"}


# Auto-register tools
register_tool(BrowserOpenUrlTool())
register_tool(BrowserGetContentTool())
register_tool(BrowserScreenshotTool())
