from pathlib import Path

from app.config import Settings
from app.models import AnalysisResult, AnalyzeResponse, FieldValue, ProductInfo
from app.services.ai import _deepseek_json, _extract_json_object, _generate_script_with_deepseek, _response_from_ai_data, build_fallback_analysis, enforce_script_limit
from app.services.scraper import ProductEvidence


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_field_value_defaults_are_unknown():
    field = FieldValue()
    assert field.value == "unknown"
    assert field.source == "unknown"
    assert "confidence" not in field.model_dump()


def test_analyze_response_serializes_nested_models():
    response = AnalyzeResponse(task_id="abc", product=ProductInfo())
    data = response.model_dump()
    assert data["product"]["title"]["value"] == "unknown"


def test_enforce_script_limit_counts_characters():
    text = "这个厨房神器开头就省时间，" + "好用" * 100
    assert len(enforce_script_limit(text)) <= 150


def test_extract_json_object_sanitizes_control_characters_inside_strings():
    content = '{"analysis": {"selling_points": ["第一行\n第二行"]}}'

    data = _extract_json_object(content)

    assert data["analysis"]["selling_points"] == ["第一行\n第二行"]


def test_deepseek_json_requests_json_mode_with_max_tokens(monkeypatch):
    captured = {}

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["payload"] = json
        return DummyResponse()

    monkeypatch.setattr("app.services.ai.httpx.post", fake_post)

    result = _deepseek_json(Settings(deepseek_api_key="deepseek-key"), "只输出 JSON 对象。", {"task": "返回 JSON"})

    assert result == {"ok": True}
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["max_tokens"] == 5000
    assert "JSON" in captured["payload"]["messages"][0]["content"] or "json" in captured["payload"]["messages"][0]["content"].lower()


def test_fallback_analysis_uses_product_title():
    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual"),
        core_features=["USB rechargeable"],
    )
    evidence = ProductEvidence(product=product, visible_text="USB rechargeable blender for travel", warnings=[])
    result = build_fallback_analysis(evidence)
    assert result.product.title.value == "Portable Blender"
    assert result.short_video_script.word_count <= 150
    assert result.short_video_script.hook


def test_fallback_localized_product_is_chinese_not_raw_english():
    from app.services.ai import localize_product_info

    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual"),
        core_features=["USB rechargeable", "500ml capacity"],
    )

    localized, _ = localize_product_info(product, "Portable Blender USB rechargeable 500ml capacity")

    assert localized.title != "Portable Blender"
    assert "USB rechargeable" not in "".join(localized.core_features)
    assert any("便携" in item or "充电" in item or "容量" in item for item in [localized.title, *localized.core_features])


def test_fallback_product_analysis_and_script_are_chinese():
    from app.services.ai import generate_product_analysis, generate_short_video_script

    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual"),
        core_features=["USB rechargeable", "500ml capacity"],
    )

    analysis_response = generate_product_analysis("abc", product, "Portable Blender USB rechargeable 500ml capacity", [])
    script_response = generate_short_video_script("abc", product, analysis_response.analysis, [])

    joined_analysis = "".join(analysis_response.analysis.selling_points + analysis_response.analysis.content_angles)
    assert "USB rechargeable" not in joined_analysis
    assert "Portable Blender" not in script_response.short_video_script.script
    assert any("便携" in item or "充电" in item or "容量" in item for item in analysis_response.analysis.selling_points)


def test_generate_short_video_script_tts_text_includes_hook_and_body():
    from app.services.ai import generate_short_video_script

    product = ProductInfo(title=FieldValue(value="便携榨汁杯", source="manual"))
    analysis = AnalysisResult(selling_points=["通勤携带", "USB 充电"])

    response = generate_short_video_script("abc", product, analysis, [], settings=Settings(deepseek_api_key=""))

    assert response.short_video_script.hook
    assert response.short_video_script.script
    assert not response.short_video_script.script.startswith(response.short_video_script.hook)
    assert response.tts_text == f"{response.short_video_script.hook}\n{response.short_video_script.script}"


def test_script_prompt_requires_clear_semantics_grammar_and_no_obvious_errors(monkeypatch):
    captured = {}

    def fake_deepseek_json(settings, system_prompt, payload):
        captured["system_prompt"] = system_prompt
        captured["payload"] = payload
        return {
            "short_video_script": {"hook": "先看这点", "script": "这款商品适合日常使用。", "word_count": 12},
            "tts_text": "先看这点\n这款商品适合日常使用。",
        }

    monkeypatch.setattr("app.services.ai._deepseek_json", fake_deepseek_json)
    product = ProductInfo(title=FieldValue(value="Portable Blender", source="manual"))
    analysis = AnalysisResult(selling_points=["USB rechargeable"])

    _generate_script_with_deepseek(product, analysis, Settings(deepseek_api_key="deepseek-key"))

    prompt_text = f"{captured['system_prompt']} {captured['payload']['task']}"
    assert "语句" in prompt_text
    assert "语义" in prompt_text
    assert "语法" in prompt_text
    assert "没有明显错误" in prompt_text


def test_stage_analysis_prompt_lists_content_logic_dimensions_separately():
    source = (PROJECT_ROOT / "app" / "services" / "ai.py").read_text(encoding="utf-8")

    assert "目标用户/购买动机/真实使用场景" not in source
    for dimension in ["目标用户", "购买动机", "真实使用场景", "用户痛点", "核心转化卖点", "差异化亮点", "内容切入角度", "购买决策提醒"]:
        assert f'"dimension": "{dimension}"' in source


def test_short_video_script_keeps_recommendation_tone_positive():
    from app.services.ai import generate_short_video_script

    product = ProductInfo(title=FieldValue(value="Eiliko AI Pendant", source="manual"))
    analysis = AnalysisResult(
        selling_points=["动态 LED 表情", "情绪陪伴"],
        use_scenarios=["日常穿搭", "送礼"],
    )

    response = generate_short_video_script("abc", product, analysis, [], settings=Settings(deepseek_api_key=""))
    copy = response.short_video_script.hook + response.short_video_script.script

    assert "不适合" not in copy
    assert "跳过" not in copy
    assert "别只看参数" not in copy


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


def test_generate_product_analysis_includes_evidence():
    from app.services.ai import generate_product_analysis

    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual"),
        core_features=["USB rechargeable"],
    )

    result = generate_product_analysis("abc", product, "USB rechargeable blender for travel", [])

    assert result.evidence
    assert any(item.claim and item.evidence for item in result.evidence)
    assert any("USB rechargeable" in item.evidence for item in result.evidence)


def test_product_analysis_includes_content_logic_rows():
    from app.services.ai import generate_product_analysis

    product = ProductInfo(
        title=FieldValue(value="Eiliko AI Pendant", source="manual"),
        category=FieldValue(value="AI companion pendant", source="manual"),
        core_features=["Dynamic LED screen with animated faces", "Gift-ready emotional AI companion"],
    )

    result = generate_product_analysis("abc", product, "AI companion pendant with LED expressions for gifts", [], settings=Settings(deepseek_api_key=""))

    expected_dimensions = ["目标用户", "购买动机", "真实使用场景", "用户痛点", "核心转化卖点", "差异化亮点", "内容切入角度", "购买决策提醒"]
    assert [row.dimension for row in result.analysis.content_logic] == expected_dimensions
    for row in result.analysis.content_logic:
        assert row.conclusion
        assert row.evidence
        assert row.content_angle


def test_analysis_evidence_uses_multiple_relevant_source_snippets():
    from app.services.ai import generate_product_analysis

    product = ProductInfo(
        title=FieldValue(value="Eiliko AI Pendant", source="manual"),
        category=FieldValue(value="AI companion pendant", source="manual"),
        core_features=[
            "Dynamic LED screen with animated faces",
            "Magnetic pendant clip for daily outfits",
            "Gift-ready emotional AI companion",
        ],
    )
    visible_text = "\n".join(
        [
            "YOUR EMOTIONAL AI COMPANION: Eiliko is more than a pendant, it's a charismatic AI friend.",
            "DYNAMIC LED EXPRESSIONS: animated faces respond to interactions with personality and charm.",
            "WEARABLE STYLE ACCESSORY: magnetic pendant clip works with bags, jackets, and daily outfits.",
            "PERFECT GIFT FOR FRIENDS AND COUPLES: a playful companion for birthdays and special moments.",
        ]
    )

    result = generate_product_analysis("abc", product, visible_text, [], settings=Settings(deepseek_api_key=""))
    evidence_texts = [item.evidence for item in result.evidence]

    assert len(set(evidence_texts)) >= 3
    assert any("LED" in text or "animated faces" in text for text in evidence_texts)
    assert any("outfits" in text or "STYLE ACCESSORY" in text for text in evidence_texts)
    assert any("gift" in text.lower() or "couples" in text.lower() for text in evidence_texts)


def test_ai_response_accepts_scalar_product_fields():
    evidence = ProductEvidence(product=ProductInfo(), visible_text="", warnings=[])
    result = _response_from_ai_data(
        {
            "product": {"title": "Portable Blender", "category": "Kitchen", "price": "unknown", "rating": 4.2, "review_count": 462},
            "analysis": {"target_users": ["旅行用户"]},
            "short_video_script": {"hook": "先看这一点", "script": "先看这一点，这款便携榨汁杯适合通勤和旅行。", "word_count": 24},
            "tts_text": "先看这一点，这款便携榨汁杯适合通勤和旅行。",
        },
        evidence,
    )

    assert result.product.title.value == "Portable Blender"
    assert result.product.category.value == "Kitchen"
    assert result.product.price.value == "unknown"
    assert result.product.rating.value == "4.2"
    assert result.product.review_count.value == "462"


def test_ai_response_accepts_text_analysis():
    evidence = ProductEvidence(product=ProductInfo(), visible_text="", warnings=[])
    result = _response_from_ai_data(
        {
            "product": {"title": "Aquamarine Necklace"},
            "analysis": "这款项链适合礼物场景，主打色彩清透和日常搭配，但需要说明尺寸较小。",
            "short_video_script": {"hook": "先看实物效果", "script": "先看实物效果，这款海蓝宝项链适合送礼和日常搭配。", "word_count": 28},
        },
        evidence,
    )

    assert result.analysis.content_angles == ["这款项链适合礼物场景，主打色彩清透和日常搭配，但需要说明尺寸较小。"]
