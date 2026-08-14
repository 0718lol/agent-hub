"""Browser lifecycle manager using Playwright.

Provides a singleton browser instance with:
- Automatic page management (max 5 concurrent pages)
- Idle page cleanup (5 minute timeout)
- Resource limits and cleanup on exit
"""
import asyncio
import atexit
import glob
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass, field

logger = logging.getLogger("browser_manager")


def browser_launch_options() -> dict:
    """Reuse a managed Chromium binary when Playwright's exact revision is absent."""
    configured = os.environ.get("AGENTHUB_CHROMIUM_EXECUTABLE", "").strip()
    candidates = [configured] if configured else []
    candidates.extend(sorted(
        glob.glob("/opt/ms-playwright/chromium-*/chrome-linux*/chrome"),
        reverse=True,
    ))
    executable = next((path for path in candidates if path and os.path.isfile(path)), None)
    options = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }
    if executable:
        options["executable_path"] = executable
    return options

# Try to import playwright, graceful fallback if not installed
try:
    from playwright.async_api import BrowserContext, Page, async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("Playwright not installed. Browser tools will be disabled.")


@dataclass
class PageState:
    """Track page state for lifecycle management."""
    page: object  # Page instance
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    url: str = ""


class BrowserManager:
    """Singleton browser manager with resource limits."""

    MAX_PAGES = 5
    PAGE_TIMEOUT = 30000  # 30 seconds
    IDLE_TIMEOUT = 300    # 5 minutes

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._pages: list[PageState] = []
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Check if browser is available."""
        return PLAYWRIGHT_AVAILABLE

    async def initialize(self):
        """Initialize browser if not already done."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright not installed")
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:  # Double-check after acquiring lock
                return
            try:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(**browser_launch_options())
                self._context = await self._browser.new_context(
                    viewport={'width': 1280, 'height': 720},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                self._initialized = True
                logger.info("Browser manager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                raise

    async def new_page(self):
        """Create a new page, evict oldest if at limit."""
        if not self._initialized:
            await self.initialize()

        # Cleanup idle pages first
        await self._cleanup_idle_pages()

        # Evict oldest if at limit
        if len(self._pages) >= self.MAX_PAGES:
            oldest = min(self._pages, key=lambda p: p.last_used)
            try:
                await oldest.page.close()
            except Exception:
                pass
            self._pages.remove(oldest)
            logger.info(f"Evicted idle page (was at {oldest.url})")

        # Create new page
        page = await self._context.new_page()
        page.set_default_timeout(self.PAGE_TIMEOUT)
        state = PageState(page=page)
        self._pages.append(state)
        logger.info(f"New page created (total: {len(self._pages)})")
        return page

    async def get_current_page(self):
        """Get the most recently used page, or create a new one."""
        if not self._pages:
            return await self.new_page()
        # Return most recently used
        newest = max(self._pages, key=lambda p: p.last_used)
        newest.last_used = time.time()
        return newest.page

    async def close_page(self, page):
        """Close a specific page."""
        for state in self._pages:
            if state.page == page:
                try:
                    await page.close()
                except Exception:
                    pass
                self._pages.remove(state)
                logger.info(f"Page closed (total: {len(self._pages)})")
                return

    async def _cleanup_idle_pages(self):
        """Close pages idle for more than IDLE_TIMEOUT."""
        now = time.time()
        idle = [s for s in self._pages if now - s.last_used > self.IDLE_TIMEOUT]
        for state in idle:
            try:
                await state.page.close()
            except Exception:
                pass
            self._pages.remove(state)
            logger.info(f"Cleaned up idle page (was at {state.url})")

    async def close(self):
        """Shutdown browser and cleanup all resources."""
        logger.info("Shutting down browser manager...")
        for state in self._pages:
            try:
                await state.page.close()
            except Exception:
                pass
        self._pages.clear()

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        self._initialized = False
        logger.info("Browser manager shut down")


# Global singleton
browser_manager = BrowserManager()


# Cleanup on exit
def _cleanup():
    if browser_manager._initialized:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(browser_manager.close())
            else:
                loop.run_until_complete(browser_manager.close())
        except Exception:
            pass

atexit.register(_cleanup)


def _signal_handler(sig, frame):
    _cleanup()
    sys.exit(0)

try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
except (ValueError, OSError):
    pass  # Signal handling may not work in all contexts
