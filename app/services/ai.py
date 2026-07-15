from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.models import AnalysisResult, AnalyzeResponse, ContentLogicItem, EvidenceItem, FieldValue, GenerateAnalysisResponse, GenerateScriptResponse, LocalizedProductInfo, ProductInfo, ShortVideoScript
from app.services.scraper import ProductEvidence


def enforce_script_limit(text: str, limit: int = 150) -> str:
    cleaned = re.sub(r"\s+", "", text.strip())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip("，。；、") + "。"


def _speech_text_for_script(script: ShortVideoScript) -> str:
    parts = [script.hook.strip(), script.script.strip()]
    return "\n".join(part for part in parts if part)


def localize_product_info(product: ProductInfo, visible_text: str = "", settings: Settings | None = None) -> tuple[LocalizedProductInfo, list[str]]:
    settings = settings or Settings.from_env()
    if settings.has_deepseek:
        try:
            data = _deepseek_json(
                settings,
                "你是电商产品信息整理助手。只输出 JSON 对象，不要 Markdown。保留事实，不要编造价格、评分、规格。",
                {
                    "task": "把英文商品事实整理成中文展示信息。原始信息缺失时写 unknown。",
                    "schema": {
                        "title": "中文商品名称",
                        "category": "中文品类",
                        "price": "保留原价格或 unknown",
                        "rating": "评分文本或 unknown",
                        "review_count": "评论数文本或 unknown",
                        "core_features": ["中文核心功能"],
                        "specifications": {"中文规格名": "中文规格值"},
                        "summary": "一句话中文商品摘要",
                    },
                    "product": product.model_dump(),
                    "visible_text": visible_text[:3000],
                },
            )
            return LocalizedProductInfo.model_validate(_normalize_localized_product_data(data)), []
        except Exception as exc:  # noqa: BLE001
            localized = _fallback_localized_product(product)
            return localized, [f"DeepSeek 中文整理失败，已使用本地兜底整理：{exc}"]
    return _fallback_localized_product(product), ["未配置 DEEPSEEK_API_KEY，已使用本地兜底中文整理。"]


def generate_product_analysis(task_id: str, product: ProductInfo, visible_text: str = "", warnings: list[str] | None = None, settings: Settings | None = None) -> GenerateAnalysisResponse:
    settings = settings or Settings.from_env()
    warnings = list(warnings or [])
    if settings.has_deepseek:
        try:
            analysis = _generate_stage_analysis_with_deepseek(product, visible_text, settings)
            if not analysis.content_logic:
                analysis.content_logic = _content_logic_from_analysis(analysis, product, visible_text)
            return GenerateAnalysisResponse(task_id=task_id, product=product, analysis=analysis, visible_text=visible_text, evidence=_analysis_evidence(analysis, product, visible_text), warnings=warnings)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"DeepSeek 产品分析失败，已使用本地兜底分析：{exc}")
    else:
        warnings.append("未配置 DEEPSEEK_API_KEY，已使用本地兜底产品分析。")
    analysis = _fallback_analysis_for_product(product)
    analysis.content_logic = _content_logic_from_analysis(analysis, product, visible_text)
    return GenerateAnalysisResponse(task_id=task_id, product=product, analysis=analysis, visible_text=visible_text, evidence=_analysis_evidence(analysis, product, visible_text), warnings=warnings)


def generate_short_video_script(task_id: str, product: ProductInfo, analysis: AnalysisResult, warnings: list[str] | None = None, settings: Settings | None = None) -> GenerateScriptResponse:
    settings = settings or Settings.from_env()
    warnings = list(warnings or [])
    if settings.has_deepseek:
        try:
            script, image_prompt, _ = _generate_script_with_deepseek(product, analysis, settings)
            return GenerateScriptResponse(task_id=task_id, product=product, analysis=analysis, short_video_script=script, image_prompt=image_prompt, tts_text=_speech_text_for_script(script), warnings=warnings)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"DeepSeek 口播文案失败，已使用本地兜底文案：{exc}")
    else:
        warnings.append("未配置 DEEPSEEK_API_KEY，已使用本地兜底口播文案。")
    script = _fallback_script_for_product(product, analysis)
    return GenerateScriptResponse(task_id=task_id, product=product, analysis=analysis, short_video_script=script, image_prompt=_image_prompt_for_product(product), tts_text=_speech_text_for_script(script), warnings=warnings)


def generate_analysis(evidence: ProductEvidence, settings: Settings | None = None) -> AnalyzeResponse:
    settings = settings or Settings.from_env()
    if settings.has_deepseek:
        try:
            return _generate_with_deepseek(evidence, settings)
        except Exception as exc:  # noqa: BLE001
            fallback = build_fallback_analysis(evidence)
            fallback.warnings.append(f"DeepSeek 生成失败，已使用本地兜底分析：{exc}")
            return fallback

    fallback = build_fallback_analysis(evidence)
    fallback.warnings.append("未配置 DEEPSEEK_API_KEY，已使用本地兜底分析。")
    return fallback


def build_fallback_analysis(evidence: ProductEvidence) -> AnalyzeResponse:
    product = _complete_product_from_text(evidence.product, evidence.visible_text)
    name = product.title.value if product.title.value != "unknown" else "这款商品"
    features = product.core_features[:3] or ["核心信息来自商品页面或手动描述", "适合用短视频突出使用前后变化"]

    analysis = AnalysisResult(
        target_users=["关注实用性和性价比的消费者", "需要快速了解商品卖点的短视频观众"],
        use_scenarios=["日常使用前的购买决策", "内容种草和商品讲解", "同类商品对比筛选"],
        pain_points=["页面信息分散，难以快速判断是否适合自己", "卖点多但缺少短视频表达角度"],
        selling_points=features,
        content_angles=["用一个具体痛点开场", "展示核心功能带来的省时或省心变化", "用适用人群做收尾提醒"],
    )
    analysis.content_logic = _content_logic_from_analysis(analysis, product, evidence.visible_text)
    hook = f"别急着下单，先看{name}最值得关注的一点。"
    feature_text = "、".join(features[:2])
    script = enforce_script_limit(f"它的重点是{feature_text}，适合想少踩坑、快速判断值不值得买的人。用真实场景讲清痛点，再把核心卖点放大，转化会更自然。")
    image_prompt = f"Vertical product short video cover for {name}, clean ecommerce style, highlight practical selling points"
    return AnalyzeResponse(
        task_id=str(uuid.uuid4()),
        product=product,
        analysis=analysis,
        short_video_script=ShortVideoScript(hook=hook, script=script, word_count=len(script)),
        image_prompt=image_prompt,
        tts_text=script,
        warnings=list(evidence.warnings),
    )


def _analysis_evidence(analysis: AnalysisResult, product: ProductInfo, visible_text: str = "") -> list[EvidenceItem]:
    candidates = _evidence_candidates(product, visible_text)
    if not candidates:
        candidates = [("商品页面原文", "product")]
    claims = [
        *analysis.target_users,
        *analysis.use_scenarios,
        *analysis.pain_points,
        *analysis.selling_points,
        *analysis.content_angles,
    ]
    items: list[EvidenceItem] = []
    for index, claim in enumerate(claim for claim in claims if claim):
        evidence, source = _select_evidence_for_claim(str(claim), candidates, index)
        items.append(EvidenceItem(claim=str(claim), evidence=evidence, source=source))
    return items


def _evidence_candidates(product: ProductInfo, visible_text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for value in [product.title.value, product.category.value, *product.core_features]:
        text = str(value or "").strip()
        if text and text.lower() != "unknown":
            candidates.append((text, "product"))
    for key, value in product.specifications.items():
        text = f"{key}: {value}".strip()
        if text and text.lower() != "unknown":
            candidates.append((text, "product"))
    for line in _visible_text_snippets(visible_text):
        candidates.append((line, "visible_text"))
    return _dedupe_evidence_candidates(candidates)


def _visible_text_snippets(visible_text: str) -> list[str]:
    snippets: list[str] = []
    for line in re.split(r"[\n。！？!?]+", visible_text):
        text = re.sub(r"\s+", " ", line).strip()
        if len(text) >= 12:
            snippets.append(text[:220])
    return snippets


def _dedupe_evidence_candidates(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    deduped: list[tuple[str, str]] = []
    for text, source in candidates:
        key = text.lower()
        if key not in seen:
            seen.add(key)
            deduped.append((text, source))
    return deduped


def _select_evidence_for_claim(claim: str, candidates: list[tuple[str, str]], index: int) -> tuple[str, str]:
    claim_tokens = _evidence_tokens(claim)
    scored: list[tuple[int, int, str, str]] = []
    for candidate_index, (text, source) in enumerate(candidates):
        score = len(claim_tokens & _evidence_tokens(text))
        scored.append((score, -candidate_index, text, source))
    best_score, _, best_text, best_source = max(scored, key=lambda item: (item[0], item[1]))
    if best_score > 0:
        return best_text, best_source
    return candidates[index % len(candidates)]


def _evidence_tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]+|[一-鿿]{2,}", text)}


def _content_logic_from_analysis(analysis: AnalysisResult, product: ProductInfo, visible_text: str = "") -> list[ContentLogicItem]:
    groups = [
        ("目标用户", analysis.target_users[:2]),
        ("购买动机", analysis.selling_points[:2]),
        ("真实使用场景", analysis.use_scenarios[:2]),
        ("用户痛点", analysis.pain_points[:2]),
        ("核心转化卖点", analysis.selling_points[:2]),
        ("差异化亮点", analysis.selling_points[:1] + analysis.content_angles[:1]),
        ("内容切入角度", analysis.content_angles[:2]),
    ]
    rows: list[ContentLogicItem] = []
    candidates = _evidence_candidates(product, visible_text)
    for dimension, conclusions in groups:
        conclusion = "、".join(str(item) for item in conclusions if str(item).strip())
        if not conclusion:
            continue
        evidence, _ = _select_evidence_for_claim(conclusion, candidates or [("商品页面原文", "product")], len(rows))
        rows.append(ContentLogicItem(dimension=dimension, conclusion=conclusion, evidence=evidence, content_angle=_content_angle_for_dimension(dimension, conclusion)))
    rows.append(ContentLogicItem(dimension="购买决策提醒", conclusion="适合关注真实使用场景、功能体验和核心卖点匹配度的人", evidence=_first_non_unknown([product.category.value, product.title.value, visible_text[:160]]), content_angle="收尾用适合人群和推荐理由做真实提醒，避免硬广感。"))
    return rows


def _content_angle_for_dimension(dimension: str, conclusion: str) -> str:
    if dimension == "目标人群":
        return f"开场直接点名{conclusion}，让观众判断是不是自己。"
    if dimension == "购买动机":
        return f"把购买理由讲成一个具体变化：{conclusion}。"
    if dimension == "真实使用场景":
        return f"用真实场景带出产品，而不是直接念参数：{conclusion}。"
    if dimension == "用户顾虑":
        return f"先承认顾虑再解释卖点，降低硬广感：{conclusion}。"
    if dimension == "核心转化卖点":
        return f"把卖点翻译成观众能感知的好处：{conclusion}。"
    return conclusion


def _first_non_unknown(values: list[str]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() != "unknown":
            return text
    return "商品页面原文"


def _generate_stage_analysis_with_deepseek(product: ProductInfo, visible_text: str, settings: Settings) -> AnalysisResult:
    data = _deepseek_json(
        settings,
        "你是电商产品分析师。只输出 JSON 对象，不要 Markdown。",
        {
            "task": "基于商品信息做产品分析，只返回 analysis 对象。",
            "schema": {
                "target_users": ["目标用户"],
                "use_scenarios": ["使用场景"],
                "pain_points": ["用户痛点"],
                "selling_points": ["核心卖点"],
                "content_angles": ["短视频内容角度"],
                "content_logic": [
                    {"dimension": "目标用户", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "购买动机", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "真实使用场景", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "用户痛点", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "核心转化卖点", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "差异化亮点", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "内容切入角度", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                    {"dimension": "购买决策提醒", "conclusion": "分析结论", "evidence": "商品依据", "content_angle": "口播文案内容启发"},
                ],
            },
            "product": product.model_dump(),
            "visible_text": visible_text[:4000],
        },
    )
    return AnalysisResult.model_validate(_normalize_analysis_data(data.get("analysis", data)))


def _generate_script_with_deepseek(product: ProductInfo, analysis: AnalysisResult, settings: Settings) -> tuple[ShortVideoScript, str, str]:
    data = _deepseek_json(
        settings,
        "你是中文带货短视频编导。只输出 JSON 对象，不要 Markdown。",
        {
            "task": "基于商品信息和产品分析生成短视频口播文案。不要写成商品说明书，要像短视频博主真实口播。脚本必须150字以内，前5秒有吸引继续观看的钩子，必须体现谁会喜欢、关键卖点和具体使用场景，避免空泛词，不要出现不适合、跳过、劝退等负向推荐表达。语句、语义、语法必须清晰，没有明显错误。",
            "schema": {"hook": "反差/问题/场景式开头钩子", "script": "150字以内中文口播：谁会喜欢 + 关键卖点 + 使用场景 + 推荐理由", "image_prompt": "竖屏封面提示词", "tts_text": "TTS文本"},
            "product": product.model_dump(),
            "analysis": analysis.model_dump(),
        },
    )
    script_text = enforce_script_limit(str(data.get("script") or data.get("short_video_script", {}).get("script") or ""))
    hook = str(data.get("hook") or data.get("short_video_script", {}).get("hook") or script_text[:30])
    if not script_text:
        raise ValueError("AI 未返回口播文案")
    script = ShortVideoScript(hook=hook, script=script_text, word_count=len(script_text))
    image_prompt = str(data.get("image_prompt") or _image_prompt_for_product(product))
    tts_text = _speech_text_for_script(script)
    return script, image_prompt, tts_text


def _deepseek_json(settings: Settings, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
        json={
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.3,
            "max_tokens": 5000,
            "response_format": {"type": "json_object"},
        },
        timeout=45.0,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return _extract_json_object(content)


def _generate_with_deepseek(evidence: ProductEvidence, settings: Settings) -> AnalyzeResponse:
    payload = _prompt_payload(evidence)
    response = httpx.post(
        f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
        json={
            "model": settings.deepseek_model,
            "messages": [
                {"role": "system", "content": "你是电商短视频产品分析助手。只输出严格 JSON，不要 Markdown。事实字段不能编造，未知写 unknown。"},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.4,
            "max_tokens": 5000,
            "response_format": {"type": "json_object"},
        },
        timeout=45.0,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        data = _extract_json_object(content)
    result = _response_from_ai_data(data, evidence)
    result.short_video_script.script = enforce_script_limit(result.short_video_script.script)
    result.short_video_script.word_count = len(result.short_video_script.script)
    if result.short_video_script.word_count > 150:
        raise ValueError("AI 文案超过 150 字")
    return result


def _prompt_payload(evidence: ProductEvidence) -> dict[str, Any]:
    return {
        "task": "基于商品证据生成产品信息整理、产品分析、150字以内中文短视频口播文案、TTS文本和图片提示词。",
        "required_json_keys": ["product", "analysis", "short_video_script", "image_prompt", "tts_text", "warnings"],
        "product_evidence": evidence.product.model_dump(),
        "visible_text": evidence.visible_text[:5000],
        "warnings": evidence.warnings,
    }


def _response_from_ai_data(data: dict[str, Any], evidence: ProductEvidence) -> AnalyzeResponse:
    try:
        product_data = _normalize_product_data(data.get("product") or evidence.product.model_dump())
        product = ProductInfo.model_validate(product_data)
        analysis = AnalysisResult.model_validate(_normalize_analysis_data(data.get("analysis")))
        script = ShortVideoScript.model_validate(data.get("short_video_script") or {})
        warnings = list(evidence.warnings) + [str(item) for item in data.get("warnings", [])]
        return AnalyzeResponse(
            task_id=str(uuid.uuid4()),
            product=product,
            analysis=analysis,
            short_video_script=script,
            image_prompt=str(data.get("image_prompt", "")),
            tts_text=_speech_text_for_script(script),
            warnings=warnings,
        )
    except ValidationError as exc:
        raise ValueError(f"AI JSON 结构不符合接口：{exc}") from exc


def _extract_json_object(content: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise ValueError("AI 未返回 JSON 对象")
    raw_json = match.group(0)
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return json.loads(_escape_control_characters_in_json_strings(raw_json))


def _escape_control_characters_in_json_strings(value: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    for char in value:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\":
            result.append(char)
            escaped = True
            continue
        if char == '"':
            result.append(char)
            in_string = not in_string
            continue
        if in_string and char in {"\n", "\r", "\t"}:
            result.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[char])
            continue
        result.append(char)
    return "".join(result)


def _normalize_localized_product_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    normalized = dict(data)
    for key in ("title", "category", "price", "rating", "review_count", "summary"):
        value = normalized.get(key)
        if value is not None:
            normalized[key] = str(value) if str(value).strip() else "unknown"
    features = normalized.get("core_features")
    if isinstance(features, str):
        normalized["core_features"] = [features]
    elif isinstance(features, list):
        normalized["core_features"] = [str(item) for item in features if str(item).strip()]
    else:
        normalized["core_features"] = []
    specs = normalized.get("specifications")
    if isinstance(specs, dict):
        normalized["specifications"] = {str(key): str(value) for key, value in specs.items() if str(key).strip() and str(value).strip()}
    else:
        normalized["specifications"] = {}
    return normalized


def _fallback_localized_product(product: ProductInfo) -> LocalizedProductInfo:
    title = product.title.value
    features = product.core_features[:6]
    specs = dict(list(product.specifications.items())[:12])
    summary_name = title if title != "unknown" else "该商品"
    return LocalizedProductInfo(
        title=title,
        category=product.category.value,
        price=product.price.value,
        rating=product.rating.value,
        review_count=product.review_count.value,
        core_features=features,
        specifications=specs,
        summary=f"{summary_name} 的信息已按原始页面提取，建议结合核心功能和规格继续分析。",
    )


def _fallback_analysis_for_product(product: ProductInfo) -> AnalysisResult:
    features = product.core_features[:3] or ["商品信息需要结合页面和手动描述判断"]
    name = product.title.value if product.title.value != "unknown" else "这款商品"
    return AnalysisResult(
        target_users=["正在比较同类商品的消费者", "希望快速判断是否值得购买的短视频观众"],
        use_scenarios=["购买前快速了解商品", "短视频带货讲解", "同类商品对比筛选"],
        pain_points=["商品页面信息分散", "用户难以快速判断真实卖点", "担心参数和实际体验不一致"],
        selling_points=features,
        content_angles=[f"围绕{name}的核心使用场景开场", "先讲用户痛点，再展示关键卖点", "用适合/不适合人群增强真实感"],
    )


def _fallback_script_for_product(product: ProductInfo, analysis: AnalysisResult) -> ShortVideoScript:
    name = product.title.value if product.title.value != "unknown" else "这款商品"
    selling_points = analysis.selling_points[:2] or product.core_features[:2] or ["核心功能", "实际使用场景"]
    hook = f"别急着下单，先看{name}值不值得买。"
    content_angle = analysis.content_logic[0].content_angle if analysis.content_logic else "先讲适合谁，再讲真实使用场景。"
    script = enforce_script_limit(f"如果你关注{selling_points[0]}，可以先看它放进真实场景里的效果。它的关键点是{'、'.join(selling_points)}。{content_angle}适合想快速判断亮点和使用感的人参考。")
    return ShortVideoScript(hook=hook, script=script, word_count=len(script))


def _image_prompt_for_product(product: ProductInfo) -> str:
    name = product.title.value if product.title.value != "unknown" else "Amazon product"
    return f"Vertical ecommerce short video cover for {name}, clean product layout, highlight practical selling points"


def _normalize_product_data(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    normalized = dict(data)
    for key in ("title", "category", "price", "rating", "review_count"):
        value = normalized.get(key)
        if value is not None and not isinstance(value, dict):
            text = str(value) if value != "" else "unknown"
            normalized[key] = {"value": text, "source": "ai"}
    return normalized


def _normalize_analysis_data(data: Any) -> dict[str, list[str]]:
    if isinstance(data, str):
        return {"content_angles": [data]} if data.strip() else {}
    if isinstance(data, list):
        return {"content_angles": [str(item) for item in data if str(item).strip()]}
    if not isinstance(data, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for key in ("target_users", "use_scenarios", "pain_points", "selling_points", "content_angles"):
        value = data.get(key)
        if isinstance(value, list):
            normalized[key] = [str(item) for item in value if str(item).strip()]
        elif value is not None and str(value).strip():
            normalized[key] = [str(value)]
    logic = data.get("content_logic")
    if isinstance(logic, list):
        normalized["content_logic"] = [item for item in logic if isinstance(item, dict)]
    if not normalized and data:
        normalized["content_angles"] = [str(value) for value in data.values() if str(value).strip()]
    return normalized


def _complete_product_from_text(product: ProductInfo, text: str) -> ProductInfo:
    if product.title.value != "unknown" or not text.strip():
        return product
    title = re.split(r"[。！？.!?\n]", text.strip(), maxsplit=1)[0][:80]
    return product.model_copy(update={"title": FieldValue(value=title or "unknown", source="manual")})
