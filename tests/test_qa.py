from app.models import AnalysisResult, FieldValue, LocalizedProductInfo, ProductInfo
from app.services.qa import qa_analysis, qa_product_info


def test_product_info_qa_rejects_unsupported_or_exaggerated_localized_claims():
    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual"),
        core_features=["USB rechargeable"],
    )
    localized = LocalizedProductInfo(
        title="便携榨汁杯",
        core_features=["USB 充电", "100% 治愈失眠", "全网最强性能"],
    )

    result = qa_product_info(product, localized, "Portable Blender USB rechargeable", attempts=3)

    assert result.status == "manual_review"
    assert result.passed is False
    assert result.attempts == 3
    assert "100% 治愈失眠" in result.unsupported_claims
    assert "全网最强性能" in result.exaggerated_claims
    assert result.rewrite_guidance


def test_product_info_qa_passes_grounded_localized_claims():
    product = ProductInfo(
        title=FieldValue(value="Portable Blender", source="manual"),
        core_features=["USB rechargeable", "500ml capacity"],
    )
    localized = LocalizedProductInfo(
        title="便携榨汁杯",
        core_features=["USB 充电", "500ml 容量"],
    )

    result = qa_product_info(product, localized, "Portable Blender USB rechargeable 500ml capacity", attempts=1)

    assert result.status == "passed"
    assert result.passed is True
    assert result.issues == []


def test_analysis_qa_rejects_exaggerated_claims_without_evidence():
    product = ProductInfo(
        title=FieldValue(value="Desk Lamp", source="manual"),
        core_features=["Adjustable brightness"],
    )
    analysis = AnalysisResult(
        selling_points=["全球第一护眼效果，100% 保护视力"],
        content_angles=["强调可调亮度适合夜间阅读"],
    )

    result = qa_analysis(analysis, product, "Desk Lamp Adjustable brightness", attempts=2)

    assert result.status == "retrying"
    assert result.passed is False
    assert result.attempts == 2
    assert result.exaggerated_claims
    assert result.missing_evidence


def test_analysis_qa_passes_grounded_claims():
    product = ProductInfo(
        title=FieldValue(value="Desk Lamp", source="manual"),
        core_features=["Adjustable brightness"],
    )
    analysis = AnalysisResult(
        selling_points=["可调亮度方便夜间阅读"],
        content_angles=["围绕夜间阅读场景展示亮度调节"],
    )

    result = qa_analysis(analysis, product, "Desk Lamp Adjustable brightness night reading", attempts=1)

    assert result.status == "passed"
    assert result.passed is True


def test_product_info_qa_rejects_non_chinese_localized_output():
    product = ProductInfo(title=FieldValue(value="Portable Blender", source="manual"), core_features=["USB rechargeable"])
    localized = LocalizedProductInfo(title="Portable Blender", core_features=["USB rechargeable", "500ml capacity"])

    result = qa_product_info(product, localized, "Portable Blender USB rechargeable 500ml capacity", attempts=2)

    assert result.passed is False
    assert result.status == "retrying"
    assert "生成内容不是中文" in result.issues
    assert "Portable Blender" in result.non_chinese_claims


def test_analysis_qa_rejects_non_chinese_analysis_output():
    product = ProductInfo(title=FieldValue(value="Portable Blender", source="manual"), core_features=["USB rechargeable"])
    analysis = AnalysisResult(selling_points=["USB rechargeable for travel"], content_angles=["Show travel scenario"])

    result = qa_analysis(analysis, product, "Portable Blender USB rechargeable for travel", attempts=3)

    assert result.passed is False
    assert result.status == "manual_review"
    assert "生成内容不是中文" in result.issues
    assert "USB rechargeable for travel" in result.non_chinese_claims
