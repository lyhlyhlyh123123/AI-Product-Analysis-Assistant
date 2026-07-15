# QA Voice Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automatic QA retry checkpoints, traceable product analysis, and replace the main video stage with configurable voiceover-audio generation.

**Architecture:** Extend the existing FastAPI + LangGraph staged workflow. Keep current extraction, analysis, and script endpoints compatible while adding QA fields and a new voice endpoint. Replace the frontend video page with a voiceover audio page and persist voice artifacts in saved records.

**Tech Stack:** FastAPI, Pydantic v2, LangGraph, DeepSeek chat completions, DashScope/Qwen TTS, pytest, static HTML/CSS/JS.

## Global Constraints

- QA rules check generated content to reduce factual errors and exaggerated claims.
- QA retries the previous generation stage automatically up to three times.
- Three failed QA attempts must return a manual-review status.
- Product analysis must include original product evidence for traceability.
- Main dashboard stage changes from video generation to voiceover audio generation.
- DashScope non-streaming TTS responses contain a remote audio URL valid for 24 hours, so backend should download and save a local artifact when possible.
- Do not commit secrets; `.env.example` must remain placeholder-only.

---

## File Structure

- `app/models.py`: add QA, evidence, and voice request/response schemas; extend existing stage responses with optional QA/evidence fields.
- `app/services/qa.py`: new rule-based QA service and retry helpers.
- `app/services/ai.py`: add evidence references to generated/fallback analysis and allow QA guidance for retries.
- `app/services/voice.py`: new DashScope/Qwen TTS voice service that downloads returned audio URLs.
- `app/services/storage.py`: persist product QA, analysis QA, and voice response; summarize QA/voice status.
- `app/workflows/product_graph.py`: insert QA retry before analysis and before script; add voice workflow runner.
- `app/main.py`: add QA and voice API routes.
- `app/static/index.html`: rename video page/stage to voiceover audio and add controls.
- `app/static/app.js`: wire QA display/evidence rendering/voice generation.
- `app/static/styles.css`: update asset/audio controls and QA/evidence display.
- Tests in `tests/test_qa.py`, `tests/test_voice.py`, `tests/test_workflow.py`, `tests/test_api.py`, and `tests/test_frontend_static.py`.

---

### Task 1: QA Models and Rule-Based Checks

**Files:**
- Modify: `app/models.py`
- Create: `app/services/qa.py`
- Test: `tests/test_qa.py`

**Interfaces:**
- Produces: `QAResult`, `EvidenceItem`, `qa_product_info(product, localized_product, visible_text, attempts=1) -> QAResult`, `qa_analysis(analysis, product, visible_text, attempts=1) -> QAResult`.

- [ ] **Step 1: Write failing QA tests**

Create `tests/test_qa.py` with tests asserting exaggerated/unsupported claims fail and grounded claims pass.

- [ ] **Step 2: Run QA tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_qa.py -q`
Expected: FAIL because `app.services.qa` or `QAResult` does not exist.

- [ ] **Step 3: Implement models and rule checks**

Add schemas and a focused rule-based QA implementation that catches absolute exaggeration keywords and missing evidence.

- [ ] **Step 4: Run QA tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_qa.py -q`
Expected: PASS.

---

### Task 2: Analysis Evidence Traceability

**Files:**
- Modify: `app/models.py`
- Modify: `app/services/ai.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Produces: `GenerateAnalysisResponse.evidence: list[EvidenceItem]`.

- [ ] **Step 1: Write failing evidence test**

Add a test that `generate_product_analysis()` returns non-empty evidence referencing product fields or visible text.

- [ ] **Step 2: Run evidence test**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_ai.py::test_generate_product_analysis_includes_evidence -q`
Expected: FAIL because `evidence` is absent.

- [ ] **Step 3: Implement minimal evidence generation**

Attach evidence items for generated analysis claims using product title/features/specifications and visible text excerpts.

- [ ] **Step 4: Run evidence test**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_ai.py::test_generate_product_analysis_includes_evidence -q`
Expected: PASS.

---

### Task 3: Workflow QA Retry and Persistence

**Files:**
- Modify: `app/workflows/product_graph.py`
- Modify: `app/services/storage.py`
- Modify: `app/main.py`
- Test: `tests/test_workflow.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `run_qa_product_info`, `run_qa_analysis`, QA fields in saved records.

- [ ] **Step 1: Write failing workflow/API tests**

Add tests that QA results are persisted, analysis response carries `product_qa`, script response carries `analysis_qa`, and failed QA stops at manual review after three attempts.

- [ ] **Step 2: Run workflow/API tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_workflow.py tests/test_api.py -q`
Expected: FAIL because QA workflow fields/routes do not exist.

- [ ] **Step 3: Implement QA persistence and workflow calls**

Call QA before analysis/script generation, retry up to three times, save QA result fields, add explicit QA endpoints.

- [ ] **Step 4: Run workflow/API tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_workflow.py tests/test_api.py -q`
Expected: PASS.

---

### Task 4: Voiceover Audio Service

**Files:**
- Modify: `app/models.py`
- Create: `app/services/voice.py`
- Modify: `app/workflows/product_graph.py`
- Modify: `app/services/storage.py`
- Modify: `app/main.py`
- Test: `tests/test_voice.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Produces: `GenerateVoiceRequest`, `GenerateVoiceResponse`, `generate_voice_audio(request, settings=None) -> GenerateVoiceResponse`, `/api/generate-voice`.

- [ ] **Step 1: Write failing voice tests**

Test DashScope payload uses configurable model/voice/instruction/format/sample rate, downloads returned remote URL to local output, and persists `voice_response`.

- [ ] **Step 2: Run voice tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_voice.py -q`
Expected: FAIL because voice service/models do not exist.

- [ ] **Step 3: Implement voice service and route**

Call Qwen TTS endpoint, download remote audio URL when returned, save local artifact, return local and remote URLs plus warnings.

- [ ] **Step 4: Run voice tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_voice.py -q`
Expected: PASS.

---

### Task 5: Frontend Voice and QA UI

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes: response fields `product_qa`, `analysis_qa`, `evidence`, `voice_url`, `remote_audio_url`.

- [ ] **Step 1: Write failing frontend static tests**

Assert sidebar contains `口播语音`, not `带货短视频`; JS calls `/api/generate-voice`; UI contains voice controls and QA containers.

- [ ] **Step 2: Run frontend static tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py -q`
Expected: FAIL because current UI still exposes video stage names/routes.

- [ ] **Step 3: Update static UI**

Rename page/stage, add audio controls, render QA status/evidence, post to `/api/generate-voice`.

- [ ] **Step 4: Run frontend static tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_frontend_static.py -q`
Expected: PASS.

---

### Task 6: Full Verification and Review

**Files:**
- All modified files.

**Interfaces:**
- Verifies full app behavior.

- [ ] **Step 1: Run full tests**

Run: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Run code review**

Use a code-review agent focused on QA retry correctness, evidence traceability, TTS persistence, and frontend stale state.

- [ ] **Step 3: Address confirmed review findings with TDD**

For every confirmed bug, add a failing test first, then fix and rerun tests.

---

## Self-Review

Spec coverage: the tasks cover QA rules, retry behavior, evidence traceability, voice generation, frontend changes, persistence, and tests.

Placeholder scan: no TBD/TODO placeholders remain.

Type consistency: model names and service function names are consistent across tasks.
