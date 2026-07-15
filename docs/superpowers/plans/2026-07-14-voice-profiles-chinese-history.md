# Voice Profiles Chinese History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable DashScope voice profiles, select saved voices from the voiceover page, keep history artifacts inline, and enforce Chinese output outside raw product fields.

**Architecture:** Add a small JSON-backed voice profile store beside existing output records. Split voice creation from voice synthesis: `/api/voices` creates/lists saved voice IDs, `/api/generate-voice` uses a selected saved voice. Keep raw extracted product fields unchanged, while localized product, analysis, QA summaries, scripts, and UI labels remain Chinese.

**Tech Stack:** FastAPI, Pydantic v2, static HTML/CSS/JS, DashScope SDK, httpx, pytest.

## Global Constraints

- Raw scraped product information can remain English.
- All non-raw generated outputs must be Chinese.
- Voice design creates reusable voice profiles and should not run on every audio generation if a saved voice is selected.
- History records expand inline and should show artifacts without navigating away.
- Use TDD: add failing tests before implementation.

---

## Tasks

### Task 1: Voice Profile Store and API

**Files:**
- Modify: `app/models.py`
- Create: `app/services/voices.py`
- Modify: `app/main.py`
- Test: `tests/test_voice.py`

**Interfaces:**
- `VoiceProfile(id, voice_id, name, prompt, model, created_at)`
- `CreateVoiceRequest(name, prompt, sample_rate, audio_format)`
- `CreateVoiceResponse(profile, warnings)`
- `list_voice_profiles(settings=None) -> list[VoiceProfile]`
- `create_voice_profile(request, settings=None) -> CreateVoiceResponse`
- Routes: `GET /api/voices`, `POST /api/voices`

**Steps:**
- [ ] Add tests that `POST /api/voices` creates a voice through customization and saves it to `outputs/voices.json`.
- [ ] Add tests that `GET /api/voices` lists saved voices.
- [ ] Implement models, JSON store, and routes.
- [ ] Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_voice.py -q`.

### Task 2: Generate Voice Uses Saved Voice

**Files:**
- Modify: `app/models.py`
- Modify: `app/services/voice.py`
- Test: `tests/test_voice.py`

**Interfaces:**
- Extend `GenerateVoiceRequest` with `voice_id`.
- If `voice_id` is provided, `generate_voice_audio()` skips voice design and calls `dashscope.MultiModalConversation.call` directly.
- If `voice_id` is missing, it may create a voice from `voice_instruction` and save/reuse behavior remains available through `/api/voices`.

**Steps:**
- [ ] Add test proving selected `voice_id` skips customization request.
- [ ] Implement voice_id path.
- [ ] Run targeted voice tests.

### Task 3: Chinese Output Enforcement

**Files:**
- Modify: `app/services/ai.py`
- Modify: `app/services/qa.py`
- Test: `tests/test_ai.py`

**Interfaces:**
- Fallback analysis/script output strings are Chinese.
- DeepSeek prompts explicitly require Chinese for localized product, analysis, script, QA guidance.
- Raw `ProductInfo` remains unchanged.

**Steps:**
- [ ] Add tests that fallback `generate_product_analysis()` and `generate_short_video_script()` do not return English-only analysis/script content.
- [ ] Strengthen prompts and fallback copy.
- [ ] Run targeted AI tests.

### Task 4: Frontend Voice Dropdown and Inline History

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Voice page loads `GET /api/voices` into a dropdown.
- Create voice button calls `POST /api/voices`.
- Generate voice sends selected `voice_id` to `/api/generate-voice`.
- History record details expand inline with audio player/download link and no primary jump/open behavior.

**Steps:**
- [ ] Add static tests for `voice-select`, `/api/voices`, `create-voice-button`, and no `history-load` jump button.
- [ ] Implement frontend controls and inline history rendering.
- [ ] Run frontend tests.

### Task 5: Full Verification

**Steps:**
- [ ] Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q`.
- [ ] Review changed voice/AI/frontend paths for regressions.

## Self-Review

Spec coverage: reusable voices, dropdown selection, inline history, and Chinese output are covered.

Placeholder scan: no TBD/TODO placeholders.

Type consistency: request/response names match task interfaces.
