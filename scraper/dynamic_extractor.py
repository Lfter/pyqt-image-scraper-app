import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from scraper.extractor import ImageExtractor
from utils.helpers import USER_AGENT


class DynamicImageExtractor(ImageExtractor):
    def __init__(self):
        super().__init__(session=None)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def open_page(self, page_url: str):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.goto(page_url, wait_until="domcontentloaded", timeout=120000)

    def extract_from_current_page(self, base_url: str):
        if self.page is None:
            raise ValueError("动态页面尚未打开，请先打开页面并完成登录。")

        html = self.page.content()
        soup = BeautifulSoup(html, "html.parser")
        return self.extract_image_urls(soup, base_url)

    def build_authenticated_session(self):
        if self.context is None:
            raise ValueError("动态页面尚未打开，无法同步登录状态。")

        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

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
            self.page.close()
            self.page = None
        if self.context:
            self.context.close()
            self.context = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
