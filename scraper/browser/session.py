import requests
from playwright.sync_api import sync_playwright

from utils.helpers import USER_AGENT


class BrowserSession:
    def __init__(self, user_agent: str = USER_AGENT):
        self.user_agent = user_agent
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def open_page(self, page_url: str, headless: bool = False, response_handler=None):
        self.close()
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context(user_agent=self.user_agent)
        self.page = self.context.new_page()

        if response_handler is not None:
            self.page.on("response", response_handler)

        self.page.goto(page_url, wait_until="domcontentloaded", timeout=120000)
        self.wait_for_network_quietly()
        return self.page

    def wait_for_network_quietly(self, timeout: int = 10000):
        if self.page is None:
            return

        try:
            self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

    def build_authenticated_session(self):
        if self.context is None:
            raise ValueError("动态页面尚未打开，无法同步登录状态。")

        session = requests.Session()
        session.headers.update({"User-Agent": self.user_agent})

        for cookie in self.context.cookies():
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
                secure=cookie.get("secure", False),
            )

        return session

    def close(self):
        if self.page:
            try:
                self.page.close()
            except Exception:
                pass
            self.page = None
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
