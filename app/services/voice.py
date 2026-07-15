from __future__ import annotations

from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import CreateVoiceRequest, GenerateVoiceRequest, GenerateVoiceResponse
from app.services.voices import create_voice_profile

def generate_voice_audio(request: GenerateVoiceRequest, settings: Settings | None = None) -> GenerateVoiceResponse:
    settings = settings or Settings.from_env()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    if not settings.has_dashscope_tts:
        return GenerateVoiceResponse(warnings=["未配置 DASHSCOPE_API_KEY，无法生成口播语音。"])
    if not request.text.strip():
        return GenerateVoiceResponse(warnings=["没有可用于生成口播语音的文本。"])

    warnings: list[str] = []
    voice_id = request.voice_id.strip()
    if not voice_id:
        voice_prompt = request.voice_instruction.strip() or "年轻活泼的女性声音，语速较快，带有明显的上扬语调，适合介绍时尚产品。"
        created = create_voice_profile(
            CreateVoiceRequest(name=_profile_name(request, settings), prompt=voice_prompt, sample_rate=request.sample_rate, audio_format=request.audio_format),
            settings,
        )
        if not created.profile:
            return GenerateVoiceResponse(warnings=created.warnings)
        voice_id = created.profile.voice_id
        warnings.extend(created.warnings)

    try:
        response = httpx.post(
            f"{settings.dashscope_base_url.rstrip('/')}/services/aigc/multimodal-generation/generation",
            json={"model": settings.dashscope_tts_model, "input": {"text": request.text, "voice": voice_id}},
            headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "Content-Type": "application/json"},
            timeout=60.0,
        )
    except Exception as exc:  # noqa: BLE001
        return GenerateVoiceResponse(warnings=[f"DashScope 语音合成请求失败：{exc}"])
    if response.status_code != 200:
        return GenerateVoiceResponse(warnings=[_response_error_message("DashScope 语音合成失败", response)])
    try:
        result = response.json()
    except Exception as exc:  # noqa: BLE001
        return GenerateVoiceResponse(warnings=[f"DashScope 语音合成响应不是有效 JSON：{exc}"])

    remote_audio_url = _extract_audio_url_from_result(result)
    if not remote_audio_url:
        return GenerateVoiceResponse(warnings=["DashScope 语音合成响应中没有音频 URL。"])

    local_url = ""
    try:
        audio_response = httpx.get(remote_audio_url, timeout=60.0)
        audio_response.raise_for_status()
        path = settings.output_dir / f"{_safe_task_id(request.task_id)}.{_audio_extension(remote_audio_url, request.audio_format)}"
        path.write_bytes(audio_response.content)
        local_url = f"/static/outputs/{path.name}"
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"音频 URL 有效期约 24 小时，本地保存失败：{exc}")

    return GenerateVoiceResponse(audio_url=local_url or remote_audio_url, remote_audio_url=remote_audio_url, warnings=warnings)


def _profile_name(request: GenerateVoiceRequest, settings: Settings) -> str:
    name = (request.voice or "").strip()
    if name and name not in {"longanlingxi", "longxiaochun"}:
        return name
    return settings.dashscope_preferred_voice_name or "custom_voice"


def _extract_audio_url_from_result(result) -> str:
    output = getattr(result, "output", None)
    if output is None:
        try:
            output = result["output"]
        except Exception:  # noqa: BLE001
            output = None
    if not isinstance(output, dict):
        return ""
    audio = output.get("audio")
    if isinstance(audio, dict) and audio.get("url"):
        return str(audio["url"])
    if output.get("url"):
        return str(output["url"])
    if output.get("audio_url"):
        return str(output["audio_url"])
    return ""


def _response_error_message(prefix: str, response) -> str:
    try:
        data = response.json()
        detail = " ".join(str(data.get(key, "")) for key in ("code", "message") if data.get(key))
    except Exception:  # noqa: BLE001
        detail = getattr(response, "text", "")[:500]
    return f"{prefix}：HTTP {response.status_code} {detail}".strip()


def _audio_extension(audio_url: str, requested_format: str) -> str:
    path = urlparse(audio_url).path
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return ext if ext in {"wav", "mp3", "aac", "opus"} else _safe_extension(requested_format)


def _safe_task_id(task_id: str) -> str:
    return "".join(ch for ch in task_id if ch.isalnum() or ch in {"-", "_"})[:80] or "voice"


def _safe_extension(audio_format: str) -> str:
    ext = "".join(ch for ch in audio_format.lower() if ch.isalnum())
    return ext if ext in {"wav", "mp3", "aac", "opus"} else "wav"
