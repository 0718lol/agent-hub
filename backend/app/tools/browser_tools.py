"""CyberBrowser Tools — Sandboxed browser automation with vision feedback for agents."""

import os
import base64
import logging
import json
import asyncio
from typing import Dict, Any
from .registry import AgentTool, ToolResult, register_tool
from app.core.websocket import manager

logger = logging.getLogger("tool_browser_tools")

# DOM Minimizer JavaScript to inject into browser pages
DOM_MINIMIZER_JS = """
() => {
    const interactiveSelectors = [
        'a', 'button', 'input', 'select', 'textarea', 
        '[role="button"]', '[role="link"]', '[role="textbox"]',
        '[role="checkbox"]', '[role="combobox"]', '[role="listbox"]',
        '[onclick]', '[cursor="pointer"]'
    ];
    
    // Clean up previous highlights/badges if any
    const oldBadges = document.querySelectorAll('.cyberbrowser-badge');
    oldBadges.forEach(b => b.remove());

    const elements = document.querySelectorAll(interactiveSelectors.join(', '));
    const results = [];
    let idCounter = 1;

    elements.forEach(el => {
        // Filter out invisible elements
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;
        
        const id = idCounter++;
        
        // Get text/label description
        let text = el.innerText || el.placeholder || el.getAttribute('aria-label') || el.value || '';
        text = text.trim().substring(0, 100);
        
        // Compute center coordinates
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;
        
        results.push({
            id: id,
            tagName: el.tagName.toLowerCase(),
            role: el.getAttribute('role') || el.tagName.toLowerCase(),
            text: text,
            x: x,
            y: y,
            width: rect.width,
            height: rect.height
        });
        
        // Draw small visual number badges for multimodal LLM screenshots!
        const badge = document.createElement('div');
        badge.className = 'cyberbrowser-badge';
        badge.innerText = id;
        badge.style.position = 'absolute';
        badge.style.left = `${rect.left + window.scrollX}px`;
        badge.style.top = `${rect.top + window.scrollY}px`;
        badge.style.background = 'rgba(255, 0, 85, 0.95)';
        badge.style.color = '#fff';
        badge.style.fontSize = '10px';
        badge.style.fontWeight = 'bold';
        badge.style.padding = '1px 3px';
        badge.style.borderRadius = '3px';
        badge.style.border = '1px solid #fff';
        badge.style.boxShadow = '0 0 4px rgba(0,0,0,0.5)';
        badge.style.zIndex = '9999999';
        badge.style.pointerEvents = 'none';
        document.body.appendChild(badge);
    });
    
    return results;
}
"""


class BrowserSessionManager:
    """Manages persistent Playwright browser instances and conversation-level contexts."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.pages = {}
        # conversation_id -> {id: element_dict}
        self.elements_cache = {}

    async def get_page(self, conversation_id: str):
        if not self.playwright:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
        if conversation_id not in self.pages:
            context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800},
                device_scale_factor=1
            )
            page = await context.new_page()
            self.pages[conversation_id] = page
        return self.pages[conversation_id]

    async def close_all(self):
        for page in list(self.pages.values()):
            try:
                await page.close()
            except Exception:
                pass
        self.pages.clear()
        self.elements_cache.clear()
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self.browser = None
        self.playwright = None


browser_session_manager = BrowserSessionManager()


class BrowserActionTool(AgentTool):
    name = "browser_action"
    description = "以视觉验证和DOM元素扁平压缩的形式在赛博浏览器内打开、导航及模拟点击页面交互"
    icon = "🌐"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["goto", "click", "type", "scroll", "screenshot"],
                "description": "要执行的浏览器操作类型",
            },
            "url": {
                "type": "string",
                "description": "目标网址 (仅在 goto 动作时必填，允许使用本地物理沙盒地址或在线 URL)",
            },
            "element_id": {
                "type": "integer",
                "description": "要操作的目标元素数字 ID (在 click 和 type 动作时必填)",
            },
            "text": {
                "type": "string",
                "description": "要输入的内容 (仅在 type 动作时必填)",
            },
            "scroll_direction": {
                "type": "string",
                "enum": ["up", "down"],
                "description": "滚动方向 (仅在 scroll 动作时必填)",
            },
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
        },
        "required": ["action"],
    }

    async def execute(self, params: dict) -> ToolResult:
        action = params.get("action", "").strip()
        conv_id = params.get("conversation_id", "default")
        
        try:
            page = await browser_session_manager.get_page(conv_id)
        except Exception as e:
            return ToolResult(success=False, error=f"浏览器启动失败: {str(e)}")

        try:
            # 1. Dispatch action
            if action == "goto":
                url = params.get("url", "").strip()
                if not url:
                    return ToolResult(success=False, error=" goto 操作必须提供 url 参数")
                
                # Check for sandboxed local file resolution: e.g. "index.html" -> resolve to absolute file:/// path
                if not url.startswith(("http://", "https://", "file://")):
                    # Assume relative file in sandboxed workspace
                    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
                    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conv_id)
                    abs_path = os.path.abspath(os.path.join(sandbox_dir, url))
                    if not abs_path.startswith(sandbox_dir):
                        return ToolResult(success=False, error="路径越权：只允许加载当前沙盒目录内的文件")
                    url = "file:///" + abs_path.replace(os.sep, "/")

                logger.info(f"[CyberBrowser] Navigating to: {url}")
                await page.goto(url, wait_until="load", timeout=15000)

            elif action == "click":
                el_id = params.get("element_id")
                if el_id is None:
                    return ToolResult(success=False, error="click 操作必须提供 element_id")
                
                cache = browser_session_manager.elements_cache.get(conv_id, {})
                if el_id not in cache:
                    return ToolResult(success=False, error=f"未找到指定的元素 ID: {el_id}。请重新获取截图或验证页面状态。")
                
                el_data = cache[el_id]
                x, y = el_data["x"], el_data["y"]
                logger.info(f"[CyberBrowser] Clicking element {el_id} at coordinate ({x}, {y})")
                await page.mouse.click(x, y)
                await page.wait_for_timeout(1000)  # Wait briefly for transition

            elif action == "type":
                el_id = params.get("element_id")
                text = params.get("text", "")
                if el_id is None:
                    return ToolResult(success=False, error="type 操作必须提供 element_id")
                
                cache = browser_session_manager.elements_cache.get(conv_id, {})
                if el_id not in cache:
                    return ToolResult(success=False, error=f"未找到指定的元素 ID: {el_id}。")
                
                el_data = cache[el_id]
                x, y = el_data["x"], el_data["y"]
                logger.info(f"[CyberBrowser] Typing into element {el_id} at coordinate ({x}, {y}): '{text}'")
                await page.mouse.click(x, y)
                # Select all and delete before typing
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(text)
                await page.wait_for_timeout(500)

            elif action == "scroll":
                direction = params.get("scroll_direction", "down")
                scroll_amount = 400 if direction == "down" else -400
                logger.info(f"[CyberBrowser] Scrolling page: {direction}")
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                await page.wait_for_timeout(500)

            elif action == "screenshot":
                logger.info("[CyberBrowser] Generating screenshot verification")
                pass

            else:
                return ToolResult(success=False, error=f"不支持的浏览器操作类型: {action}")

            # 2. Extract simplified DOM elements and capture screenshot
            elements = await page.evaluate(DOM_MINIMIZER_JS)
            
            # Update local elements cache for clicks/inputs
            browser_session_manager.elements_cache[conv_id] = {el["id"]: el for el in elements}

            # Take screenshot and encode as Base64
            screenshot_bytes = await page.screenshot(type="png")
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            # 3. Stream Viewport live data to Frontend clients
            current_url = page.url
            await manager.broadcast(conv_id, {
                "type": "browser_viewport",
                "conversation_id": conv_id,
                "url": current_url,
                "screenshot": screenshot_b64,
                "elements": elements
            })

            # Format visual elements list for LLM context
            element_lines = []
            for el in elements:
                element_lines.append(f"  - [{el['id']}] {el['tagName']}: \"{el['text']}\" (Role: {el['role']}, bounds: size {int(el['width'])}x{int(el['height'])})")
            elements_list_str = "\n".join(element_lines) if element_lines else "  - (页面上目前没有可交互元素)"

            summary_text = (
                f"浏览器操作执行成功！\n"
                f"当前网址: {current_url}\n"
                f"--- 页面可交互元素列表 (ID 列表已在网页截图中以红底白字小标签标示) ---\n"
                f"{elements_list_str}\n"
                f"------------------------------------------------------------------"
            )

            return ToolResult(
                success=True,
                data={
                    "url": current_url,
                    "screenshot": screenshot_b64,
                    "elements": elements,
                    "message": summary_text
                }
            )

        except Exception as ex:
            logger.error(f"[CyberBrowser] Action '{action}' execution crash: {ex}")
            return ToolResult(success=False, error=f"浏览器操作期异常: {type(ex).__name__}: {str(ex)}")

# Auto-register on import
register_tool(BrowserActionTool())
