from pathlib import Path


STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"


def test_sidebar_navigation_is_always_clickable_and_has_no_current_record_panel():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "当前记录" not in html
    assert 'id="saved-panel"' not in html
    assert "disabled" not in html
    assert "unlockPages" not in script
    assert "renderSavedLinks" not in script
    assert 'data-target="records-page"' in html


def test_hydrating_or_resetting_workspace_clears_stale_stage_views():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    hydrate_body = _function_body(script, "hydrateSavedRecord")
    reset_body = _function_body(script, "resetWorkspace")

    assert "clearWorkspaceData();" in hydrate_body
    assert "clearWorkspaceData();" in reset_body
    assert "function clearWorkspaceData()" in script


def test_frontend_displays_extraction_method_on_product_page():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    render_body = _function_body(script, "renderProduct")

    assert 'id="scrape-method"' in html
    assert "formatExtractionMethod(data.extraction_method)" in render_body
    assert "function formatExtractionMethod" in script
    assert "Firecrawl 抓取" in script


def test_frontend_renders_analysis_logic_without_standalone_evidence_panel():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    render_body = _function_body(script, "renderAnalysis")

    assert "renderAnalysisLogic(data.analysis?.content_logic || [])" in render_body
    assert "function renderAnalysisLogic" in script
    assert "analysis-logic" in script
    assert "内容启发" in script
    assert 'id="analysis-evidence"' not in html
    assert "function renderEvidence" not in script
    assert "renderEvidence(" not in script


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


def test_analysis_logic_uses_voiceover_copy_inspiration_wording():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    ai_source = (STATIC_DIR.parents[1] / "app" / "services" / "ai.py").read_text(encoding="utf-8")

    assert "口播文案内容启发" in script
    assert "口播文案内容启发" in ai_source
    assert "短视频内容启发" not in script
    assert "短视频内容启发" not in ai_source


def test_frontend_hides_legacy_analysis_lists_when_content_logic_exists():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    render_body = _function_body(script, "renderAnalysis")

    assert "const hasContentLogic = Boolean(data.analysis?.content_logic?.length);" in render_body
    assert "analysisRoot.classList.toggle('hidden', hasContentLogic);" in render_body
    assert "if (!hasContentLogic)" in render_body


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


def test_frontend_hydrates_legacy_video_audio_as_voice():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    hydrate_body = _function_body(script, "hydrateSavedRecord")

    assert "voiceResponseForRecord(record)" in hydrate_body
    assert "function voiceResponseForRecord(record)" in script
    assert "voice.audio_url || voice.remote_audio_url" in script


def test_saved_record_with_script_or_voice_opens_script_page():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")

    assert "function pageForHydratedRecord(record)" in script
    assert "showPage(pageForHydratedRecord(record));" in _function_body(script, "loadSavedResultFromPath")
    assert "showPage(pageForHydratedRecord(record));" in _function_body(script, "loadRecord")
    page_helper = _function_body(script, "pageForHydratedRecord")
    assert "record.voice_response" in page_helper
    assert "record.script_response" in page_helper
    assert "'script-page'" in page_helper


def test_history_detail_renders_hook_and_script_together():
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    detail_body = _function_body(script, "renderRecordDetail")

    assert "speechTextForShortVideoScript(script)" in detail_body
    assert "function speechTextForShortVideoScript" in script


def test_voice_controls_collapse_to_one_column_on_mobile():
    css = (STATIC_DIR / "styles.css").read_text(encoding="utf-8")
    mobile_block = css[css.index("@media (max-width: 560px)"):]

    assert ".voice-controls { grid-template-columns: 1fr; }" in mobile_block


def _function_body(script: str, name: str) -> str:
    function_marker = f"function {name}("
    async_function_marker = f"async function {name}("
    candidates = [index for marker in (function_marker, async_function_marker) if (index := script.find(marker)) != -1]
    start = min(candidates)
    next_function = script.find("\nfunction ", start + 1)
    next_async_function = script.find("\nasync function ", start + 1)
    stops = [index for index in (next_function, next_async_function) if index != -1]
    if not stops:
        return script[start:]
    return script[start:min(stops)]


def _event_listener_body(script: str, target: str, event: str) -> str:
    marker = f"{target}.addEventListener('{event}', async () => {{"
    start = script.index(marker)
    end = script.index("});", start)
    return script[start:end]
