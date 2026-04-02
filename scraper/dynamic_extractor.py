from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from scraper.extractor import ImageExtractor


class DynamicImageExtractor(ImageExtractor):
    def __init__(self):
        super().__init__(session=None)

    def extract_from_page(self, page_url: str):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

            page.goto(page_url, wait_until="networkidle", timeout=60000)

            # 给用户一点时间手动登录/等待页面渲染
            page.wait_for_timeout(5000)

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        return self.extract_image_urls(soup, page_url)