from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

Source = Literal["dom", "metadata", "ai", "manual", "unknown"]
InputMethod = Literal["firecrawl", "local", "manual"]
QAStage = Literal["product_info", "analysis"]
QAStatus = Literal["passed", "retrying", "manual_review"]
EvidenceSource = Literal["product", "localized_product", "visible_text", "manual", "qa"]


class FieldValue(BaseModel):
    value: str = "unknown"
    source: Source = "unknown"


class ProductInfo(BaseModel):
    title: FieldValue = Field(default_factory=FieldValue)
    category: FieldValue = Field(default_factory=FieldValue)
    price: FieldValue = Field(default_factory=FieldValue)
    rating: FieldValue = Field(default_factory=FieldValue)
    review_count: FieldValue = Field(default_factory=FieldValue)
    main_image_url: str = ""
    image_candidates: list[str] = Field(default_factory=list)
    core_features: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)


class QAResult(BaseModel):
    stage: QAStage
    status: QAStatus = "passed"
    passed: bool = True
    attempts: int = 1
    issues: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    exaggerated_claims: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    non_chinese_claims: list[str] = Field(default_factory=list)
    rewrite_guidance: str = ""


class EvidenceItem(BaseModel):
    claim: str
    evidence: str
    source: EvidenceSource = "product"


class LocalizedProductInfo(BaseModel):
    title: str = "unknown"
    category: str = "unknown"
    price: str = "unknown"
    rating: str = "unknown"
    review_count: str = "unknown"
    core_features: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    summary: str = ""


class ContentLogicItem(BaseModel):
    dimension: str = ""
    conclusion: str = ""
    evidence: str = ""
    content_angle: str = ""


class AnalysisResult(BaseModel):
    target_users: list[str] = Field(default_factory=list)
    use_scenarios: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    selling_points: list[str] = Field(default_factory=list)
    content_angles: list[str] = Field(default_factory=list)
    content_logic: list[ContentLogicItem] = Field(default_factory=list)


class ShortVideoScript(BaseModel):
    hook: str = ""
    script: str = ""
    word_count: int = 0


class ExtractProductRequest(BaseModel):
    url: HttpUrl | None = None
    manual_text: str | None = None
    input_method: InputMethod = "firecrawl"

    @model_validator(mode="after")
    def validate_selected_input(self) -> "ExtractProductRequest":
        if self.input_method in {"firecrawl", "local"} and self.url is None:
            raise ValueError("选择抓取方式时必须提供 Amazon 商品链接。")
        if self.input_method == "manual" and not (self.manual_text and self.manual_text.strip()):
            raise ValueError("选择手动复制粘贴时必须提供商品描述。")
        return self


class ExtractProductResponse(BaseModel):
    task_id: str
    source_url: str
    product: ProductInfo = Field(default_factory=ProductInfo)
    localized_product: LocalizedProductInfo = Field(default_factory=LocalizedProductInfo)
    visible_text: str = ""
    extraction_method: str = "local"
    warnings: list[str] = Field(default_factory=list)


class GenerateAnalysisRequest(BaseModel):
    task_id: str
    product: ProductInfo = Field(default_factory=ProductInfo)
    localized_product: LocalizedProductInfo = Field(default_factory=LocalizedProductInfo)
    visible_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class GenerateAnalysisResponse(BaseModel):
    task_id: str
    product: ProductInfo = Field(default_factory=ProductInfo)
    localized_product: LocalizedProductInfo = Field(default_factory=LocalizedProductInfo)
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    visible_text: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    product_qa: QAResult | None = None
    warnings: list[str] = Field(default_factory=list)


class GenerateScriptRequest(BaseModel):
    task_id: str
    product: ProductInfo = Field(default_factory=ProductInfo)
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    visible_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class UpdateScriptRequest(BaseModel):
    hook: str = ""
    script: str = ""


class GenerateScriptResponse(BaseModel):
    task_id: str
    product: ProductInfo = Field(default_factory=ProductInfo)
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    analysis_qa: QAResult | None = None
    short_video_script: ShortVideoScript = Field(default_factory=ShortVideoScript)
    tts_text: str = ""
    warnings: list[str] = Field(default_factory=list)


class AnalyzeRequest(ExtractProductRequest):
    pass


class AnalyzeResponse(BaseModel):
    task_id: str
    product: ProductInfo = Field(default_factory=ProductInfo)
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    short_video_script: ShortVideoScript = Field(default_factory=ShortVideoScript)
    tts_text: str = ""
    warnings: list[str] = Field(default_factory=list)



class VoiceProfile(BaseModel):
    id: str
    voice_id: str
    name: str = "custom_voice"
    prompt: str = ""
    model: str = "qwen3-tts-vd-2026-01-26"
    created_at: str = ""


class CreateVoiceRequest(BaseModel):
    name: str = "custom_voice"
    prompt: str = ""
    sample_rate: int = 24000
    audio_format: str = "wav"


class CreateVoiceResponse(BaseModel):
    profile: VoiceProfile | None = None
    warnings: list[str] = Field(default_factory=list)


class DeleteVoiceResponse(BaseModel):
    deleted: bool = False
    voice_id: str = ""
    warnings: list[str] = Field(default_factory=list)


class GenerateVoiceRequest(BaseModel):
    task_id: str
    text: str = ""
    voice: str = "longanlingxi"
    voice_id: str = ""
    voice_instruction: str = ""
    audio_format: str = "wav"
    sample_rate: int = 24000


class GenerateVoiceResponse(BaseModel):
    audio_url: str = ""
    remote_audio_url: str = ""
    expires_in_hours: int = 24
    warnings: list[str] = Field(default_factory=list)
