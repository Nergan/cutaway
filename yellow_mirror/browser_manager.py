import asyncio
import time
from typing import Dict, Optional
from playwright.async_api import async_playwright, Browser, Page


class BrowserSession:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.last_activity = time.time()
        self.current_url = "about:blank"

    async def launch(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page(viewport={"width": 1280, "height": 720})
        self.last_activity = time.time()

    async def goto(self, url: str):
        if not self.page:
            await self.launch()
        try:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            await self.page.goto(url, timeout=30000)
            self.current_url = self.page.url
            self.last_activity = time.time()
        except Exception as e:
            print(f"Error navigating to {url}: {e}")
            raise

    async def click(self, x: int, y: int):
        if self.page:
            await self.page.mouse.click(x, y)
            self.last_activity = time.time()

    async def type(self, text: str):
        if self.page:
            await self.page.keyboard.type(text)
            self.last_activity = time.time()

    async def press_key(self, key: str):
        if self.page:
            await self.page.keyboard.press(key)
            self.last_activity = time.time()

    async def screenshot(self) -> bytes:
        if self.page:
            self.last_activity = time.time()
            return await self.page.screenshot(type="jpeg", quality=70)
        return b""

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()


class BrowserManager:
    def __init__(self):
        self.sessions: Dict[str, BrowserSession] = {}
        self._cleanup_task = None

    def start_cleanup(self):
        async def cleanup_loop():
            while True:
                await asyncio.sleep(60)
                now = time.time()
                to_delete = []
                for sid, sess in self.sessions.items():
                    if now - sess.last_activity > 300:
                        await sess.close()
                        to_delete.append(sid)
                for sid in to_delete:
                    del self.sessions[sid]

        self._cleanup_task = asyncio.create_task(cleanup_loop())

    async def get_or_create_session(self, session_id: str) -> BrowserSession:
        if session_id not in self.sessions:
            sess = BrowserSession(session_id)
            await sess.launch()
            self.sessions[session_id] = sess
        return self.sessions[session_id]

    async def close_all(self):
        for sess in self.sessions.values():
            await sess.close()
        self.sessions.clear()
        if self._cleanup_task:
            self._cleanup_task.cancel()


manager = BrowserManager()