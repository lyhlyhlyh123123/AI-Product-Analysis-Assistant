from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import Settings
from app.models import CreateVoiceRequest, CreateVoiceResponse, VoiceProfile

VOICE_DESIGN_MODEL = "qwen-voice-design"
PREVIEW_TEXT = "大家好，欢迎来到我们的直播间！今天给大家推荐的这款产品真的超级好用。"


def list_voice_profiles(settings: Settings | None = None) -> list[VoiceProfile]:
    settings = settings or Settings.from_env()
    path = _voices_path(settings.output_dir)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [VoiceProfile.model_validate(item) for item in data if isinstance(item, dict)]


def create_voice_profile(request: CreateVoiceRequest, settings: Settings | None = None) -> CreateVoiceResponse:
    settings = settings or Settings.from_env()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    if not settings.has_dashscope_tts:
        return CreateVoiceResponse(warnings=["未配置 DASHSCOPE_API_KEY，无法创建音色。"])
    prompt = request.prompt.strip()
    if not prompt:
        return CreateVoiceResponse(warnings=["请填写声音描述后再创建音色。"])

    payload = _voice_design_payload(request, settings, prompt)
    try:
        response = httpx.post(
            f"{settings.dashscope_base_url.rstrip('/')}/services/audio/tts/customization",
            json=payload,
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "Content-Type": "application/json"},
            timeout=60.0,
        )
    except Exception as exc:  # noqa: BLE001
        return CreateVoiceResponse(warnings=[f"DashScope 声音设计请求失败：{exc}"])
    if response.status_code != 200:
        return CreateVoiceResponse(warnings=[_response_error_message("DashScope 声音设计失败", response)])
    try:
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        return CreateVoiceResponse(warnings=[f"DashScope 声音设计响应不是有效 JSON：{exc}"])
    voice_id = data.get("output", {}).get("voice")
    if not voice_id:
        return CreateVoiceResponse(warnings=["DashScope 声音设计响应中没有 voice。"])

    profile = VoiceProfile(
        id=_safe_profile_id(request.name or settings.dashscope_preferred_voice_name),
        voice_id=str(voice_id),
        name=request.name or settings.dashscope_preferred_voice_name or "custom_voice",
        prompt=prompt,
        model=settings.dashscope_tts_model,
        created_at=_now_iso(),
    )
    profiles = [item for item in list_voice_profiles(settings) if item.id != profile.id]
    profiles.append(profile)
    _write_profiles(settings.output_dir, profiles)
    return CreateVoiceResponse(profile=profile)


def _voice_design_payload(request: CreateVoiceRequest, settings: Settings, prompt: str) -> dict:
    return {
        "model": VOICE_DESIGN_MODEL,
        "input": {
            "action": "create",
            "target_model": settings.dashscope_tts_model,
            "preferred_name": _preferred_name(request.name, settings),
            "voice_prompt": prompt,
            "preview_text": PREVIEW_TEXT,
        },
        "parameters": {"sample_rate": request.sample_rate, "response_format": request.audio_format},
    }


def _write_profiles(output_dir: Path, profiles: list[VoiceProfile]) -> None:
    path = _voices_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([profile.model_dump(mode="json") for profile in profiles], ensure_ascii=False, indent=2), encoding="utf-8")


def _voices_path(output_dir: Path) -> Path:
    return output_dir / "voices.json"


def _preferred_name(name: str, settings: Settings) -> str:
    for candidate in (name, settings.dashscope_preferred_voice_name, "custom_voice"):
        safe = _ascii_identifier(candidate)
        if safe:
            return safe
    return "custom_voice"


def _safe_profile_id(name: str) -> str:
    safe = "".join(ch for ch in name.strip().lower().replace(" ", "-") if ch.isalnum() or ch in {"-", "_"})
    return safe[:80] or "custom_voice"


def _ascii_identifier(value: str) -> str:
    safe = "".join(ch for ch in str(value).strip().lower().replace(" ", "_") if ch.isascii() and (ch.isalnum() or ch == "_"))
    if not safe or not safe[0].isalpha():
        return ""
    return safe[:80]


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _response_error_message(prefix: str, response) -> str:
    try:
        data = response.json()
        detail = " ".join(str(data.get(key, "")) for key in ("code", "message") if data.get(key))
    except Exception:  # noqa: BLE001
        detail = getattr(response, "text", "")[:500]
    return f"{prefix}：HTTP {response.status_code} {detail}".strip()
