from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.models import AnalyzeResponse, ExtractProductResponse, GenerateAnalysisResponse, GenerateScriptResponse, GenerateVideoResponse, GenerateVoiceResponse, QAResult

# Importers/callers: app.main will call save_analysis_result, update_video_result, and load_result_record from API routes.
# Affected API: POST /api/analyze and POST /api/generate-video gain persistence side effects; GET /api/results/{task_id} will read saved records.
# Data schemas: no existing Pydantic request/response schema is changed; saved JSON records include task_id, source_url, timestamps, analysis_response, and video_response.
# User instruction: "一个链接生成的产物要能够保存，能明白吗"
TASK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def save_product_result(response: ExtractProductResponse, settings: Settings | None = None) -> dict[str, Any]:
    return _update_record(
        response.task_id,
        settings,
        source_url=response.source_url,
        product_response=response.model_dump(mode="json"),
    )


def save_product_qa_result(task_id: str, response: QAResult, settings: Settings | None = None) -> dict[str, Any]:
    return _update_record(task_id, settings, product_qa_response=response.model_dump(mode="json"))


def save_stage_analysis_result(response: GenerateAnalysisResponse, settings: Settings | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {"stage_analysis_response": response.model_dump(mode="json")}
    if response.product_qa:
        updates["product_qa_response"] = response.product_qa.model_dump(mode="json")
    return _update_record(response.task_id, settings, **updates)


def save_analysis_qa_result(task_id: str, response: QAResult, settings: Settings | None = None) -> dict[str, Any]:
    return _update_record(task_id, settings, analysis_qa_response=response.model_dump(mode="json"))


def save_script_result(response: GenerateScriptResponse, settings: Settings | None = None) -> dict[str, Any]:
    updates: dict[str, Any] = {"script_response": response.model_dump(mode="json")}
    if response.analysis_qa:
        updates["analysis_qa_response"] = response.analysis_qa.model_dump(mode="json")
    return _update_record(response.task_id, settings, **updates)


def update_voice_result(task_id: str, response: GenerateVoiceResponse, settings: Settings | None = None) -> dict[str, Any]:
    return _update_record(task_id, settings, voice_response=response.model_dump(mode="json"))


def save_analysis_result(url: str, response: AnalyzeResponse, settings: Settings | None = None) -> dict[str, Any]:
    return _update_record(
        response.task_id,
        settings,
        source_url=url,
        analysis_response=response.model_dump(mode="json"),
    )


def update_video_result(task_id: str, response: GenerateVideoResponse, settings: Settings | None = None) -> dict[str, Any]:
    return _update_record(task_id, settings, video_response=response.model_dump(mode="json"))


def load_result_record(task_id: str, output_dir: Path | None = None) -> dict[str, Any] | None:
    output_dir = output_dir or Settings.from_env().output_dir
    path = _record_path(task_id, output_dir)
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def list_result_records(output_dir: Path | None = None) -> list[dict[str, Any]]:
    output_dir = output_dir or Settings.from_env().output_dir
    records_dir = output_dir / "records"
    if not records_dir.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in records_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as file:
                record = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        records.append(_record_summary(record))
    return sorted(records, key=lambda item: item.get("updated_at", ""), reverse=True)


def delete_result_record(task_id: str, output_dir: Path | None = None) -> bool:
    output_dir = output_dir or Settings.from_env().output_dir
    safe_task_id = _safe_task_id(task_id)
    path = _record_path(safe_task_id, output_dir)
    existed = path.exists()
    if existed:
        path.unlink()
    for suffix in (".png", ".mp3", ".mp4", ".wav", ".aac", ".opus"):
        media_path = output_dir / f"{safe_task_id}{suffix}"
        if media_path.exists():
            media_path.unlink()
    return existed


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    product_response = record.get("product_response") or {}
    product = product_response.get("localized_product") or product_response.get("product") or {}
    title = product.get("title") if isinstance(product, dict) else ""
    if isinstance(title, dict):
        title = title.get("value", "")
    legacy = record.get("analysis_response") or {}
    legacy_product = legacy.get("product") or {}
    if not title and isinstance(legacy_product, dict):
        legacy_title = legacy_product.get("title") or {}
        title = legacy_title.get("value", "") if isinstance(legacy_title, dict) else str(legacy_title)
    video_response = record.get("video_response") or {}
    voice_response = record.get("voice_response") or {}
    product_qa = record.get("product_qa_response") or {}
    analysis_qa = record.get("analysis_qa_response") or {}
    return {
        "task_id": record.get("task_id", ""),
        "source_url": record.get("source_url", ""),
        "title": title or "unknown",
        "created_at": record.get("created_at", ""),
        "updated_at": record.get("updated_at", ""),
        "has_product": bool(record.get("product_response") or record.get("analysis_response")),
        "has_analysis": bool(record.get("stage_analysis_response") or record.get("analysis_response")),
        "has_script": bool(record.get("script_response") or record.get("analysis_response")),
        "has_video": bool(video_response.get("video_url")),
        "has_voice": bool(voice_response.get("audio_url") or video_response.get("audio_url")),
        "product_qa_status": product_qa.get("status", ""),
        "analysis_qa_status": analysis_qa.get("status", ""),
        "has_assets": bool(voice_response.get("audio_url") or video_response.get("image_url") or video_response.get("audio_url") or video_response.get("video_url")),
    }


def _update_record(task_id: str, settings: Settings | None = None, **updates: Any) -> dict[str, Any]:
    settings = settings or Settings.from_env()
    record = load_result_record(task_id, settings.output_dir)
    now = _now_iso()
    if record is None:
        record = {
            "task_id": _safe_task_id(task_id),
            "source_url": "",
            "created_at": now,
            "updated_at": now,
            "product_response": None,
            "product_qa_response": None,
            "stage_analysis_response": None,
            "analysis_qa_response": None,
            "script_response": None,
            "analysis_response": None,
            "video_response": None,
            "voice_response": None,
        }
    record.update({key: value for key, value in updates.items() if value is not None})
    record["updated_at"] = now
    _write_record(task_id, record, settings.output_dir)
    return record


def _write_record(task_id: str, record: dict[str, Any], output_dir: Path) -> None:
    path = _record_path(task_id, output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def _record_path(task_id: str, output_dir: Path) -> Path:
    safe_task_id = _safe_task_id(task_id)
    return output_dir / "records" / f"{safe_task_id}.json"


def _safe_task_id(task_id: str) -> str:
    if not TASK_ID_RE.fullmatch(task_id):
        raise ValueError("无效的任务 ID")
    return task_id


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
