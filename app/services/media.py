from __future__ import annotations

import textwrap
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.config import Settings
from app.models import GenerateVideoRequest, GenerateVideoResponse

VIDEO_SIZE = (1080, 1920)


def generate_video_assets(request: GenerateVideoRequest, settings: Settings | None = None) -> GenerateVideoResponse:
    settings = settings or Settings.from_env()
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    image_url = ""
    audio_url = ""
    video_url = ""

    try:
        image_path = _create_cover_image(request, settings.output_dir)
        image_url = f"/static/outputs/{image_path.name}"
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"封面图生成失败：{exc}")

    if settings.has_dashscope_tts:
        try:
            audio_path = _generate_tts(request, settings)
            audio_url = f"/static/outputs/{audio_path.name}"
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"TTS 生成失败：{exc}")
    else:
        warnings.append("未配置 DASHSCOPE_API_KEY，已跳过 TTS 音频生成。")

    if audio_url and image_url:
        try:
            video_path = _compose_video(request, settings.output_dir)
            video_url = f"/static/outputs/{video_path.name}"
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"MP4 合成失败：{exc}")
    else:
        warnings.append("缺少音频或封面图，已跳过 MP4 合成。")

    return GenerateVideoResponse(video_url=video_url, audio_url=audio_url, image_url=image_url, warnings=warnings)


def _create_cover_image(request: GenerateVideoRequest, output_dir: Path) -> Path:
    product = request.product or {}
    title = _nested_value(product, "title", "value") or "Amazon Product"
    script = request.short_video_script.get("script") or request.tts_text or "商品短视频"
    image = Image.new("RGB", VIDEO_SIZE, "#f7f3ea")
    draw = ImageDraw.Draw(image)
    font_large = _font(58)
    font_mid = _font(40)
    font_small = _font(32)

    draw.rectangle((0, 0, 1080, 220), fill="#1f2933")
    draw.text((72, 70), "AI Product Analysis", fill="#ffffff", font=font_mid)
    draw.rounded_rectangle((72, 300, 1008, 1010), radius=28, fill="#ffffff", outline="#d8d0c3", width=3)
    product_image = _download_first_product_image(_product_image_urls(product))
    if product_image:
        _paste_contained(image, product_image, (120, 340, 960, 800))
        draw.text((120, 840), _wrap_text(title, 26), fill="#111827", font=font_mid, spacing=12)
    else:
        draw.text((120, 390), _wrap_text(title, 22), fill="#111827", font=font_large, spacing=16)
    draw.text((120, 1110), _wrap_text(script, 24), fill="#263238", font=font_mid, spacing=14)
    draw.rectangle((72, 1670, 1008, 1780), fill="#0f766e")
    draw.text((120, 1702), "150字中文口播 + 卖点卡片", fill="#ffffff", font=font_small)
    path = output_dir / f"{_safe_task_id(request.task_id)}.png"
    image.save(path)
    return path


def _generate_tts(request: GenerateVideoRequest, settings: Settings) -> Path:
    text = request.tts_text or request.short_video_script.get("script") or ""
    if not text.strip():
        raise ValueError("没有可用于 TTS 的文案")
    payload = {
        "model": settings.dashscope_tts_model,
        "input": {"text": text},
        "parameters": {"voice": settings.dashscope_voice_id or settings.dashscope_preferred_voice_name},
    }
    response = httpx.post(
        f"{settings.dashscope_base_url.rstrip('/')}/services/aigc/multimodal-generation/generation",
        headers={"Authorization": f"Bearer {settings.dashscope_api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    audio_url = data.get("output", {}).get("audio", {}).get("url") or data.get("output", {}).get("url")
    if not audio_url:
        raise ValueError("DashScope 响应中没有音频 URL")
    audio_response = httpx.get(audio_url, timeout=60.0)
    audio_response.raise_for_status()
    path = settings.output_dir / f"{_safe_task_id(request.task_id)}.mp3"
    path.write_bytes(audio_response.content)
    return path


def _compose_video(request: GenerateVideoRequest, output_dir: Path) -> Path:
    from moviepy.editor import AudioFileClip, ImageClip

    task_id = _safe_task_id(request.task_id)
    image_path = output_dir / f"{task_id}.png"
    audio_path = output_dir / f"{task_id}.mp3"
    video_path = output_dir / f"{task_id}.mp4"
    audio = AudioFileClip(str(audio_path))
    try:
        duration = max(15, min(30, audio.duration))
        clip = ImageClip(str(image_path)).set_duration(duration).set_audio(audio.subclip(0, min(duration, audio.duration)))
        try:
            clip.write_videofile(str(video_path), fps=24, codec="libx264", audio_codec="aac", verbose=False, logger=None)
        finally:
            clip.close()
    finally:
        audio.close()
    return video_path


def _product_image_urls(product: dict) -> list[str]:
    urls: list[str] = []
    main_image_url = _nested_value(product, "main_image_url")
    if main_image_url:
        urls.append(main_image_url)
    candidates = product.get("image_candidates") if isinstance(product, dict) else None
    if isinstance(candidates, list):
        urls.extend(str(candidate) for candidate in candidates if candidate)
    return _unique_non_empty(urls)


def _download_first_product_image(urls: list[str]) -> Image.Image | None:
    for url in urls:
        try:
            response = httpx.get(url, timeout=20.0)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGBA")
        except Exception:  # noqa: BLE001
            continue
    return None


def _paste_contained(canvas: Image.Image, source: Image.Image, box: tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    max_size = (x2 - x1, y2 - y1)
    image = ImageOps.contain(source, max_size)
    background = Image.new("RGBA", image.size, "#ffffff")
    background.alpha_composite(image)
    left = x1 + (max_size[0] - image.width) // 2
    top = y1 + (max_size[1] - image.height) // 2
    canvas.paste(background.convert("RGB"), (left, top))


def _nested_value(data: dict, *keys: str) -> str:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return str(current or "")


def _unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            result.append(cleaned)
            seen.add(cleaned)
    return result


def _font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def _wrap_text(text: str, width: int) -> str:
    return "\n".join(textwrap.wrap(str(text), width=width, break_long_words=True))


def _safe_task_id(task_id: str) -> str:
    return "".join(ch for ch in task_id if ch.isalnum() or ch in {"-", "_"})[:80] or "video"
