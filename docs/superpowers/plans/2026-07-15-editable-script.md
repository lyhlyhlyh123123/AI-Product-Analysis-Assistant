# Editable Script Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit generated oral copy, save it to the current record, and generate voice from the edited text.

**Architecture:** Add a small PATCH endpoint that updates a saved record's `script_response.short_video_script` and `tts_text`. Replace read-only script text with editable controls on the script page and update frontend state after save.

**Tech Stack:** FastAPI, Pydantic, static HTML/CSS/JS, JSON file storage.

## Global Constraints

- Hook and script body are editable on the script page.
- Save updates `stageState.script.short_video_script`, `tts_text`, and persisted `script_response`.
- Voice generation reads the edited text.
- No script QA, edit history, AI regeneration, or test run is required for this change.

---

### Task 1: Add Script Save API

**Files:**
- Modify: `app/models.py`
- Modify: `app/services/storage.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `UpdateScriptRequest(hook: str, script: str)`.
- Produces: `PATCH /api/results/{task_id}/script -> GenerateScriptResponse`.

- [ ] Add request model.
- [ ] Add storage helper to update `script_response.short_video_script` and `tts_text`.
- [ ] Add FastAPI PATCH route.

### Task 2: Add Editable Frontend Controls

**Files:**
- Modify: `app/static/index.html`
- Modify: `app/static/app.js`
- Modify: `app/static/styles.css`

**Interfaces:**
- Produces: editable hook/body fields and save behavior.

- [ ] Replace read-only hook/body with editable input/textarea.
- [ ] Add save button.
- [ ] Render generated scripts into editable controls.
- [ ] Save edits through PATCH and update `stageState.script`.
- [ ] Read voice text from editable controls.

### Task 3: Static Review

**Files:**
- Review changed files only.

**Interfaces:**
- Produces: no known selector/import mismatch.

- [ ] Grep for stale selectors.
- [ ] Run code review agent only; do not run tests.
- [ ] Leave commit/push to user unless requested.

## Self-Review

- Spec coverage: covers backend save, frontend editing, persisted script response, and edited voice input.
- Placeholder scan: no placeholders.
- Type consistency: `UpdateScriptRequest`, `short_video_script`, and `tts_text` names match existing models.
