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
                "description": "要操作的目标元素数字 ID (在 click 和 type 动作时可选，优先使用 ID)",
            },
            "visual_description": {
                "type": "string",
                "description": "要操作的目标元素的自然语言视觉描述（当 element_id 缺失时必填，开启视觉定位与模糊自愈）",
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
        
        vision_used = False
        failover_used = False
        resolved_msg = ""

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

            elif action in ("click", "type"):
                text = params.get("text", "")
                if action == "type" and not text:
                    return ToolResult(success=False, error="type 操作必须提供 text 参数")

                try:
                    x, y, resolved_msg, vision_used, failover_used = await self._resolve_coordinates(page, params, conv_id)
                except ValueError as ve:
                    return ToolResult(success=False, error=str(ve))

                if action == "click":
                    logger.info(f"[CyberBrowser] Clicking at coordinate ({x:.2f}, {y:.2f}) resolved by {resolved_msg}")
                    await page.mouse.click(x, y)
                    await page.wait_for_timeout(1000)  # Wait briefly for transition
                else:
                    logger.info(f"[CyberBrowser] Typing into coordinate ({x:.2f}, {y:.2f}) resolved by {resolved_msg}: '{text}'")
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

            summary_prefix = "浏览器操作执行成功！\n"
            if vision_used:
                summary_prefix += f"👁️ [多模态视觉自愈定位已触发]: 成功基于自然语言描述 '{params.get('visual_description')}' 通过 Vision-Loop 预测坐标点并点击。\n"
            elif failover_used:
                summary_prefix += f"🛡️ [模糊文字自愈网络已触发]: 成功将描述 '{params.get('visual_description')}' 模糊文本匹配自愈命中元素 '{resolved_msg}'。\n"

            summary_text = (
                f"{summary_prefix}"
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
                    "vision_used": vision_used,
                    "failover_used": failover_used,
                    "message": summary_text
                }
            )

        except Exception as ex:
            logger.error(f"[CyberBrowser] Action '{action}' execution crash: {ex}")
            return ToolResult(success=False, error=f"浏览器操作期异常: {type(ex).__name__}: {str(ex)}")

    async def _resolve_coordinates(self, page, params: dict, conv_id: str) -> tuple[float, float, str, bool, bool]:
        """Resolves target coordinate (x, y) using element_id, or falls back to vision / fuzzy DOM search."""
        el_id = params.get("element_id")
        visual_desc = params.get("visual_description", "").strip()

        if el_id is not None:
            # 1. Standard ACI DOM ID lookup
            cache = browser_session_manager.elements_cache.get(conv_id, {})
            if el_id not in cache:
                raise ValueError(f"未找到指定的元素 ID: {el_id}。请重新获取截图或验证页面状态。")
            el_data = cache[el_id]
            return el_data["x"], el_data["y"], f"ID {el_id} ('{el_data['text']}')", False, False

        if not visual_desc:
            raise ValueError("必须提供 element_id 或 visual_description 之一进行定位")

        # 2. Try Skyvern-style Multimodal Vision Loop
        try:
            x_abs, y_abs = await self._locate_by_vision(page, visual_desc, conv_id)
            return x_abs, y_abs, f"视觉定位 '{visual_desc}'", True, False
        except Exception as e:
            logger.warning(f"[CyberBrowser] Vision locator failed: {e}. Falling back to fuzzy DOM match.")
            
            # 3. Fallback to Fuzzy DOM similarity match
            x_cached, y_cached, matched_text = self._locate_by_fuzzy_dom(conv_id, visual_desc)
            return x_cached, y_cached, f"模糊自愈命中 '{matched_text}'", False, True

    async def _locate_by_vision(self, page, visual_description: str, conversation_id: str) -> tuple[float, float]:
        """Predict coordinates using multimodal vision model from screenshot."""
        # Temporarily remove badges for clean screenshot
        await page.evaluate("const old = document.querySelectorAll('.cyberbrowser-badge'); old.forEach(b => b.remove());")
        
        screenshot_bytes = await page.screenshot(type="png")
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        from app.core.llm_client import llm_client
        prompt_text = (
            f"你是一个专业的网页视觉操作助手。以下是当前网页的屏幕截图。\n"
            f"请在图片中定位符合以下自然语言描述的交互元素：\n"
            f"\"{visual_description}\"\n\n"
            f"请计算该元素中心位置的相对百分比坐标 x 和 y（相对于图片左上角，取值在 0.0 到 100.0 之间）。\n"
            f"你必须仅以合法的 JSON 格式返回结果，绝对不要附带任何 markdown 块或其它解释文字。JSON 格式如下：\n"
            f"{{\"x\": 45.2, \"y\": 62.1, \"confidence\": 0.95}}"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
                ]
            }
        ]

        full_response = ""
        async for chunk in llm_client.chat_stream(messages, system="You are a precise multimodal coordinates visual locator. Return only valid JSON."):
            full_response += chunk

        cleaned_resp = full_response.strip().strip("'\"`").replace("```json", "").replace("```", "").strip()
        coords = json.loads(cleaned_resp)
        x_pct = float(coords["x"])
        y_pct = float(coords["y"])

        viewport = page.viewport_size
        if not viewport:
            viewport = {"width": 1280, "height": 800}

        x_abs = (x_pct / 100.0) * viewport["width"]
        y_abs = (y_pct / 100.0) * viewport["height"]
        return x_abs, y_abs

    def _locate_by_fuzzy_dom(self, conversation_id: str, visual_description: str) -> tuple[float, float, str]:
        """Fallback helper to search current elements cache for text matching."""
        cache = browser_session_manager.elements_cache.get(conversation_id, {})
        if not cache:
            raise ValueError("没有可用的页面元素缓存以执行模糊匹配")

        best_el = None
        best_score = -1
        query_words = set(visual_description.lower().split())

        for el_id, el in cache.items():
            text = (el.get("text") or "").lower()
            role = (el.get("role") or "").lower()
            tag = (el.get("tagName") or "").lower()

            score = 0
            if visual_description.lower() in text:
                score += 10
            if visual_description.lower() in role or visual_description.lower() in tag:
                score += 5

            el_words = set(text.split() + role.split() + tag.split())
            overlap = len(query_words.intersection(el_words))
            score += overlap * 2

            if score > best_score and score > 0:
                best_score = score
                best_el = el

        if best_el is None:
            # Fallback to the first interactive element as emergency safety net
            first_key = list(cache.keys())[0]
            best_el = cache[first_key]

        return best_el["x"], best_el["y"], best_el["text"]

class WorkspaceCaptureScreenshotTool(AgentTool):
    name = "workspace_capture_screenshot"
    description = "使用 Playwright Headless 自动截取当前沙箱内网页（如 http://localhost:5173 或 index.html）的高清视觉截图以执行多模态审查。"
    icon = "📸"
    parameters = {
        "type": "object",
        "properties": {
            "conversation_id": {
                "type": "string",
                "description": "对话 ID（自动注入）",
            },
            "url": {
                "type": "string",
                "description": "可选的重定向网页地址或本地 HTML 文件名（例如 'http://localhost:5173' 或 'index.html'）",
            }
        }
    }

    async def execute(self, params: dict) -> ToolResult:
        conv_id = params.get("conversation_id", "default")
        url = params.get("url", "").strip()
        
        try:
            page = await browser_session_manager.get_page(conv_id)
        except Exception as e:
            return ToolResult(success=False, error=f"浏览器启动失败: {str(e)}")

        try:
            if url:
                # Check for sandboxed local file resolution
                if not url.startswith(("http://", "https://", "file://")):
                    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
                    sandbox_dir = os.path.join(workspace_dir, "agenthub_export", conv_id)
                    abs_path = os.path.abspath(os.path.join(sandbox_dir, url))
                    if abs_path.startswith(sandbox_dir) and os.path.exists(abs_path):
                        url = "file:///" + abs_path.replace(os.sep, "/")
                    else:
                        url = f"http://localhost:5173/{url.lstrip('/')}"
                
                logger.info(f"[CyberBrowser] Navigating to target URL for screenshot: {url}")
                try:
                    await page.goto(url, wait_until="load", timeout=10000)
                except Exception as go_ex:
                    logger.warning(f"[CyberBrowser] Failed navigating to {url}: {go_ex}. Capturing current state instead.")
            
            # Capture screenshot
            screenshot_bytes = await page.screenshot(type="png")
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            
            return ToolResult(
                success=True,
                data={
                    "screenshot_base64": screenshot_b64,
                    "url": page.url,
                    "message": f"📸 成功截取当前沙箱视口高清截图：{page.url}"
                }
            )
        except Exception as ex:
            return ToolResult(success=False, error=f"网页截图生成失败: {type(ex).__name__}: {str(ex)}")


# Auto-register on import
register_tool(BrowserActionTool())
register_tool(WorkspaceCaptureScreenshotTool())
