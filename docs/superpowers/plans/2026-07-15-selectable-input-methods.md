# Selectable Input Methods Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users choose Firecrawl, local scraping, or manual paste as the product information source, with strict no-fallback behavior.

**Architecture:** Add an `input_method` request field and route extraction through one explicit backend path. Update the static frontend to show only the URL field for scrape methods and only the paste field for manual mode. Use `firecrawl-py` SDK for Firecrawl page retrieval and reuse existing HTML extraction logic.

**Tech Stack:** FastAPI, Pydantic, static HTML/CSS/JS, BeautifulSoup, httpx, firecrawl-py.

## Global Constraints

- Default input method is `firecrawl`.
- Firecrawl and local methods require a URL and hide manual paste input.
- Manual method requires pasted product text and hides URL input.
- Extraction is strict: do not automatically fall back from the selected method to another method.
- User requested no new tests and no test run for this change.

---

### Task 1: Backend Request Contract And Extraction Routing

**Files:**
- Modify: `app/models.py`
- Modify: `app/services/scraper.py`
- Modify: `app/workflows/product_graph.py`
- Modify: `app/main.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: `ExtractProductRequest.input_method`, `url`, `manual_text`.
- Produces: `fetch_product_evidence(url: str | None, manual_text: str | None = None, settings: Settings | None = None, input_method: InputMethod = "firecrawl") -> ProductEvidence`.

- [ ] Add `InputMethod = Literal["firecrawl", "local", "manual"]` and make `ExtractProductRequest.url` optional.
- [ ] Add validation rules requiring URL for `firecrawl/local` and manual text for `manual`.
- [ ] Update extraction callers to pass `request.input_method`.
- [ ] Replace the direct Firecrawl HTTP POST with `firecrawl-py` SDK `Firecrawl.scrape(url, formats=["markdown", "html"])`.
- [ ] Keep strict selected-method behavior: Firecrawl failure returns `firecrawl_failed`; local failure returns `local_failed`; manual failure raises validation.
- [ ] Add `firecrawl-py` to `requirements.txt`.

### Task 2: Frontend Source Selector

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`

**Interfaces:**
- Consumes: backend `input_method` request field.
- Produces: a form that submits only the selected method's required input.

- [ ] Add a dropdown with options `firecrawl`, `local`, and `manual`, defaulting to `firecrawl`.
- [ ] Wrap URL and manual textarea fields in containers that can be hidden.
- [ ] Show URL only for `firecrawl/local`; show manual textarea only for `manual`.
- [ ] Submit `input_method` and only the active input value.
- [ ] Extend `formatExtractionMethod` labels for failed strict modes.

### Task 3: Documentation Touch-Up

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: new dependency and Firecrawl SDK behavior.
- Produces: docs that describe the user-selectable source method and Firecrawl env var.

- [ ] Mention selectable information source in README features and API example.
- [ ] Add Firecrawl env vars to README and `.env.example` if missing.

## Self-Review

- Spec coverage: covers method selection, strict behavior, SDK Firecrawl scrape, conditional frontend fields, labels, and dependency/docs.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: `input_method` and `InputMethod` are consistently named.
