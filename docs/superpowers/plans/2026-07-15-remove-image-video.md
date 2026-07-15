# Remove Image And Video Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove generated image and video functionality while preserving product analysis, script generation, and voice generation.

**Architecture:** Delete generated media models, route, workflow node, frontend state, storage summaries, prompts, and tests. Keep product image evidence fields such as `main_image_url` because they describe scraped product data, not generated media.

**Tech Stack:** FastAPI, Pydantic, static HTML/CSS/JS, pytest.

## Global Constraints

- Remove stale image and video generation surfaces so the app only presents product extraction, product analysis, oral script generation, and oral voice generation.
- Do not add script QA.
- Do not change product extraction, analysis QA, or voice generation behavior.
- Do not remove product image extraction fields such as `main_image_url`; they are product evidence, not generated image/video output.

---

### Task 1: Remove Generated Media From Backend Contracts

**Files:**
- Modify: `app/models.py`
- Modify: `app/main.py`
- Modify: `app/workflows/product_graph.py`
- Modify: `app/services/ai.py`
- Modify: `app/services/storage.py`
- Delete or stop using: `app/services/media.py`
- Test: `tests/test_ai.py`, `tests/test_api.py`, `tests/test_media.py`, `tests/test_workflow.py`

**Interfaces:**
- Produces: `GenerateScriptResponse` without `image_prompt`; no `GenerateVideoRequest` or `GenerateVideoResponse`; no `/api/generate-video` route.

- [ ] Remove `image_prompt` fields from response models and AI response creation.
- [ ] Remove generated video request/response models and route.
- [ ] Remove workflow video node and generated media service import.
- [ ] Remove storage summary fields for generated video/assets while preserving voice summary.
- [ ] Remove or ignore generated-media tests that only validate deleted behavior.

### Task 2: Remove Generated Media From Frontend

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css` if generated-video-only styles remain
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Produces: UI flow with product, analysis, script, and voice only.

- [ ] Remove video button/state/rendering and generated image/video preview elements.
- [ ] Preserve voice generation controls and audio playback.
- [ ] Update frontend tests to assert voice-only behavior where relevant.

### Task 3: Docs And Verification

**Files:**
- Modify: `README.md`
- Modify: docs only if stale generated-media mentions remain.

**Interfaces:**
- Produces: docs that do not promise generated image, cover, MP4, or video output.

- [ ] Grep for generated image/video terms and remove only stale generated-media references.
- [ ] Run targeted tests for API/frontend/model changes.
- [ ] Run full test suite.
- [ ] Run code review agent.
- [ ] Commit changes.

## Self-Review

- Spec coverage: tasks cover backend contracts, workflow, frontend, storage, tests, and docs.
- Placeholder scan: no placeholders.
- Type consistency: script response keeps `short_video_script` and `tts_text`; generated media fields are removed.
