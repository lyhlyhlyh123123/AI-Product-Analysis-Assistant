from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import FieldValue, InputMethod, ProductInfo


@dataclass
class ProductEvidence:
    product: ProductInfo
    visible_text: str
    warnings: list[str]
    extraction_method: str = "local"


SUPPORTED_AMAZON_MARKETPLACES = {
    "amazon.ae",
    "amazon.ca",
    "amazon.cn",
    "amazon.co.jp",
    "amazon.co.uk",
    "amazon.com",
    "amazon.com.au",
    "amazon.com.br",
    "amazon.com.mx",
    "amazon.com.tr",
    "amazon.de",
    "amazon.eg",
    "amazon.es",
    "amazon.fr",
    "amazon.in",
    "amazon.it",
    "amazon.nl",
    "amazon.pl",
    "amazon.sa",
    "amazon.se",
    "amazon.sg",
}


def is_supported_amazon_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not any(host == domain or host.endswith(f".{domain}") for domain in SUPPORTED_AMAZON_MARKETPLACES):
        return False
    return "/dp/" in parsed.path or "/gp/product/" in parsed.path


def extract_product_from_html(html: str, url: str = "") -> tuple[ProductInfo, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    warnings: list[str] = []
    product = ProductInfo()

    title = _first_text(soup, ["#productTitle"])
    if title:
        product.title = FieldValue(value=title, source="dom")
    else:
        meta_title = _meta_content(soup, "og:title")
        if meta_title:
            product.title = FieldValue(value=_clean_title(meta_title), source="metadata")

    category = _first_text(soup, ["#wayfinding-breadcrumbs_feature_div", "#nav-subnav"])
    if category:
        product.category = FieldValue(value=category, source="dom")

    price = _first_text(soup, [".a-price .a-offscreen", "#priceblock_ourprice", "#priceblock_dealprice", "#corePrice_feature_div .a-offscreen"])
    if price:
        product.price = FieldValue(value=price, source="dom")

    rating = ""
    rating_el = soup.select_one("#acrPopover")
    if rating_el:
        rating = (rating_el.get("title") or rating_el.get_text(" ", strip=True)).strip()
    rating = rating or _first_text(soup, ["span[data-hook='rating-out-of-text']", ".reviewCountTextLinkedHistogram"])
    if rating:
        product.rating = FieldValue(value=rating, source="dom")

    review_count = _first_text(soup, ["#acrCustomerReviewText", "#acrCustomerReviewLink"])
    if review_count:
        product.review_count = FieldValue(value=review_count, source="dom")

    images = _extract_image_candidates(soup)
    product.image_candidates = images
    product.main_image_url = images[0] if images else ""
    product.core_features = _feature_bullets(soup)
    product.specifications = _specifications(soup)

    visible_text = _visible_text(soup)
    if not visible_text:
        warnings.append("页面可见文本为空，可能遇到验证码或反爬页面。")
    if _is_amazon_continue_shopping_page(visible_text):
        warnings.extend(_amazon_interstitial_warnings())
    elif url and is_supported_amazon_url(url) and _is_empty_product(product):
        warnings.extend(_amazon_interstitial_warnings())
    if url and not is_supported_amazon_url(url):
        warnings.append("输入链接不是受支持的 Amazon 商品链接。")
    return product, visible_text, warnings


def fetch_product_evidence(url: str | None, manual_text: str | None = None, settings: Settings | None = None, input_method: InputMethod = "firecrawl") -> ProductEvidence:
    settings = settings or Settings.from_env()
    warnings: list[str] = []

    if input_method == "manual":
        if not (manual_text and manual_text.strip()):
            raise ValueError("选择手动复制粘贴时必须提供商品描述。")
        product = _product_from_manual_text(manual_text)
        return ProductEvidence(product=product, visible_text=manual_text.strip(), warnings=["已使用手动商品描述作为分析依据。"], extraction_method="manual")

    if not url:
        raise ValueError("选择抓取方式时必须提供 Amazon 商品链接。")

    is_supported_url = is_supported_amazon_url(url)
    if not is_supported_url:
        return ProductEvidence(product=ProductInfo(), visible_text="", warnings=["请输入 Amazon 商品详情页链接。"], extraction_method="unsupported")

    if input_method == "firecrawl":
        try:
            return _fetch_product_evidence_with_firecrawl(url, settings, warnings)
        except Exception as exc:  # noqa: BLE001
            return ProductEvidence(product=ProductInfo(), visible_text="", warnings=[f"Firecrawl 抓取失败：{exc}"], extraction_method="firecrawl_failed")

    try:
        html = _fetch_html(url)
    except Exception as exc:  # noqa: BLE001
        return ProductEvidence(product=ProductInfo(), visible_text="", warnings=_fetch_failure_warnings(exc), extraction_method="local_failed")

    product, visible_text, parse_warnings = extract_product_from_html(html, url=url)
    method = "blocked" if any("反爬" in warning or "继续购物" in warning for warning in parse_warnings) else "local"
    return ProductEvidence(product=product, visible_text=visible_text, warnings=parse_warnings, extraction_method=method)


def _fetch_product_evidence_with_firecrawl(url: str, settings: Settings, warnings: list[str]) -> ProductEvidence:
    try:
        from firecrawl import Firecrawl
    except ImportError as exc:
        raise RuntimeError("未安装 firecrawl-py，请先运行 python -m pip install -r requirements.txt") from exc

    client_kwargs = {"api_url": settings.firecrawl_base_url.rstrip("/")}
    if settings.firecrawl_api_key:
        client_kwargs["api_key"] = settings.firecrawl_api_key
    try:
        client = Firecrawl(**client_kwargs)
    except TypeError:
        client_kwargs.pop("api_url", None)
        client = Firecrawl(**client_kwargs)
    doc = client.scrape(url, formats=["markdown", "html"])
    data = _firecrawl_doc_to_dict(doc)
    html = str(data.get("html") or "")
    markdown = str(data.get("markdown") or "")
    if html:
        product, visible_text, parse_warnings = extract_product_from_html(html, url=url)
        visible_text = _normalize_space(markdown) or visible_text
    elif markdown:
        product = _product_from_scraped_text(markdown)
        visible_text = _normalize_space(markdown)[:6000]
        parse_warnings = []
    else:
        raise ValueError("Firecrawl 未返回 markdown 或 html 内容")
    if _is_empty_product(product):
        parse_warnings.append("Firecrawl 已返回页面内容，但未提取到明确商品字段。")
    return ProductEvidence(product=product, visible_text=visible_text, warnings=warnings + parse_warnings, extraction_method="firecrawl")


def _firecrawl_doc_to_dict(doc) -> dict:
    if isinstance(doc, dict):
        raw = doc
    elif hasattr(doc, "model_dump"):
        raw = doc.model_dump()
    elif hasattr(doc, "dict"):
        raw = doc.dict()
    else:
        raw = {key: getattr(doc, key, "") for key in ("markdown", "html")}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    return data if isinstance(data, dict) else {}


def _product_from_scraped_text(text: str) -> ProductInfo:
    lines = [_normalize_space(re.sub(r"^[#*\-\s]+", "", line)) for line in text.splitlines()]
    lines = [line for line in lines if line]
    title = lines[0] if lines else "unknown"
    return ProductInfo(
        title=FieldValue(value=title, source="ai" if title != "unknown" else "unknown"),
        core_features=lines[1:6],
    )


def _fetch_html(url: str) -> str:
    last_exc: Exception | None = None
    for _ in range(3):
        try:
            with httpx.Client(headers=_browser_headers(), follow_redirects=True, timeout=20.0) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    raise RuntimeError("抓取失败")


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def _is_amazon_continue_shopping_page(visible_text: str) -> bool:
    lowered = visible_text.lower()
    return "click the button below to continue shopping" in lowered and "continue shopping" in lowered


def _is_empty_product(product: ProductInfo) -> bool:
    return (
        product.title.value == "unknown"
        and product.category.value == "unknown"
        and product.price.value == "unknown"
        and product.rating.value == "unknown"
        and product.review_count.value == "unknown"
        and not product.core_features
        and not product.specifications
    )


def _amazon_interstitial_warnings() -> list[str]:
    return [
        "Amazon 返回了继续购物或反爬页面，没有进入商品详情页。",
        "请把商品标题、卖点、规格粘贴到手动商品描述后重试。",
    ]


def _fetch_failure_warnings(exc: Exception) -> list[str]:
    message = str(exc)
    if "UNEXPECTED_EOF_WHILE_READING" in message or "EOF occurred" in message:
        return [
            f"抓取失败：网络连接被提前断开（SSL/EOF）：{message}",
            "请把商品标题、卖点、规格粘贴到手动商品描述后重试。",
        ]
    return [f"抓取失败：{exc}", "请把商品标题、卖点、规格粘贴到手动商品描述后重试。"]


def _product_from_manual_text(text: str) -> ProductInfo:
    lines = [_normalize_space(line) for line in text.splitlines() if _normalize_space(line)]
    title = lines[0] if lines else text.strip()[:80]
    features = lines[1:6] if len(lines) > 1 else _sentences(text)[:5]
    return ProductInfo(
        title=FieldValue(value=title or "unknown", source="manual" if title else "unknown"),
        core_features=features,
    )


def _extract_image_candidates(soup: BeautifulSoup) -> list[str]:
    candidates: list[str] = []
    landing = soup.select_one("#landingImage")
    if landing:
        dynamic = landing.get("data-a-dynamic-image")
        if dynamic:
            try:
                decoded = json.loads(unescape(dynamic))
                candidates.extend(str(url) for url in decoded if isinstance(url, str))
            except json.JSONDecodeError:
                pass
        candidates.extend(_image_urls_from_node(landing))

    for node in soup.select("#altImages img, .imageThumbnail img, img.a-dynamic-image"):
        candidates.extend(_image_urls_from_node(node))

    for script in soup.select("script"):
        candidates.extend(_image_urls_from_script(script.string or script.get_text(" ", strip=False)))

    og_image = _meta_content(soup, "og:image")
    if og_image:
        candidates.append(og_image)
    return _unique_non_empty(candidates)


def _image_urls_from_node(node) -> list[str]:
    urls: list[str] = []
    for attr in ("data-old-hires", "data-a-hires", "data-large", "data-main-url", "src"):
        value = node.get(attr)
        if value:
            urls.append(value)
    return urls


def _image_urls_from_script(text: str) -> list[str]:
    if not text:
        return []
    fields = r"(?:hiRes|large|mainUrl)"
    return [unescape(match) for match in re.findall(rf'"{fields}"\s*:\s*"(https?://[^"\\]+)"', text)]


def _feature_bullets(soup: BeautifulSoup) -> list[str]:
    bullets = [_normalize_space(node.get_text(" ", strip=True)) for node in soup.select("#feature-bullets .a-list-item")]
    blocked = {"", "make sure this fits by entering your model number."}
    return [bullet for bullet in _unique_non_empty(bullets) if bullet.lower() not in blocked][:8]


def _specifications(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for row in soup.select("#productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr, table.prodDetTable tr"):
        key_el = row.select_one("th")
        val_el = row.select_one("td")
        if key_el and val_el:
            key = _normalize_space(key_el.get_text(" ", strip=True))
            value = _normalize_space(val_el.get_text(" ", strip=True))
            if key and value:
                specs[key] = value
    for item in soup.select("#detailBullets_feature_div li"):
        text = _normalize_space(item.get_text(" ", strip=True))
        if ":" in text:
            key, value = [part.strip() for part in text.split(":", 1)]
            if key and value:
                specs[key] = value
    return specs


def _visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _normalize_space(soup.get_text(" ", strip=True))[:6000]


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = _normalize_space(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _meta_content(soup: BeautifulSoup, property_name: str) -> str:
    node = soup.select_one(f'meta[property="{property_name}"]') or soup.select_one(f'meta[name="{property_name}"]')
    if not node:
        return ""
    return _normalize_space(node.get("content", ""))


def _clean_title(title: str) -> str:
    return re.sub(r"\s*[:|,-]?\s*Amazon\..*$", "", title, flags=re.IGNORECASE).strip() or title


def _sentences(text: str) -> list[str]:
    return [_normalize_space(part) for part in re.split(r"[。！？.!?\n]+", text) if _normalize_space(part)]


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _unique_non_empty(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _normalize_space(value)
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result
