# AI Product Analysis Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public-deployable FastAPI web tool that accepts Amazon product links, extracts product evidence, generates Chinese product analysis and a sub-150-character short-video script, and optionally produces a vertical MP4.

**Architecture:** The app is a Python 3.11 FastAPI service with a static single-page frontend. Product extraction is deterministic first, with manual-text fallback and optional DeepSeek JSON completion. TTS, image generation, and video synthesis are isolated optional services so failures return warnings without blocking the main analysis result.

**Tech Stack:** FastAPI, Uvicorn, Pydantic, httpx, BeautifulSoup, optional Crawlee/Playwright, optional DeepSeek-compatible API, optional DashScope TTS, optional Volcengine Ark image API, Pillow, MoviePy/FFmpeg, pytest.

## Global Constraints

- Real API keys must never be committed; only `.env.example` with placeholders is allowed.
- Main analysis must work even when scraping, TTS, image generation, or video generation fails.
- The page must provide a manual product description fallback for Amazon CAPTCHA, region differences, anti-bot blocks, or missing fields.
- Chinese short-video voiceover script must be 150 Chinese characters or fewer and start with a hook.
- Generated media must be written under `app/static/outputs/` and served from `/static/outputs/<file>`.
- Deployment target is Docker on Render Web Service with HTTPS public access.
- Do not commit the PDF, rendered PDF images, generated media, caches, or real `.env` files.

---

## File Structure

- Create `app/main.py`: FastAPI routes, static mounting, and frontend template serving.
- Create `app/config.py`: environment-backed settings and optional feature checks.
- Create `app/models.py`: Pydantic request and response schemas shared by API routes and tests.
- Create `app/services/scraper.py`: Amazon URL validation, HTTP fetch, visible-text cleanup, and deterministic field extraction.
- Create `app/services/ai.py`: DeepSeek JSON generation plus deterministic fallback analysis.
- Create `app/services/media.py`: optional DashScope TTS, optional Ark image generation, fallback cover generation, and MP4 composition.
- Create `app/static/index.html`, `app/static/styles.css`, `app/static/app.js`: usable single-page tool UI.
- Create `tests/test_scraper.py`, `tests/test_ai.py`, `tests/test_api.py`: focused regression coverage for URL validation, parsing, script length, fallback behavior, and API shape.
- Create `requirements.txt`, `Dockerfile`, `.env.example`, `README.md`: local setup and Render deployment packaging.

### Task 1: Project Scaffold And Schemas

**Files:**
- Create: `app/config.py`
- Create: `app/models.py`
- Create: `app/__init__.py`
- Create: `app/services/__init__.py`
- Create: `requirements.txt`
- Create: `.env.example`
- Test: `tests/test_ai.py`

**Interfaces:**
- Produces: `Settings.from_env() -> Settings`, `FieldValue`, `ProductInfo`, `AnalysisResult`, `AnalyzeRequest`, `AnalyzeResponse`, `GenerateVideoRequest`, `GenerateVideoResponse`.
- Later tasks rely on every response model using JSON-serializable Python primitives.

- [ ] **Step 1: Write schema and settings tests**

```python
from app.models import AnalyzeResponse, FieldValue, ProductInfo


def test_field_value_defaults_are_unknown():
    field = FieldValue()
    assert field.value == "unknown"
    assert field.source == "unknown"
    assert field.confidence == "low"


def test_analyze_response_serializes_nested_models():
    response = AnalyzeResponse(task_id="abc", product=ProductInfo())
    data = response.model_dump()
    assert data["product"]["title"]["value"] == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai.py -v`
Expected: FAIL with missing `app.models`.

- [ ] **Step 3: Write minimal implementation**

Create the Pydantic models and settings exactly named in the interfaces block.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai.py -v`
Expected: PASS.

### Task 2: Amazon Extraction And Fallback Evidence

**Files:**
- Create: `app/services/scraper.py`
- Test: `tests/test_scraper.py`

**Interfaces:**
- Consumes: `ProductInfo`, `FieldValue` from `app.models`.
- Produces: `ProductEvidence`, `is_supported_amazon_url(url: str) -> bool`, `extract_product_from_html(html: str, url: str = "") -> tuple[ProductInfo, str, list[str]]`, `fetch_product_evidence(url: str, manual_text: str | None) -> ProductEvidence`.

- [ ] **Step 1: Write tests for URL validation and deterministic extraction**

```python
from app.services.scraper import extract_product_from_html, is_supported_amazon_url


def test_supported_amazon_url_accepts_dp_links():
    assert is_supported_amazon_url("https://www.amazon.com/dp/B0TEST1234")
    assert is_supported_amazon_url("https://amazon.co.uk/gp/product/B0TEST1234")
    assert not is_supported_amazon_url("https://example.com/dp/B0TEST1234")


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scraper.py -v`
Expected: FAIL with missing `app.services.scraper`.

- [ ] **Step 3: Implement deterministic parser and fetch fallback**

Use BeautifulSoup selectors from the spec, parse `data-a-dynamic-image`, keep source/confidence, and return warnings when network scraping fails.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scraper.py -v`
Expected: PASS.

### Task 3: AI Analysis Service

**Files:**
- Create: `app/services/ai.py`
- Modify: `tests/test_ai.py`

**Interfaces:**
- Consumes: `ProductEvidence` from `scraper.py` and response models from `models.py`.
- Produces: `generate_analysis(evidence: ProductEvidence) -> AnalyzeResponse` and `enforce_script_limit(text: str, limit: int = 150) -> str`.

- [ ] **Step 1: Add tests for deterministic fallback and script length**

```python
from app.models import FieldValue, ProductInfo
from app.services.ai import build_fallback_analysis, enforce_script_limit
from app.services.scraper import ProductEvidence


def test_enforce_script_limit_counts_characters():
    text = "这个厨房神器开头就省时间，" + "好用" * 100
    assert len(enforce_script_limit(text)) <= 150


def test_fallback_analysis_uses_product_title():
    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual", confidence="medium"),
        core_features=["USB rechargeable"],
    )
    evidence = ProductEvidence(product=product, visible_text="USB rechargeable blender for travel", warnings=[])
    result = build_fallback_analysis(evidence)
    assert result.product.title.value == "Portable Blender"
    assert result.short_video_script.word_count <= 150
    assert result.short_video_script.hook
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ai.py -v`
Expected: FAIL with missing `app.services.ai`.

- [ ] **Step 3: Implement DeepSeek optional JSON completion with fallback**

If `DEEPSEEK_API_KEY` is absent or parsing fails, return deterministic Chinese analysis and warnings rather than failing the request.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_ai.py -v`
Expected: PASS.

### Task 4: API Routes And Frontend

**Files:**
- Create: `app/main.py`
- Create: `app/static/index.html`
- Create: `app/static/styles.css`
- Create: `app/static/app.js`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `fetch_product_evidence`, `generate_analysis`, `generate_video_assets`.
- Produces: `GET /`, `GET /health`, `POST /api/analyze`, `POST /api/generate-video`, and static file serving under `/static`.

- [ ] **Step 1: Write API tests**

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_analyze_accepts_manual_text_without_network():
    response = client.post(
        "/api/analyze",
        json={"url": "https://www.amazon.com/dp/B0TEST1234", "manual_text": "Portable Blender USB rechargeable 500ml"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"]
    assert data["short_video_script"]["word_count"] <= 150


def test_generate_video_returns_warning_when_tts_unconfigured():
    response = client.post(
        "/api/generate-video",
        json={"task_id": "abc", "product": {}, "analysis": {}, "short_video_script": {"script": "测试文案"}},
    )
    assert response.status_code == 200
    assert response.json()["warnings"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL with missing `app.main` or `app.services.media`.

- [ ] **Step 3: Implement routes and browser UI**

Keep the UI as a dense single-page tool with input, status, product card, analysis sections, script display, warnings, and video result.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS.

### Task 5: Optional Media Pipeline

**Files:**
- Create: `app/services/media.py`
- Modify: `app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `GenerateVideoRequest`.
- Produces: `generate_video_assets(request: GenerateVideoRequest) -> GenerateVideoResponse`.

- [ ] **Step 1: Implement safe optional media generation**

When DashScope credentials or FFmpeg/MoviePy are missing, return warnings. Always generate a simple local PNG cover with Pillow when possible.

- [ ] **Step 2: Ensure video endpoint never blocks main analysis**

Catch media errors and return partial URLs plus warnings.

- [ ] **Step 3: Run API tests**

Run: `pytest tests/test_api.py -v`
Expected: PASS.

### Task 6: Packaging, Docs, And Verification

**Files:**
- Create: `Dockerfile`
- Create: `README.md`
- Modify: `.gitignore` only if generated-path ignores are missing.

**Interfaces:**
- Produces: documented local startup, environment variable reference, Render deployment steps, known limits, and acceptance checklist.

- [ ] **Step 1: Add Docker packaging**

Install Python dependencies, Playwright Chromium dependencies, and FFmpeg; run Uvicorn on `$PORT`.

- [ ] **Step 2: Add README**

Document features, startup, deployment, environment variables, known limitations, and testing steps.

- [ ] **Step 3: Run final verification**

Run: `pytest -v` and `python -m compileall app tests`
Expected: all tests pass and Python files compile.
