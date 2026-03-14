import importlib.util
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def install_optional_dependency_stubs() -> None:
    """Provide minimal stubs so the scraper module can be imported in tests."""
    if importlib.util.find_spec("requests") is None:
        requests_module = types.ModuleType("requests")

        class Session:
            def __init__(self) -> None:
                self.headers = {}

            def close(self) -> None:
                pass

        class RequestException(Exception):
            pass

        requests_module.Session = Session
        requests_module.exceptions = types.SimpleNamespace(RequestException=RequestException)
        sys.modules["requests"] = requests_module

    if importlib.util.find_spec("bs4") is None:
        bs4_module = types.ModuleType("bs4")
        bs4_module.__path__ = []

        class BeautifulSoup:
            pass

        bs4_module.BeautifulSoup = BeautifulSoup
        sys.modules["bs4"] = bs4_module

    if importlib.util.find_spec("selenium") is None:
        selenium_module = types.ModuleType("selenium")
        webdriver_module = types.ModuleType("selenium.webdriver")
        webdriver_common_module = types.ModuleType("selenium.webdriver.common")
        webdriver_common_by_module = types.ModuleType("selenium.webdriver.common.by")
        webdriver_support_module = types.ModuleType("selenium.webdriver.support")
        webdriver_support_ui_module = types.ModuleType("selenium.webdriver.support.ui")
        webdriver_support_ec_module = types.ModuleType("selenium.webdriver.support.expected_conditions")
        webdriver_chrome_module = types.ModuleType("selenium.webdriver.chrome")
        webdriver_chrome_service_module = types.ModuleType("selenium.webdriver.chrome.service")
        webdriver_chrome_options_module = types.ModuleType("selenium.webdriver.chrome.options")

        selenium_module.__path__ = []
        webdriver_module.__path__ = []
        webdriver_common_module.__path__ = []
        webdriver_support_module.__path__ = []
        webdriver_chrome_module.__path__ = []

        class Chrome:
            pass

        class By:
            CSS_SELECTOR = "css selector"
            TAG_NAME = "tag name"

        class WebDriverWait:
            def __init__(self, driver, timeout) -> None:
                self.driver = driver
                self.timeout = timeout

            def until(self, condition):
                return []

        class Service:
            def __init__(self, *args, **kwargs) -> None:
                pass

        class Options:
            def add_argument(self, *args, **kwargs) -> None:
                pass

        def presence_of_element_located(locator):
            return locator

        def presence_of_all_elements_located(locator):
            return locator

        webdriver_module.Chrome = Chrome
        webdriver_module.common = webdriver_common_module
        webdriver_module.support = webdriver_support_module
        webdriver_module.chrome = webdriver_chrome_module
        webdriver_common_module.by = webdriver_common_by_module
        webdriver_common_by_module.By = By
        webdriver_support_module.ui = webdriver_support_ui_module
        webdriver_support_module.expected_conditions = webdriver_support_ec_module
        webdriver_support_ui_module.WebDriverWait = WebDriverWait
        webdriver_support_ec_module.presence_of_element_located = presence_of_element_located
        webdriver_support_ec_module.presence_of_all_elements_located = presence_of_all_elements_located
        webdriver_chrome_module.service = webdriver_chrome_service_module
        webdriver_chrome_module.options = webdriver_chrome_options_module
        webdriver_chrome_service_module.Service = Service
        webdriver_chrome_options_module.Options = Options
        selenium_module.webdriver = webdriver_module

        sys.modules["selenium"] = selenium_module
        sys.modules["selenium.webdriver"] = webdriver_module
        sys.modules["selenium.webdriver.common"] = webdriver_common_module
        sys.modules["selenium.webdriver.common.by"] = webdriver_common_by_module
        sys.modules["selenium.webdriver.support"] = webdriver_support_module
        sys.modules["selenium.webdriver.support.ui"] = webdriver_support_ui_module
        sys.modules["selenium.webdriver.support.expected_conditions"] = webdriver_support_ec_module
        sys.modules["selenium.webdriver.chrome"] = webdriver_chrome_module
        sys.modules["selenium.webdriver.chrome.service"] = webdriver_chrome_service_module
        sys.modules["selenium.webdriver.chrome.options"] = webdriver_chrome_options_module

    if importlib.util.find_spec("webdriver_manager") is None:
        webdriver_manager_module = types.ModuleType("webdriver_manager")
        webdriver_manager_chrome_module = types.ModuleType("webdriver_manager.chrome")

        webdriver_manager_module.__path__ = []

        class ChromeDriverManager:
            def install(self) -> str:
                return "chromedriver"

        webdriver_manager_module.chrome = webdriver_manager_chrome_module
        webdriver_manager_chrome_module.ChromeDriverManager = ChromeDriverManager
        sys.modules["webdriver_manager"] = webdriver_manager_module
        sys.modules["webdriver_manager.chrome"] = webdriver_manager_chrome_module


install_optional_dependency_stubs()

from bs4 import BeautifulSoup
from config import ScraperConfig
from scraper import (
    ImageCandidate,
    SITE_TYPE_GENERIC,
    contains_unwanted_image_term,
    dedupe_artsy_candidates,
    extract_generic_site_and_title,
    extract_images_from_page,
    parse_html_document,
    resolve_page_asset_url,
)


class FakeTag:
    def __init__(self, attrs=None) -> None:
        self.attrs = attrs or {}

    def __getitem__(self, key):
        return self.attrs[key]

    def get(self, key, default=None):
        return self.attrs.get(key, default)


class FakeSoup:
    def __init__(self, img_srcs=None, style_values=None) -> None:
        self.img_tags = [FakeTag({"src": src}) for src in (img_srcs or [])]
        self.styled_elements = [FakeTag({"style": style}) for style in (style_values or [])]

    def find(self, tag_name, *args, **kwargs):
        return None

    def find_all(self, tag_name, *args, **kwargs):
        if tag_name == "img":
            return self.img_tags
        return []

    def select(self, selector):
        if selector == '[style*="background-image"]':
            return self.styled_elements
        return []


class ResolvePageAssetUrlTests(unittest.TestCase):
    def test_resolves_common_generic_asset_urls(self) -> None:
        page_url = "https://example.com/gallery/work/item"
        cases = {
            "../img/pic.jpg": "https://example.com/gallery/img/pic.jpg",
            "/img/pic.jpg": "https://example.com/img/pic.jpg",
            "img/pic.jpg": "https://example.com/gallery/work/img/pic.jpg",
            "//cdn.example.com/a.jpg": "https://cdn.example.com/a.jpg",
            "?size=large": "https://example.com/gallery/work/item?size=large",
        }

        for raw_url, expected_url in cases.items():
            with self.subTest(raw_url=raw_url):
                self.assertEqual(resolve_page_asset_url(page_url, raw_url), expected_url)

    def test_rejects_empty_data_and_non_http_urls(self) -> None:
        page_url = "https://example.com/gallery/work/item"
        invalid_values = [
            "",
            "   ",
            "data:image/png;base64,abcdef",
            "ftp://example.com/image.jpg",
        ]

        for raw_url in invalid_values:
            with self.subTest(raw_url=raw_url):
                self.assertIsNone(resolve_page_asset_url(page_url, raw_url))


class ExtractImagesFromGenericPageTests(unittest.TestCase):
    def test_generic_extraction_resolves_img_and_background_urls(self) -> None:
        soup = FakeSoup(
            img_srcs=[
                "../img/pic.jpg",
                "/img/root.jpg",
                "img/local.jpg",
                "//cdn.example.com/a.jpg",
                "icon.svg",
                "data:image/png;base64,abcdef",
                "/assets/logo-banner.jpg",
            ],
            style_values=[
                "background-image:url(../bg/hero.png)",
                "background-image: url(\"//cdn.example.com/hero.webp\")",
                "background-image:url(data:image/png;base64,abcdef)",
            ],
        )

        image_urls = extract_images_from_page(
            soup=soup,
            url="https://example.com/gallery/work/item",
            site_type=SITE_TYPE_GENERIC,
            config=ScraperConfig(),
        )

        self.assertEqual(
            image_urls,
            {
                "https://example.com/gallery/img/pic.jpg",
                "https://example.com/img/root.jpg",
                "https://example.com/gallery/work/img/local.jpg",
                "https://cdn.example.com/a.jpg",
                "https://example.com/gallery/bg/hero.png",
                "https://cdn.example.com/hero.webp",
            },
        )

    def test_generic_extraction_keeps_og_image_from_uploads_path(self) -> None:
        html = """
        <html>
            <head>
                <meta property="og:image" content="https://cdn.arstechnica.net/wp-content/uploads/2026/03/GettyImages-1258714131-1152x648-1773339019.jpg">
            </head>
            <body>
                <img src="https://cdn.arstechnica.net/wp-content/themes/ars-v9/public/images/firework-loader.75ab30.gif">
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        image_urls = extract_images_from_page(
            soup=soup,
            url="https://arstechnica.com/story",
            site_type=SITE_TYPE_GENERIC,
            config=ScraperConfig(),
        )

        self.assertIn(
            "https://cdn.arstechnica.net/wp-content/uploads/2026/03/GettyImages-1258714131-1152x648-1773339019.jpg",
            image_urls,
        )

    def test_generic_extraction_prefers_largest_srcset_candidate(self) -> None:
        html = """
        <html>
            <body>
                <img
                    src="https://example.com/image-640.jpg"
                    srcset="https://example.com/image-640.jpg 640w, https://example.com/image-1536.jpg 1536w"
                >
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        image_urls = extract_images_from_page(
            soup=soup,
            url="https://example.com/story",
            site_type=SITE_TYPE_GENERIC,
            config=ScraperConfig(),
        )

        self.assertIn("https://example.com/image-1536.jpg", image_urls)
        self.assertNotIn("https://example.com/image-640.jpg", image_urls)


class HelperBehaviorTests(unittest.TestCase):
    def test_unwanted_term_matching_uses_tokens_not_substrings(self) -> None:
        config = ScraperConfig()

        self.assertFalse(
            contains_unwanted_image_term(
                "https://cdn.arstechnica.net/wp-content/uploads/2026/03/photo.jpg",
                config.unwanted_image_terms,
            )
        )
        self.assertTrue(
            contains_unwanted_image_term(
                "https://example.com/assets/logo-banner.jpg",
                config.unwanted_image_terms,
            )
        )

    def test_generic_title_extraction_prefers_metadata_over_cookie_text(self) -> None:
        html = """
        <html>
            <head>
                <meta property="og:site_name" content="Ars Technica">
                <meta property="og:title" content="Trump's DOJ is not falling for Sam Bankman-Fried's MAGA makeover on X">
                <title>Trump's DOJ is not falling for Sam Bankman-Fried's MAGA makeover on X | Ars Technica</title>
            </head>
            <body>
                <h1>We and our partners process data for the following purposes</h1>
            </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")

        site_name, title = extract_generic_site_and_title(
            soup,
            "https://arstechnica.com/story",
            "Trump's DOJ is not falling for Sam Bankman-Fried's MAGA makeover on X | Ars Technica",
        )

        self.assertEqual(site_name, "Ars Technica")
        self.assertEqual(title, "Trump's DOJ is not falling for Sam Bankman-Fried's MAGA makeover on X")

    def test_parse_html_document_falls_back_when_preferred_parser_is_unavailable(self) -> None:
        html = "<html><body><p>fallback</p></body></html>"

        def fake_beautiful_soup(markup, parser_name):
            if parser_name == "lxml":
                raise __import__("bs4").FeatureNotFound("missing lxml")
            return BeautifulSoup(markup, parser_name)

        with patch("scraper.BeautifulSoup", side_effect=fake_beautiful_soup):
            soup = parse_html_document(html)

        self.assertEqual(soup.find("p").get_text(strip=True), "fallback")

    def test_artsy_candidates_are_deduped_to_the_best_variant(self) -> None:
        candidates = [
            ImageCandidate("https://d32dm0rphc51dk.cloudfront.net/asset123/large.jpg", "json_ld", 60),
            ImageCandidate("https://d32dm0rphc51dk.cloudfront.net/asset123/main.jpg", "preload", 70),
            ImageCandidate("https://d32dm0rphc51dk.cloudfront.net/asset123/small.jpg", "meta", 50),
        ]

        self.assertEqual(
            dedupe_artsy_candidates(candidates),
            {"https://d32dm0rphc51dk.cloudfront.net/asset123/main.jpg"},
        )


if __name__ == "__main__":
    unittest.main()
