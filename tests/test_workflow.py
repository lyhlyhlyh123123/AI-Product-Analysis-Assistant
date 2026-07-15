# Importers/callers: pytest validates app.workflows.product_graph LangGraph orchestration functions.
# Affected API: no public API changes; tests cover the workflow layer used by staged FastAPI routes.
# Data schemas: uses existing Pydantic request/response models and saved record shape.
# User instruction: "可以的进行优化吧"

from app.config import Settings
from app.models import AnalysisResult, ExtractProductRequest, GenerateAnalysisRequest, GenerateScriptRequest, GenerateVoiceRequest, LocalizedProductInfo, ProductInfo, FieldValue
from app.services import storage
from app.workflows.product_graph import run_analyze_product, run_extract_product, run_generate_script, run_generate_voice


def use_temp_settings(monkeypatch, tmp_path):
    settings = Settings(output_dir=tmp_path)
    monkeypatch.setattr("app.services.ai.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.services.media.Settings.from_env", lambda: settings)
    monkeypatch.setattr("app.services.storage.Settings.from_env", lambda: settings)
    return settings


def test_langgraph_staged_workflow(monkeypatch, tmp_path):
    settings = use_temp_settings(monkeypatch, tmp_path)

    product = run_extract_product(
        ExtractProductRequest(input_method="manual", manual_text="Portable Blender\nUSB rechargeable\n500ml")
    )
    assert product.product.title.value == "Portable Blender"
    assert product.localized_product.title

    analysis = run_analyze_product(
        GenerateAnalysisRequest(task_id=product.task_id, product=product.product, localized_product=product.localized_product, visible_text=product.visible_text, warnings=product.warnings)
    )
    assert analysis.product_qa.passed is True
    assert analysis.analysis.selling_points
    assert analysis.evidence

    script = run_generate_script(
        GenerateScriptRequest(task_id=analysis.task_id, product=analysis.product, analysis=analysis.analysis, visible_text=product.visible_text, warnings=analysis.warnings)
    )
    assert script.analysis_qa.passed is True
    assert script.short_video_script.script
    assert script.short_video_script.word_count <= 150

    voice = run_generate_voice(GenerateVoiceRequest(task_id=script.task_id, text=script.tts_text or script.short_video_script.script))
    assert voice.warnings

    record = storage.load_result_record(product.task_id, settings.output_dir)
    assert record["product_response"]
    assert record["product_qa_response"]
    assert record["stage_analysis_response"]
    assert record["analysis_qa_response"]
    assert record["script_response"]
    assert record["voice_response"]


def test_product_qa_checks_localized_product_claims(monkeypatch, tmp_path):
    use_temp_settings(monkeypatch, tmp_path)
    product = ProductInfo(title=FieldValue(value="Portable Blender", source="manual"), core_features=["USB rechargeable"])
    localized = LocalizedProductInfo(title="便携榨汁杯", core_features=["USB 充电", "全网最强性能"])

    analysis = run_analyze_product(
        GenerateAnalysisRequest(task_id="qa-localized", product=product, localized_product=localized, visible_text="Portable Blender USB rechargeable")
    )

    assert analysis.product_qa.passed is True
    assert analysis.product_qa.attempts == 2
    assert "全网最强性能" not in analysis.localized_product.core_features


def test_product_qa_retry_cleans_localized_title_and_specs(monkeypatch, tmp_path):
    use_temp_settings(monkeypatch, tmp_path)
    product = ProductInfo(title=FieldValue(value="Portable Blender", source="manual"), core_features=["USB rechargeable"])
    localized = LocalizedProductInfo(
        title="全球第一榨汁杯",
        core_features=["USB 充电"],
        specifications={"功效": "100%保护视力", "容量": "500ml"},
    )

    analysis = run_analyze_product(
        GenerateAnalysisRequest(task_id="qa-localized-specs", product=product, localized_product=localized, visible_text="Portable Blender USB rechargeable 500ml")
    )

    assert analysis.product_qa.passed is True
    assert analysis.product_qa.attempts == 2
    assert analysis.localized_product.title == "unknown"
    assert "功效" not in analysis.localized_product.specifications
    assert analysis.localized_product.specifications == {"容量": "500ml"}


def test_analysis_qa_receives_visible_text_evidence(monkeypatch, tmp_path):
    use_temp_settings(monkeypatch, tmp_path)
    captured = {}

    def fake_qa_analysis(analysis, product, visible_text, attempts=1):
        captured.setdefault("visible_text", visible_text)
        from app.models import QAResult

        return QAResult(stage="analysis", status="passed", passed=True, attempts=attempts)

    monkeypatch.setattr("app.workflows.product_graph.qa_analysis", fake_qa_analysis)
    product = ProductInfo(title=FieldValue(value="Desk Lamp", source="manual"))
    analysis = AnalysisResult(selling_points=["适合夜间阅读"])

    script = run_generate_script(
        GenerateScriptRequest(task_id="qa-visible-text", product=product, analysis=analysis, visible_text="Desk Lamp 适合夜间阅读")
    )

    assert script.analysis_qa.passed is True
    assert captured["visible_text"] == "Desk Lamp 适合夜间阅读"


def test_analysis_qa_cleaned_content_is_used_for_script(monkeypatch, tmp_path):
    use_temp_settings(monkeypatch, tmp_path)
    product = ProductInfo(title=FieldValue(value="Desk Lamp", source="manual"), core_features=["Adjustable brightness"])
    analysis = AnalysisResult(
        selling_points=["全球第一护眼效果", "可调亮度方便夜间阅读"],
        content_angles=["展示亮度调节"],
    )

    script = run_generate_script(
        GenerateScriptRequest(task_id="qa-clean-analysis", product=product, analysis=analysis, visible_text="Desk Lamp Adjustable brightness")
    )

    assert script.analysis_qa.passed is True
    assert script.analysis_qa.attempts == 2
    assert "全球第一护眼效果" not in script.analysis.selling_points
    assert script.analysis.selling_points == ["可调亮度方便夜间阅读"]
