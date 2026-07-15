from __future__ import annotations

import re
from typing import Iterable

from app.models import AnalysisResult, LocalizedProductInfo, ProductInfo, QAResult

EXAGGERATED_PATTERNS = (
    "100%",
    "百分百",
    "全球第一",
    "全网最强",
    "最强",
    "最佳",
    "必买",
    "零风险",
    "保证",
    "永久",
)
SENSITIVE_UNSUPPORTED_PATTERNS = ("治愈", "治疗", "护眼", "保护视力", "减肥", "安全无害")


def qa_product_info(product: ProductInfo, localized_product: LocalizedProductInfo, visible_text: str = "", attempts: int = 1) -> QAResult:
    evidence_text = _evidence_text(
        [
            product.title.value,
            product.category.value,
            product.price.value,
            product.rating.value,
            product.review_count.value,
            *product.core_features,
            *product.specifications.keys(),
            *product.specifications.values(),
            visible_text,
        ]
    )
    claims = [localized_product.title, localized_product.category, localized_product.summary, *localized_product.core_features]
    claims.extend(localized_product.specifications.keys())
    claims.extend(localized_product.specifications.values())
    return _qa_result("product_info", claims, evidence_text, attempts)


def qa_analysis(analysis: AnalysisResult, product: ProductInfo, visible_text: str = "", attempts: int = 1) -> QAResult:
    evidence_text = _evidence_text(
        [
            product.title.value,
            product.category.value,
            product.price.value,
            product.rating.value,
            product.review_count.value,
            *product.core_features,
            *product.specifications.keys(),
            *product.specifications.values(),
            visible_text,
        ]
    )
    claims = [
        *analysis.target_users,
        *analysis.use_scenarios,
        *analysis.pain_points,
        *analysis.selling_points,
        *analysis.content_angles,
    ]
    return _qa_result("analysis", claims, evidence_text, attempts)


def _qa_result(stage: str, claims: Iterable[str], evidence_text: str, attempts: int) -> QAResult:
    unsupported_claims: list[str] = []
    exaggerated_claims: list[str] = []
    missing_evidence: list[str] = []
    non_chinese_claims: list[str] = []

    for claim in _clean_claims(claims):
        if _is_non_chinese_output(claim):
            non_chinese_claims.append(claim)
        if _has_exaggeration(claim):
            exaggerated_claims.append(claim)
        if _has_sensitive_unsupported_claim(claim):
            unsupported_claims.append(claim)
        if _needs_evidence_check(claim) and not _claim_has_evidence(claim, evidence_text):
            missing_evidence.append(claim)

    issues = []
    if non_chinese_claims:
        issues.append("生成内容不是中文")
    if unsupported_claims:
        issues.append("存在无依据的效果或敏感承诺")
    if exaggerated_claims:
        issues.append("存在夸大或绝对化描述")
    if missing_evidence:
        issues.append("部分内容缺少可追溯的产品证据")

    passed = not issues
    status = "passed" if passed else "manual_review" if attempts >= 3 else "retrying"
    guidance = "" if passed else "改写为中文，删除无证据和夸大描述，只保留商品原文或规格中能支持的事实。"
    return QAResult(
        stage=stage,
        status=status,
        passed=passed,
        attempts=attempts,
        issues=issues,
        unsupported_claims=unsupported_claims,
        exaggerated_claims=exaggerated_claims,
        missing_evidence=missing_evidence,
        non_chinese_claims=non_chinese_claims,
        rewrite_guidance=guidance,
    )


def _clean_claims(claims: Iterable[str]) -> list[str]:
    return [str(claim).strip() for claim in claims if str(claim).strip() and str(claim).strip().lower() != "unknown"]


def _has_exaggeration(claim: str) -> bool:
    return any(pattern in claim for pattern in EXAGGERATED_PATTERNS)


def _is_non_chinese_output(claim: str) -> bool:
    if re.fullmatch(r"[\d\s.,+\-:/]*(ml|l|oz|cm|mm|m|kg|g|w|v|mah|ah|hz|khz|gb|mb|tb|inch|in)?", claim, flags=re.IGNORECASE):
        return False
    chinese_chars = re.findall(r"[一-鿿]", claim)
    ascii_words = re.findall(r"[A-Za-z]{2,}", claim)
    if not ascii_words:
        return False
    return len(chinese_chars) < 2 or len(ascii_words) > len(chinese_chars)


def _has_sensitive_unsupported_claim(claim: str) -> bool:
    return any(pattern in claim for pattern in SENSITIVE_UNSUPPORTED_PATTERNS)


def _needs_evidence_check(claim: str) -> bool:
    return _has_exaggeration(claim) or _has_sensitive_unsupported_claim(claim)


def _claim_has_evidence(claim: str, evidence_text: str) -> bool:
    evidence = evidence_text.lower()
    tokens = _tokens(claim)
    if not tokens:
        return True
    return any(token.lower() in evidence for token in tokens)


def _tokens(text: str) -> list[str]:
    ascii_tokens = re.findall(r"[A-Za-z0-9]+", text)
    cjk_tokens = re.findall(r"[一-鿿]{2,}", text)
    return ascii_tokens + cjk_tokens


def _evidence_text(values: Iterable[str]) -> str:
    return " ".join(str(value) for value in values if value and str(value).lower() != "unknown")
