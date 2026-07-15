from __future__ import annotations

import uuid
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.models import ExtractProductRequest, ExtractProductResponse, GenerateAnalysisRequest, GenerateAnalysisResponse, GenerateScriptRequest, GenerateScriptResponse, GenerateVoiceRequest, GenerateVoiceResponse, LocalizedProductInfo, QAResult
from app.services.ai import generate_product_analysis, generate_short_video_script, localize_product_info
from app.services.qa import qa_analysis, qa_product_info
from app.services.scraper import fetch_product_evidence
from app.services.storage import save_analysis_qa_result, save_product_qa_result, save_product_result, save_script_result, save_stage_analysis_result, update_voice_result
from app.services.voice import generate_voice_audio

# Importers/callers: app.main staged API routes call run_extract_product, run_analyze_product, run_generate_script, and run_generate_voice.
# Affected API: route names and Pydantic response contracts stay the same; implementation delegates each stage to a LangGraph node.
# Data schemas: uses existing ExtractProduct/GenerateAnalysis/GenerateScript/GenerateVoice schemas; no persisted record shape changes.
# User instruction: "可以的进行优化吧"


class ProductWorkflowState(TypedDict, total=False):
    extract_request: ExtractProductRequest
    analysis_request: GenerateAnalysisRequest
    script_request: GenerateScriptRequest
    voice_request: GenerateVoiceRequest
    product_response: ExtractProductResponse
    product_qa_response: QAResult
    analysis_response: GenerateAnalysisResponse
    analysis_qa_response: QAResult
    script_response: GenerateScriptResponse
    voice_response: GenerateVoiceResponse


def run_extract_product(request: ExtractProductRequest) -> ExtractProductResponse:
    result = _extract_graph().invoke({"extract_request": request})
    return result["product_response"]


def run_analyze_product(request: GenerateAnalysisRequest) -> GenerateAnalysisResponse:
    result = _analysis_graph().invoke({"analysis_request": request})
    return result["analysis_response"]


def run_generate_script(request: GenerateScriptRequest) -> GenerateScriptResponse:
    result = _script_graph().invoke({"script_request": request})
    return result["script_response"]



def run_generate_voice(request: GenerateVoiceRequest) -> GenerateVoiceResponse:
    result = _voice_graph().invoke({"voice_request": request})
    return result["voice_response"]


def _extract_node(state: ProductWorkflowState) -> ProductWorkflowState:
    request = state["extract_request"]
    source_url = str(request.url) if request.url else "manual://input"
    evidence = fetch_product_evidence(source_url if request.url else None, request.manual_text, input_method=request.input_method)
    localized_product, localized_warnings = localize_product_info(evidence.product, evidence.visible_text)
    response = ExtractProductResponse(task_id=str(uuid.uuid4()), source_url=source_url, product=evidence.product, localized_product=localized_product, visible_text=evidence.visible_text, extraction_method=evidence.extraction_method, warnings=evidence.warnings + localized_warnings)
    save_product_result(response)
    return {"product_response": response}


def _analysis_node(state: ProductWorkflowState) -> ProductWorkflowState:
    request = state["analysis_request"]
    product_qa, localized_product = _run_product_qa(request)
    save_product_qa_result(request.task_id, product_qa)
    response = generate_product_analysis(request.task_id, request.product, request.visible_text, request.warnings)
    response.localized_product = localized_product
    response.product_qa = product_qa
    save_stage_analysis_result(response)
    return {"analysis_response": response, "product_qa_response": product_qa}


def _script_node(state: ProductWorkflowState) -> ProductWorkflowState:
    request = state["script_request"]
    analysis_qa, analysis = _run_analysis_qa(request)
    save_analysis_qa_result(request.task_id, analysis_qa)
    response = generate_short_video_script(request.task_id, request.product, analysis, request.warnings)
    response.analysis_qa = analysis_qa
    save_script_result(response)
    return {"script_response": response, "analysis_qa_response": analysis_qa}



def _voice_node(state: ProductWorkflowState) -> ProductWorkflowState:
    request = state["voice_request"]
    try:
        response = generate_voice_audio(request)
    except Exception as exc:  # noqa: BLE001
        response = GenerateVoiceResponse(warnings=[f"口播语音生成失败：{exc}"])
    update_voice_result(request.task_id, response)
    return {"voice_response": response}


def _run_product_qa(request: GenerateAnalysisRequest) -> tuple[QAResult, LocalizedProductInfo]:
    localized = request.localized_product.model_copy(deep=True)
    result = qa_product_info(request.product, localized, request.visible_text, attempts=1)
    for attempt in range(2, 4):
        if result.passed:
            return result, localized
        rejected = result.exaggerated_claims + result.unsupported_claims + result.non_chinese_claims
        localized.title = "unknown" if localized.title in rejected else localized.title
        localized.category = "unknown" if localized.category in rejected else localized.category
        localized.core_features = _remove_claims(localized.core_features, rejected)
        localized.summary = "" if localized.summary in rejected else localized.summary
        localized.specifications = _clean_specs(localized.specifications, rejected)
        result = qa_product_info(request.product, localized, request.visible_text, attempts=attempt)
    return result, localized


def _run_analysis_qa(request: GenerateScriptRequest) -> tuple[QAResult, object]:
    analysis = request.analysis.model_copy(deep=True)
    result = qa_analysis(analysis, request.product, request.visible_text, attempts=1)
    for attempt in range(2, 4):
        if result.passed:
            return result, analysis
        rejected = result.exaggerated_claims + result.unsupported_claims + result.non_chinese_claims
        analysis.target_users = _remove_claims(analysis.target_users, rejected)
        analysis.use_scenarios = _remove_claims(analysis.use_scenarios, rejected)
        analysis.pain_points = _remove_claims(analysis.pain_points, rejected)
        analysis.selling_points = _remove_claims(analysis.selling_points, rejected)
        analysis.content_angles = _remove_claims(analysis.content_angles, rejected)
        result = qa_analysis(analysis, request.product, request.visible_text, attempts=attempt)
    return result, analysis


def _remove_claims(items: list[str], rejected: list[str]) -> list[str]:
    rejected_set = set(rejected)
    return [item for item in items if item not in rejected_set]


def _clean_specs(specs: dict[str, str], rejected: list[str]) -> dict[str, str]:
    rejected_set = set(rejected)
    return {key: value for key, value in specs.items() if key not in rejected_set and value not in rejected_set}


def _extract_graph():
    graph = StateGraph(ProductWorkflowState)
    graph.add_node("extract_product", _extract_node)
    graph.set_entry_point("extract_product")
    graph.add_edge("extract_product", END)
    return graph.compile()


def _analysis_graph():
    graph = StateGraph(ProductWorkflowState)
    graph.add_node("analyze_product", _analysis_node)
    graph.set_entry_point("analyze_product")
    graph.add_edge("analyze_product", END)
    return graph.compile()


def _script_graph():
    graph = StateGraph(ProductWorkflowState)
    graph.add_node("generate_script", _script_node)
    graph.set_entry_point("generate_script")
    graph.add_edge("generate_script", END)
    return graph.compile()



def _voice_graph():
    graph = StateGraph(ProductWorkflowState)
    graph.add_node("generate_voice", _voice_node)
    graph.set_entry_point("generate_voice")
    graph.add_edge("generate_voice", END)
    return graph.compile()
