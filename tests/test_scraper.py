import sys
import types

import httpx

from app.config import Settings
from app.services import scraper
from app.services.scraper import extract_product_from_html, fetch_product_evidence, is_supported_amazon_url


def test_supported_amazon_url_accepts_dp_links():
    assert is_supported_amazon_url("https://www.amazon.com/dp/B0TEST1234")
    assert is_supported_amazon_url("https://amazon.co.uk/gp/product/B0TEST1234")
    assert not is_supported_amazon_url("https://example.com/dp/B0TEST1234")
    assert not is_supported_amazon_url("https://amazon.com.evil.example/dp/B0TEST1234")


def test_extract_product_from_html_reads_core_fields():
    html = '''<html><head><meta property="og:image" content="https://img.example/a.jpg"></head><body>
    <span id="productTitle"> Portable Blender </span>
    <span class="a-price"><span class="a-offscreen">$29.99</span></span>
    <span id="acrPopover" title="4.5 out of 5 stars"></span>
    <span id="acrCustomerReviewText">1,234 ratings</span>
    <div id="feature-bullets"><span class="a-list-item">USB rechargeable</span></div>
    <table id="productDetails_techSpec_section_1"><tr><th>Capacity</th><td>500ml</td></tr></table>
    </body></html>'''
    product, text, warnings = extract_product_from_html(html)
    assert product.title.value == "Portable Blender"
    assert product.price.value == "$29.99"
    assert product.rating.value == "4.5 out of 5 stars"
    assert product.review_count.value == "1,234 ratings"
    assert product.main_image_url == "https://img.example/a.jpg"
    assert product.core_features == ["USB rechargeable"]
    assert product.specifications["Capacity"] == "500ml"
    assert warnings == []
    assert "Portable Blender" in text


def test_extract_product_from_html_reads_amazon_image_gallery_candidates():
    html = '''<html><head><meta property="og:image" content="https://img.example/og.jpg"></head><body>
    <span id="productTitle"> Camera Bag </span>
    <img id="landingImage" data-a-dynamic-image='{&quot;https://img.example/main.jpg&quot;:[1000,1000]}' src="https://img.example/small.jpg">
    <li class="imageThumbnail"><img src="https://img.example/thumb._SS40_.jpg" data-old-hires="https://img.example/thumb-hires.jpg"></li>
    <img class="a-dynamic-image" data-a-hires="https://img.example/dynamic-hires.jpg" data-large="https://img.example/dynamic-large.jpg">
    <script>
      var data = {"colorImages":{"initial":[{"hiRes":"https://img.example/hires-script.jpg","large":"https://img.example/large-script.jpg","mainUrl":"https://img.example/main-script.jpg"}]}};
    </script>
    </body></html>'''

    product, _, _ = extract_product_from_html(html)

    assert product.main_image_url == "https://img.example/main.jpg"
    assert product.image_candidates == [
        "https://img.example/main.jpg",
        "https://img.example/small.jpg",
        "https://img.example/thumb-hires.jpg",
        "https://img.example/thumb._SS40_.jpg",
        "https://img.example/dynamic-hires.jpg",
        "https://img.example/dynamic-large.jpg",
        "https://img.example/hires-script.jpg",
        "https://img.example/large-script.jpg",
        "https://img.example/main-script.jpg",
        "https://img.example/og.jpg",
    ]


def test_fetch_product_evidence_uses_firecrawl_sdk_when_selected(monkeypatch):
    calls = []

    class DummyFirecrawl:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def scrape(self, url, formats):
            calls.append(("scrape", url, formats))
            return {
                "html": """
                <html><head><meta property="og:image" content="https://img.example/chair.jpg"></head><body>
                <span id="productTitle">VTOY Camping Chair</span>
                <span class="a-price"><span class="a-offscreen">$59.99</span></span>
                <span id="acrPopover" title="4.4 out of 5 stars"></span>
                <span id="acrCustomerReviewText">123 ratings</span>
                <div id="feature-bullets"><span class="a-list-item">Foldable chair</span><span class="a-list-item">Built-in shade</span></div>
                <table id="productDetails_techSpec_section_1"><tr><th>Color</th><td>Blue</td></tr></table>
                </body></html>
                """,
                "markdown": "VTOY Camping Chair Foldable chair Built-in shade",
            }

    monkeypatch.setitem(sys.modules, "firecrawl", types.SimpleNamespace(Firecrawl=DummyFirecrawl))
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: (_ for _ in ()).throw(AssertionError("local fetch should not run")))

    evidence = fetch_product_evidence(
        "https://www.amazon.com/dp/B0CXT9RSGQ",
        settings=Settings(firecrawl_api_key="firecrawl-key", firecrawl_base_url="https://api.firecrawl.dev"),
        input_method="firecrawl",
    )

    assert evidence.product.title.value == "VTOY Camping Chair"
    assert evidence.product.price.value == "$59.99"
    assert evidence.product.rating.value == "4.4 out of 5 stars"
    assert evidence.product.review_count.value == "123 ratings"
    assert evidence.product.core_features == ["Foldable chair", "Built-in shade"]
    assert evidence.product.specifications == {"Color": "Blue"}
    assert evidence.product.main_image_url == "https://img.example/chair.jpg"
    assert evidence.visible_text == "VTOY Camping Chair Foldable chair Built-in shade"
    assert evidence.extraction_method == "firecrawl"
    assert calls[0] == ("init", {"api_url": "https://api.firecrawl.dev", "api_key": "firecrawl-key"})
    assert calls[1] == ("scrape", "https://www.amazon.com/dp/B0CXT9RSGQ", ["markdown", "html"])


def test_fetch_product_evidence_does_not_fallback_when_firecrawl_fails(monkeypatch):
    class FailingFirecrawl:
        def __init__(self, **kwargs):
            pass

        def scrape(self, url, formats):
            raise RuntimeError("firecrawl down")

    monkeypatch.setitem(sys.modules, "firecrawl", types.SimpleNamespace(Firecrawl=FailingFirecrawl))
    monkeypatch.setattr(scraper, "_fetch_html", lambda url: (_ for _ in ()).throw(AssertionError("local fetch should not run")))

    evidence = fetch_product_evidence(
        "https://www.amazon.com/dp/B0CXT9RSGQ",
        settings=Settings(firecrawl_api_key="firecrawl-key"),
        input_method="firecrawl",
    )

    assert evidence.product.title.value == "unknown"
    assert evidence.extraction_method == "firecrawl_failed"
    assert any("Firecrawl 抓取失败" in warning for warning in evidence.warnings)


def test_fetch_product_evidence_marks_manual_extraction_method_when_selected():
    evidence = fetch_product_evidence(None, manual_text="Manual Chair\nFoldable seat", input_method="manual")

    assert evidence.product.title.value == "Manual Chair"
    assert evidence.extraction_method == "manual"


def test_fetch_product_evidence_warns_on_amazon_continue_shopping_interstitial(monkeypatch):
    html = """<html><body>
    Amazon.com Click the button below to continue shopping
    <button>Continue shopping</button>
    Conditions of Use Privacy Policy © 1996-2025, Amazon.com, Inc. or its affiliates
    </body></html>"""

    monkeypatch.setattr(scraper, "_fetch_html", lambda url: html)

    evidence = fetch_product_evidence("https://www.amazon.com/dp/B0CXT9RSGQ", settings=Settings(firecrawl_api_key=""), input_method="local")

    assert evidence.product.title.value == "unknown"
    assert "Continue shopping" in evidence.visible_text
    assert any("Amazon 继续购物" in warning or "反爬" in warning for warning in evidence.warnings)
    assert any("手动商品描述" in warning for warning in evidence.warnings)


def test_fetch_product_evidence_rejects_non_amazon_without_network(monkeypatch):
    def fail_fetch(url):
        raise AssertionError(f"unexpected network fetch for {url}")

    monkeypatch.setattr(scraper, "_fetch_html", fail_fetch)

    evidence = fetch_product_evidence("https://example.com/not-amazon", input_method="local")

    assert evidence.product.title.value == "unknown"
    assert evidence.visible_text == ""
    assert evidence.warnings == ["请输入 Amazon 商品详情页链接。"]


def test_fetch_html_retries_ssl_eof_errors_then_succeeds(monkeypatch):
    attempts = []

    class DummyResponse:
        text = '<html><span id="productTitle">Retry Product</span></html>'

        def raise_for_status(self):
            return None

    class DummyClient:
        def __init__(self, headers, follow_redirects, timeout):
            assert headers["Sec-Fetch-Site"] == "none"
            assert "Chrome" in headers["User-Agent"]
            assert headers["Accept-Encoding"] == "gzip, deflate, br"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            attempts.append(url)
            if len(attempts) < 3:
                raise httpx.TransportError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")
            return DummyResponse()

    monkeypatch.setattr(scraper.httpx, "Client", DummyClient)

    assert scraper._fetch_html("https://www.amazon.com/dp/B0TEST1234") == DummyResponse.text
    assert len(attempts) == 3


def test_fetch_product_evidence_warns_to_paste_manual_description_after_retries(monkeypatch):
    def fail_fetch(url):
        raise httpx.TransportError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol")

    monkeypatch.setattr(scraper, "_fetch_html", fail_fetch)

    evidence = fetch_product_evidence("https://www.amazon.com/dp/B0TEST1234", settings=Settings(firecrawl_api_key=""), input_method="local")

    assert evidence.product.title.value == "unknown"
    assert any("网络连接被提前断开" in warning for warning in evidence.warnings)
    assert any("请把商品标题、卖点、规格粘贴到手动商品描述后重试" in warning for warning in evidence.warnings)
