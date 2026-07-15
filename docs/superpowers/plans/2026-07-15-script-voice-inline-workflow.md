# Script Voice Inline Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge voice selection/creation and voice generation into the video script page, require a selected or newly created voice before generation, and ensure speech text always includes hook plus body.

**Architecture:** Keep the existing staged FastAPI/static frontend architecture. Tighten the backend script response contract so `tts_text` is generated from the same helper that the frontend mirrors, then update the static frontend to make `script-page` the only voice workspace and remove the separate `video-page` navigation/page.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, static HTML/CSS/JavaScript, DashScope REST voice service.

## Global Constraints

- The generated speech must include both the hook and the body text.
- The independent `口播语音` sidebar/page must be removed.
- Voice generation must not call `/api/generate-voice` until a script exists and `#voice-select` has a non-empty `voice_id`.
- Creating a voice must automatically select the returned `voice_id`.
- History loading must render existing voice audio on the `视频口播文案` page.
- Do not change DashScope voice creation or synthesis endpoints beyond existing behavior.

---

### Task 1: Backend TTS Text Contract

**Files:**
- Modify: `app/services/ai.py:68-80`
- Modify: `app/services/ai.py:169-187`
- Modify: `app/services/ai.py:253-268`
- Test: `tests/test_ai.py`

**Interfaces:**
- Consumes: `ShortVideoScript(hook: str, script: str, word_count: int)` from `app.models`.
- Produces: `_speech_text_for_script(script: ShortVideoScript) -> str`, used by `generate_short_video_script`, `_generate_script_with_deepseek`, and `_response_from_ai_data` to populate `tts_text`.

- [ ] **Step 1: Add failing backend test for fallback staged script**

Append to `tests/test_ai.py`:

```python
def test_generate_short_video_script_tts_text_includes_hook_and_body():
    from app.services.ai import generate_short_video_script

    product = ProductInfo(title=FieldValue(value="便携榨汁杯", source="manual"))
    analysis = AnalysisResult(selling_points=["通勤携带", "USB 充电"])

    response = generate_short_video_script("abc", product, analysis, [])

    assert response.short_video_script.hook
    assert response.short_video_script.script
    assert response.tts_text == f"{response.short_video_script.hook}\n{response.short_video_script.script}"
```

- [ ] **Step 2: Add failing backend test for normalized AI response**

Append to `tests/test_ai.py`:

```python
def test_ai_response_normalizes_tts_text_to_hook_plus_script():
    evidence = ProductEvidence(product=ProductInfo(), visible_text="", warnings=[])
    result = _response_from_ai_data(
        {
            "product": {"title": "Portable Blender"},
            "analysis": {"selling_points": ["便携"]},
            "short_video_script": {"hook": "先看这一点", "script": "这款便携榨汁杯适合通勤。", "word_count": 16},
            "tts_text": "只读正文的旧文本",
        },
        evidence,
    )

    assert result.tts_text == "先看这一点\n这款便携榨汁杯适合通勤。"
```

- [ ] **Step 3: Run backend tests and verify RED**

Run: `python -m pytest tests/test_ai.py::test_generate_short_video_script_tts_text_includes_hook_and_body tests/test_ai.py::test_ai_response_normalizes_tts_text_to_hook_plus_script -q`

Expected: both fail because `tts_text` still uses old script-only or model-provided text.

- [ ] **Step 4: Implement shared backend speech helper**

In `app/services/ai.py`, add after `enforce_script_limit`:

```python
def _speech_text_for_script(script: ShortVideoScript) -> str:
    parts = [script.hook.strip(), script.script.strip()]
    return "\n".join(part for part in parts if part)
```

Update `generate_short_video_script` return paths:

```python
script, image_prompt, _ = _generate_script_with_deepseek(product, analysis, settings)
return GenerateScriptResponse(task_id=task_id, product=product, analysis=analysis, short_video_script=script, image_prompt=image_prompt, tts_text=_speech_text_for_script(script), warnings=warnings)
```

```python
script = _fallback_script_for_product(product, analysis)
return GenerateScriptResponse(task_id=task_id, product=product, analysis=analysis, short_video_script=script, image_prompt=_image_prompt_for_product(product), tts_text=_speech_text_for_script(script), warnings=warnings)
```

Update `_generate_script_with_deepseek` so it returns helper-derived text:

```python
tts_text = _speech_text_for_script(script)
return script, image_prompt, tts_text
```

Update `_response_from_ai_data`:

```python
tts_text=_speech_text_for_script(script),
```

- [ ] **Step 5: Run backend tests and verify GREEN**

Run: `python -m pytest tests/test_ai.py -q`

Expected: PASS.

---

### Task 2: Inline Voice UI And Gating

**Files:**
- Modify: `app/static/index.html:20-201`
- Modify: `app/static/app.js:1-274`
- Modify: `app/static/app.js:292-469`
- Modify: `app/static/styles.css:243-253`
- Test: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes: `stageState.script.short_video_script.hook`, `stageState.script.short_video_script.script`, `voice_select.value`.
- Produces: `speechTextForScript(scriptResponse) -> string`, `updateVoiceGenerationAvailability() -> void`, and inline voice rendering inside `script-page`.

- [ ] **Step 1: Replace static frontend expectations with failing tests**

Modify `test_frontend_uses_voiceover_audio_stage_with_qa_containers` in `tests/test_frontend_static.py` to:

```python
def test_frontend_inlines_voice_controls_on_script_page():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    script_page = html[html.index('id="script-page"'):html.index('id="records-page"')]

    assert 'data-target="video-page"' not in html
    assert 'id="video-page"' not in html
    assert "带货短视频" not in html
    assert "/api/generate-voice" in script
    assert "/api/generate-video" not in script
    assert 'id="product-qa"' in html
    assert 'id="analysis-qa"' in html
    assert 'id="voice-instruction"' in script_page
    assert 'id="voice-format"' in script_page
    assert 'id="sample-rate"' in script_page
    assert 'id="voice-select"' in script_page
    assert 'id="create-voice-button"' in script_page
    assert 'id="video-panel"' in script_page
    assert "/api/voices" in script
    assert "history-load" not in script
    assert "打开</button>" not in script
```

Append two new tests:

```python
def test_frontend_voice_generation_requires_selected_voice_before_request():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    handler_body = _event_listener_body(script, "videoButton", "click")

    assert "const selectedVoiceId = document.querySelector('#voice-select').value" in handler_body
    assert "请先创建或选择音色" in handler_body
    assert "if (!selectedVoiceId)" in handler_body
    assert handler_body.index("if (!selectedVoiceId)") < handler_body.index("postJson('/api/generate-voice'")


def test_frontend_voice_generation_uses_hook_plus_script_text():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    helper_body = _function_body(script, "speechTextForScript")
    handler_body = _event_listener_body(script, "videoButton", "click")

    assert "short_video_script?.hook" in helper_body
    assert "short_video_script?.script" in helper_body
    assert "join('\\n')" in helper_body
    assert "const text = speechTextForScript(stageState.script);" in handler_body
```

Add helper at the bottom of `tests/test_frontend_static.py`:

```python
def _event_listener_body(script: str, target: str, event: str) -> str:
    marker = f"{target}.addEventListener('{event}', async () => {{"
    start = script.index(marker)
    end = script.index("});", start)
    return script[start:end]
```

- [ ] **Step 2: Run frontend static tests and verify RED**

Run: `python -m pytest tests/test_frontend_static.py -q`

Expected: FAIL because `video-page` still exists, controls are outside `script-page`, helper functions do not exist, and generation does not gate selected voice before posting.

- [ ] **Step 3: Update HTML layout**

In `app/static/index.html`:

Remove the nav item:

```html
<button type="button" class="nav-item" data-target="video-page">口播语音</button>
```

Replace `script-page` and remove the whole `video-page` section with this single `script-page` section:

```html
<section class="page" id="script-page" data-title="视频口播文案">
  <article class="panel script-panel">
    <div class="panel-heading">
      <span class="step">04</span>
      <div>
        <h2>视频口播文案</h2>
        <p>150 字以内，前 5 秒有吸引继续观看的钩子。</p>
      </div>
    </div>
    <section class="script-copy">
      <strong id="script-hook"></strong>
      <p id="script-body"></p>
    </section>
    <section class="voice-workspace" aria-label="口播语音设置">
      <div class="voice-controls">
        <label>已保存音色
          <select id="voice-select"><option value="">先创建或选择音色</option></select>
        </label>
        <label>音色名称
          <input id="voice-id" type="text" value="custom_voice">
        </label>
        <label>声音描述
          <textarea id="voice-instruction" rows="3" placeholder="年轻活泼的女性声音，语速偏快，适合介绍时尚产品"></textarea>
        </label>
        <label>音频格式
          <select id="voice-format">
            <option value="wav">wav</option>
            <option value="mp3">mp3</option>
          </select>
        </label>
        <label>采样率
          <input id="sample-rate" type="number" value="24000" min="8000" step="1000">
        </label>
        <button id="create-voice-button" type="button">创建音色</button>
      </div>
      <button id="video-button" type="button" disabled>制作口播语音</button>
      <div id="video-panel" class="video-panel hidden">
        <audio id="voice-audio" controls class="audio-player hidden"></audio>
        <div id="download-links" class="download-links"></div>
      </div>
      <div id="asset-empty" class="empty-state">尚未生成口播语音</div>
    </section>
  </article>
</section>
```

- [ ] **Step 4: Update frontend JavaScript gating and speech text**

In `app/static/app.js`:

After `createVoiceButton.addEventListener('click', createVoiceProfile);`, add:

```javascript
document.querySelector('#voice-select').addEventListener('change', updateVoiceGenerationAvailability);
```

In the script generation success path after `renderScript(data);`, add:

```javascript
updateVoiceGenerationAvailability();
```

Replace `videoButton.addEventListener('click', async () => { ... });` with:

```javascript
videoButton.addEventListener('click', async () => {
  if (!stageState.script) return;
  const selectedVoiceId = document.querySelector('#voice-select').value;
  if (!selectedVoiceId) {
    setStatus('请先创建或选择音色');
    updateVoiceGenerationAvailability();
    return;
  }
  setStatus('生成口播语音中...');
  videoButton.disabled = true;
  try {
    const text = speechTextForScript(stageState.script);
    const data = await postJson('/api/generate-voice', {
      task_id: stageState.script.task_id,
      text,
      voice: document.querySelector('#voice-id').value || 'custom_voice',
      voice_id: selectedVoiceId,
      voice_instruction: document.querySelector('#voice-instruction').value || '',
      audio_format: document.querySelector('#voice-format').value || 'wav',
      sample_rate: Number(document.querySelector('#sample-rate').value || 24000),
    });
    stageState.video = data;
    renderVoice(data);
    renderWarnings([...(stageState.script.warnings || []), ...(data.warnings || [])]);
    loadRecordsList();
    setStatus(data.audio_url ? '口播语音生成完成' : '口播语音生成被跳过');
  } catch (error) {
    setStatus(`口播语音生成失败：${error.message}`);
  } finally {
    updateVoiceGenerationAvailability();
  }
});
```

After `renderVoiceOptions`, add:

```javascript
function updateVoiceGenerationAvailability() {
  const selectedVoiceId = document.querySelector('#voice-select').value;
  videoButton.disabled = !stageState.script || !selectedVoiceId;
}

function speechTextForScript(scriptResponse) {
  const script = scriptResponse?.short_video_script || {};
  return [script.hook, script.script].map((part) => String(part || '').trim()).filter(Boolean).join('\n');
}
```

In `renderVoiceOptions`, add before closing:

```javascript
updateVoiceGenerationAvailability();
```

In `createVoiceProfile`, after setting `#voice-select` to `data.profile.voice_id`, add:

```javascript
updateVoiceGenerationAvailability();
```

In `hydrateSavedRecord`, after `renderScript(stageState.script);`, add:

```javascript
updateVoiceGenerationAvailability();
```

In `clearWorkspaceData`, after resetting audio elements, add:

```javascript
updateVoiceGenerationAvailability();
```

Do not call `showPage('video-page')` after voice generation.

- [ ] **Step 5: Update CSS for inline voice workspace**

In `app/static/styles.css`, keep `.script-panel` and replace the script/voice area styles with:

```css
.script-panel { display: grid; gap: 16px; align-content: start; }
.script-copy { display: grid; gap: 10px; }
#script-hook { color: #0f766e; line-height: 1.55; font-size: 1.02rem; }
#script-body { margin: 0; line-height: 1.7; color: #263238; }
.voice-workspace { display: grid; gap: 14px; border-top: 1px solid #e2e8ec; padding-top: 16px; }
.video { width: min(300px, 100%); aspect-ratio: 9 / 16; background: #111827; border-radius: 8px; }
.audio-player { width: min(560px, 100%); }
.voice-controls { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 14px; }
.voice-controls textarea { min-height: 92px; }
.voice-controls select { width: 100%; border: 1px solid #b8c3c8; border-radius: 6px; padding: 12px 14px; font: inherit; color: #172026; background: #fff; }
```

- [ ] **Step 6: Run frontend static tests and verify GREEN**

Run: `python -m pytest tests/test_frontend_static.py -q`

Expected: PASS.

---

### Task 3: Full Verification And Review Cleanup

**Files:**
- Verify: `app/services/ai.py`
- Verify: `app/static/index.html`
- Verify: `app/static/app.js`
- Verify: `app/static/styles.css`
- Verify: `tests/test_ai.py`
- Verify: `tests/test_frontend_static.py`

**Interfaces:**
- Consumes: backend helper `_speech_text_for_script(script: ShortVideoScript) -> str` and frontend helper `speechTextForScript(scriptResponse) -> string`.
- Produces: a green test suite and reviewed implementation.

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest -q`

Expected: PASS. Existing dependency warnings from Pydantic/LangGraph may appear; failures must be fixed.

- [ ] **Step 2: Inspect current diff**

Run: `git diff -- app/services/ai.py app/static/index.html app/static/app.js app/static/styles.css tests/test_ai.py tests/test_frontend_static.py docs/superpowers/specs/2026-07-15-script-voice-inline-workflow-design.md docs/superpowers/plans/2026-07-15-script-voice-inline-workflow.md`

Expected: Diff only includes the approved script/voice inline workflow changes and docs.

- [ ] **Step 3: Run required code review**

Use the `ecc:python-reviewer` or `ecc:code-reviewer` agent to review the Python/static workflow changes. Ask it to focus on hook-plus-body correctness, selected voice gating, history rendering, and regressions.

- [ ] **Step 4: Fix any confirmed review findings with tests first**

If review finds a confirmed defect, add the smallest failing test in `tests/test_ai.py` or `tests/test_frontend_static.py`, run it to verify RED, implement the fix, and rerun focused plus full tests.

- [ ] **Step 5: Final verification**

Run: `python -m pytest -q`

Expected: PASS.
